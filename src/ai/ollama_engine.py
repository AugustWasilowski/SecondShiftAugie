"""
Ollama AI Engine for generating intelligent responses using local Ollama instance.

This module provides the core AI functionality for the SecondShiftAugie Discord bot,
integrating with a local Ollama instance running the Qwen2.5:1.7b model.

Requirements addressed:
- 1.1: Send messages to Ollama and receive AI responses
- 1.2: Process requests with Qwen2.5:1.7b model
- 1.3: Provide fallback responses when Ollama fails
- 2.1: Check Ollama connectivity and model availability
- 2.2: Attempt to pull model if not available
- 2.3: Implement retry logic with exponential backoff
- 6.2: Proper timeout and error handling for API calls
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import time
import aiohttp
import json
from pathlib import Path

from src.config.ollama_config import OllamaConfig
from src.ai.system_prompt_manager import SystemPromptManager

logger = logging.getLogger(__name__)


@dataclass
class AIResponse:
    """Response object for AI-generated content."""
    text: str
    success: bool
    error_message: Optional[str] = None
    model_used: Optional[str] = None
    response_time: Optional[float] = None
    truncated: bool = False


class OllamaEngine:
    """
    Core AI engine for generating responses using local Ollama instance.
    
    Manages connection to Ollama, handles request/response processing,
    implements retry logic, and provides health monitoring capabilities.
    """
    
    def __init__(self, config: OllamaConfig, system_prompt_manager: SystemPromptManager):
        """
        Initialize the Ollama AI engine.
        
        Args:
            config: Ollama configuration settings
            system_prompt_manager: Manager for dynamic system prompts
        """
        self.config = config
        self.system_prompt_manager = system_prompt_manager
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_ready = False
        self._last_health_check = 0
        self._health_check_interval = 60  # seconds
        self._consecutive_failures = 0
        self._max_consecutive_failures = 5
        
        # Fallback responses for when Ollama is unavailable
        self._fallback_responses = [
            "I'm having trouble connecting to my AI brain right now. Please try again in a moment!",
            "My AI systems are temporarily offline. I'll be back to full capacity soon!",
            "Sorry, I'm experiencing some technical difficulties. Please bear with me!",
            "My neural networks are taking a coffee break. Try asking me again shortly!",
        ]
        
        logger.info(f"OllamaEngine initialized with model: {config.model_name}")
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama engine and verify connectivity.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            # Create HTTP session
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Check Ollama connectivity
            if not await self._check_ollama_connectivity():
                logger.error("Failed to connect to Ollama instance")
                return False
            
            # Check if model is available
            if not await self._check_model_availability():
                logger.warning(f"Model {self.config.model_name} not available, attempting to pull...")
                if not await self._pull_model():
                    logger.error(f"Failed to pull model {self.config.model_name}")
                    return False
            
            self._is_ready = True
            self._consecutive_failures = 0
            logger.info("OllamaEngine initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during OllamaEngine initialization: {e}")
            return False
    
    async def generate_response(self, message: str, context: Optional[str] = None) -> AIResponse:
        """
        Generate an AI response for the given message.
        
        Args:
            message: User message to respond to
            context: Optional additional context for the response
            
        Returns:
            AIResponse: Generated response with metadata
        """
        if not self._is_ready:
            return self._create_fallback_response("AI engine not ready")
        
        start_time = time.time()
        
        # Prepare the prompt
        system_prompt = self.system_prompt_manager.get_current_prompt()
        full_prompt = self._build_prompt(system_prompt, message, context)
        
        # Attempt to generate response with retry logic
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self._make_ollama_request(full_prompt)
                
                if response and response.get('response'):
                    response_text = response['response'].strip()
                    
                    # Validate and truncate response if needed
                    truncated = False
                    if len(response_text) > self.config.max_response_length:
                        response_text = self._truncate_response(response_text)
                        truncated = True
                    
                    # Reset failure counter on success
                    self._consecutive_failures = 0
                    
                    response_time = time.time() - start_time
                    return AIResponse(
                        text=response_text,
                        success=True,
                        model_used=self.config.model_name,
                        response_time=response_time,
                        truncated=truncated
                    )
                else:
                    logger.warning(f"Empty response from Ollama on attempt {attempt + 1}")
                    
            except Exception as e:
                logger.warning(f"Ollama request failed on attempt {attempt + 1}: {e}")
                
                if attempt < self.config.max_retries:
                    # Exponential backoff
                    delay = self.config.retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
        
        # All attempts failed
        self._consecutive_failures += 1
        logger.error(f"All Ollama request attempts failed. Consecutive failures: {self._consecutive_failures}")
        
        # Check if we should mark as not ready
        if self._consecutive_failures >= self._max_consecutive_failures:
            self._is_ready = False
            logger.error("Too many consecutive failures, marking OllamaEngine as not ready")
        
        return self._create_fallback_response("Failed to generate AI response after retries")
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the Ollama instance.
        
        Returns:
            bool: True if healthy, False otherwise
        """
        current_time = time.time()
        
        # Use cached result if recent
        if current_time - self._last_health_check < self._health_check_interval:
            return self._is_ready
        
        try:
            # Check basic connectivity
            if not await self._check_ollama_connectivity():
                self._is_ready = False
                return False
            
            # Try a simple generation request
            test_response = await self._make_ollama_request("Hello", timeout=10.0)
            
            if test_response and test_response.get('response'):
                self._is_ready = True
                self._consecutive_failures = 0
                logger.debug("Ollama health check passed")
            else:
                self._is_ready = False
                logger.warning("Ollama health check failed: no response")
            
            self._last_health_check = current_time
            return self._is_ready
            
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            self._is_ready = False
            self._last_health_check = current_time
            return False
    
    def is_ready(self) -> bool:
        """
        Check if the engine is ready to process requests.
        
        Returns:
            bool: True if ready, False otherwise
        """
        return self._is_ready
    
    async def cleanup(self):
        """Clean up resources and close connections."""
        if self._session:
            await self._session.close()
            self._session = None
        
        self._is_ready = False
        logger.info("OllamaEngine cleanup completed")
    
    async def _check_ollama_connectivity(self) -> bool:
        """
        Check if Ollama instance is accessible.
        
        Returns:
            bool: True if accessible, False otherwise
        """
        try:
            if not self._session:
                return False
            
            async with self._session.get(f"{self.config.base_url}/api/tags") as response:
                return response.status == 200
                
        except Exception as e:
            logger.debug(f"Ollama connectivity check failed: {e}")
            return False
    
    async def _check_model_availability(self) -> bool:
        """
        Check if the specified model is available in Ollama.
        
        Returns:
            bool: True if model is available, False otherwise
        """
        try:
            if not self._session:
                return False
            
            async with self._session.get(f"{self.config.base_url}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get('models', [])
                    
                    for model in models:
                        if model.get('name') == self.config.model_name:
                            logger.info(f"Model {self.config.model_name} is available")
                            return True
                    
                    logger.warning(f"Model {self.config.model_name} not found in available models")
                    return False
                else:
                    logger.error(f"Failed to get model list: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error checking model availability: {e}")
            return False
    
    async def _pull_model(self) -> bool:
        """
        Attempt to pull the specified model from Ollama.
        
        Returns:
            bool: True if model pulled successfully, False otherwise
        """
        try:
            if not self._session:
                return False
            
            logger.info(f"Attempting to pull model: {self.config.model_name}")
            
            pull_data = {"name": self.config.model_name}
            
            # Use a longer timeout for model pulling
            pull_timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes
            
            async with self._session.post(
                f"{self.config.base_url}/api/pull",
                json=pull_data,
                timeout=pull_timeout
            ) as response:
                
                if response.status == 200:
                    # Stream the response to monitor progress
                    async for line in response.content:
                        if line:
                            try:
                                progress = json.loads(line.decode())
                                if progress.get('status') == 'success':
                                    logger.info(f"Successfully pulled model: {self.config.model_name}")
                                    return True
                                elif 'error' in progress:
                                    logger.error(f"Error pulling model: {progress['error']}")
                                    return False
                            except json.JSONDecodeError:
                                continue
                    
                    # If we get here, check if model is now available
                    return await self._check_model_availability()
                else:
                    logger.error(f"Failed to pull model: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error pulling model: {e}")
            return False
    
    async def _make_ollama_request(self, prompt: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Ollama API.
        
        Args:
            prompt: The prompt to send to Ollama
            timeout: Optional timeout override
            
        Returns:
            Optional[Dict[str, Any]]: Response data or None if failed
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")
        
        request_data = {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature
            }
        }
        
        # Use custom timeout if provided
        if timeout:
            request_timeout = aiohttp.ClientTimeout(total=timeout)
        else:
            request_timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        
        async with self._session.post(
            f"{self.config.base_url}/api/generate",
            json=request_data,
            timeout=request_timeout
        ) as response:
            
            if response.status == 200:
                return await response.json()
            else:
                logger.error(f"Ollama API request failed: HTTP {response.status}")
                response_text = await response.text()
                logger.error(f"Response body: {response_text}")
                return None
    
    def _build_prompt(self, system_prompt: str, message: str, context: Optional[str] = None) -> str:
        """
        Build the complete prompt for Ollama.
        
        Args:
            system_prompt: System prompt from configuration
            message: User message
            context: Optional additional context
            
        Returns:
            str: Complete formatted prompt
        """
        prompt_parts = [system_prompt]
        
        if context:
            prompt_parts.append(f"Context: {context}")
        
        prompt_parts.append(f"User: {message}")
        prompt_parts.append("Assistant:")
        
        return "\n\n".join(prompt_parts)
    
    def _truncate_response(self, response: str) -> str:
        """
        Truncate response to fit within maximum length while preserving meaning.
        
        Args:
            response: Original response text
            
        Returns:
            str: Truncated response
        """
        max_length = self.config.max_response_length
        
        if len(response) <= max_length:
            return response
        
        # Try to truncate at sentence boundary
        sentences = response.split('. ')
        truncated = ""
        
        for sentence in sentences:
            if len(truncated + sentence + '. ') <= max_length - 3:  # Leave room for "..."
                truncated += sentence + '. '
            else:
                break
        
        if truncated:
            return truncated.rstrip() + "..."
        else:
            # If no complete sentences fit, truncate at word boundary
            words = response.split()
            truncated = ""
            
            for word in words:
                if len(truncated + word + " ") <= max_length - 3:
                    truncated += word + " "
                else:
                    break
            
            return truncated.rstrip() + "..."
    
    def _create_fallback_response(self, error_message: str) -> AIResponse:
        """
        Create a fallback response when AI generation fails.
        
        Args:
            error_message: Error message for logging
            
        Returns:
            AIResponse: Fallback response
        """
        import random
        
        fallback_text = random.choice(self._fallback_responses)
        
        return AIResponse(
            text=fallback_text,
            success=False,
            error_message=error_message
        )
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        if self._session and not self._session.closed:
            logger.warning("OllamaEngine session not properly closed, forcing cleanup")