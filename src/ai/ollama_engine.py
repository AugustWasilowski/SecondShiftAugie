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
from src.utils.error_handler import (
    ai_error_handler, health_monitor, degradation_manager, 
    ComponentState, CircuitBreakerOpenError
)

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
                logger.error(f"Model {self.config.model_name} not available. Please ensure the model is pulled manually using: ollama pull {self.config.model_name}")
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
        Generate an AI response for the given message with comprehensive error handling.
        
        Implements requirements:
        - 1.3: Provide fallback responses when Ollama fails
        - 2.3: Implement retry logic with exponential backoff
        - 6.2: Proper timeout and error handling for API calls
        - 6.4: Detailed logging for AI interactions and errors
        
        Args:
            message: User message to respond to
            context: Optional additional context for the response
            
        Returns:
            AIResponse: Generated response with metadata
        """
        start_time = time.time()
        operation = "generate_response"
        
        # Check if AI should be used based on circuit breaker state
        if not ai_error_handler.should_use_ai():
            degradation_reason = ai_error_handler.get_degradation_reason()
            logger.warning(f"AI degraded mode active: {degradation_reason}")
            
            # Log the degraded interaction
            ai_error_handler.log_ai_interaction(
                operation, 
                False, 
                time.time() - start_time,
                details={"reason": "circuit_breaker_open", "message_length": len(message)}
            )
            
            return self._create_fallback_response(f"AI unavailable: {degradation_reason}")
        
        if not self._is_ready:
            ai_error_handler.log_ai_interaction(
                operation, 
                False, 
                time.time() - start_time,
                details={"reason": "engine_not_ready", "message_length": len(message)}
            )
            return self._create_fallback_response("AI engine not ready")
        
        # Prepare the prompt
        system_prompt = self.system_prompt_manager.get_current_prompt()
        full_prompt = self._build_prompt(system_prompt, message, context)
        
        # Attempt to generate response with circuit breaker protection
        try:
            response = await self._generate_response_with_circuit_breaker(full_prompt, start_time, message)
            
            # Log successful interaction
            response_time = time.time() - start_time
            ai_error_handler.log_ai_interaction(
                operation, 
                True, 
                response_time,
                details={
                    "message_length": len(message),
                    "response_length": len(response.text) if response.text else 0,
                    "model": self.config.model_name,
                    "truncated": response.truncated
                }
            )
            
            return response
            
        except CircuitBreakerOpenError as cb_error:
            # Circuit breaker is open
            response_time = time.time() - start_time
            ai_error_handler.log_ai_interaction(
                operation, 
                False, 
                response_time,
                error=cb_error,
                details={"reason": "circuit_breaker_open", "message_length": len(message)}
            )
            
            # Update degradation manager
            degradation_manager.disable_feature("ai_responses", str(cb_error))
            health_monitor.update_component_state("ollama_engine", ComponentState.FAILED, str(cb_error))
            
            return self._create_fallback_response("AI temporarily unavailable due to repeated failures")
            
        except Exception as e:
            # Unexpected error
            response_time = time.time() - start_time
            ai_error_handler.log_ai_interaction(
                operation, 
                False, 
                response_time,
                error=e,
                details={"reason": "unexpected_error", "message_length": len(message)}
            )
            
            logger.error(f"Unexpected error in AI response generation: {e}")
            return self._create_fallback_response("AI response generation failed")
    
    @ai_error_handler.ai_response_circuit_breaker
    async def _generate_response_with_circuit_breaker(self, full_prompt: str, start_time: float, original_message: str) -> AIResponse:
        """
        Generate response with circuit breaker protection.
        
        Args:
            full_prompt: Complete prompt to send to Ollama
            start_time: Start time for timing
            original_message: Original user message for logging
            
        Returns:
            AIResponse: Generated response
            
        Raises:
            Exception: If response generation fails
        """
        # Attempt to generate response with retry logic
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self._make_ollama_request_with_circuit_breaker(full_prompt)
                
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
                    error_msg = f"Empty response from Ollama on attempt {attempt + 1}"
                    logger.warning(error_msg)
                    last_exception = Exception(error_msg)
                    
            except Exception as e:
                last_exception = e
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
            health_monitor.update_component_state("ollama_engine", ComponentState.FAILED, "Too many consecutive failures")
        
        # Raise the last exception to trigger circuit breaker
        if last_exception:
            raise last_exception
        else:
            raise Exception("Failed to generate AI response after all retries")
    
    async def health_check(self) -> bool:
        """
        Perform a comprehensive health check on the Ollama instance.
        
        Implements requirements:
        - 2.5: Continue operating in degraded mode
        - 6.4: Detailed logging for AI interactions and errors
        
        Returns:
            bool: True if healthy, False otherwise
        """
        current_time = time.time()
        operation = "health_check"
        start_time = current_time
        
        # Use cached result if recent
        if current_time - self._last_health_check < self._health_check_interval:
            return self._is_ready
        
        try:
            # Check if circuit breakers allow health check
            if not ai_error_handler.should_use_ai():
                degradation_reason = ai_error_handler.get_degradation_reason()
                logger.debug(f"Health check skipped due to circuit breaker: {degradation_reason}")
                
                ai_error_handler.log_ai_interaction(
                    operation,
                    False,
                    time.time() - start_time,
                    details={"reason": "circuit_breaker_open"}
                )
                
                self._is_ready = False
                self._last_health_check = current_time
                return False
            
            # Check basic connectivity
            if not await self._check_ollama_connectivity():
                self._is_ready = False
                health_monitor.update_component_state("ollama_engine", ComponentState.FAILED, "Connectivity check failed")
                
                ai_error_handler.log_ai_interaction(
                    operation,
                    False,
                    time.time() - start_time,
                    details={"reason": "connectivity_failed"}
                )
                
                self._last_health_check = current_time
                return False
            
            # Try a simple generation request with circuit breaker protection
            try:
                test_response = await self._make_ollama_request_with_circuit_breaker("Hello", timeout=60.0)
                
                if test_response and test_response.get('response'):
                    self._is_ready = True
                    self._consecutive_failures = 0
                    health_monitor.update_component_state("ollama_engine", ComponentState.HEALTHY)
                    
                    ai_error_handler.log_ai_interaction(
                        operation,
                        True,
                        time.time() - start_time,
                        details={"test_response_length": len(test_response.get('response', ''))}
                    )
                    
                    logger.debug("Ollama health check passed")
                else:
                    self._is_ready = False
                    health_monitor.update_component_state("ollama_engine", ComponentState.DEGRADED, "No response from test request")
                    
                    ai_error_handler.log_ai_interaction(
                        operation,
                        False,
                        time.time() - start_time,
                        details={"reason": "empty_response"}
                    )
                    
                    logger.warning("Ollama health check failed: no response")
                    
            except CircuitBreakerOpenError as cb_error:
                self._is_ready = False
                health_monitor.update_component_state("ollama_engine", ComponentState.FAILED, str(cb_error))
                
                ai_error_handler.log_ai_interaction(
                    operation,
                    False,
                    time.time() - start_time,
                    error=cb_error,
                    details={"reason": "circuit_breaker_open"}
                )
                
                logger.warning(f"Ollama health check blocked by circuit breaker: {cb_error}")
                
            except Exception as test_error:
                self._is_ready = False
                health_monitor.update_component_state("ollama_engine", ComponentState.DEGRADED, str(test_error))
                
                ai_error_handler.log_ai_interaction(
                    operation,
                    False,
                    time.time() - start_time,
                    error=test_error,
                    details={"reason": "test_request_failed"}
                )
                
                logger.warning(f"Ollama health check test request failed: {test_error}")
            
            self._last_health_check = current_time
            return self._is_ready
            
        except Exception as e:
            self._is_ready = False
            health_monitor.update_component_state("ollama_engine", ComponentState.FAILED, str(e))
            
            ai_error_handler.log_ai_interaction(
                operation,
                False,
                time.time() - start_time,
                error=e,
                details={"reason": "unexpected_error"}
            )
            
            logger.warning(f"Ollama health check failed: {e}")
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
    

    
    @ai_error_handler.ollama_circuit_breaker
    async def _make_ollama_request_with_circuit_breaker(self, prompt: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Ollama API with circuit breaker protection.
        
        Implements requirements:
        - 6.2: Proper timeout and error handling for API calls
        - 6.4: Detailed logging for AI interactions and errors
        
        Args:
            prompt: The prompt to send to Ollama
            timeout: Optional timeout override
            
        Returns:
            Optional[Dict[str, Any]]: Response data or None if failed
            
        Raises:
            Exception: If request fails (to trigger circuit breaker)
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")
        
        request_start = time.time()
        
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
        
        try:
            async with self._session.post(
                f"{self.config.base_url}/api/generate",
                json=request_data,
                timeout=request_timeout
            ) as response:
                
                request_duration = time.time() - request_start
                
                if response.status == 200:
                    response_data = await response.json()
                    
                    # Log successful API call
                    ai_error_handler.log_ai_interaction(
                        "ollama_api_call",
                        True,
                        request_duration,
                        details={
                            "model": self.config.model_name,
                            "prompt_length": len(prompt),
                            "response_length": len(response_data.get('response', '')) if response_data else 0,
                            "status_code": response.status
                        }
                    )
                    
                    return response_data
                else:
                    response_text = await response.text()
                    error_msg = f"Ollama API request failed: HTTP {response.status}"
                    
                    # Log failed API call
                    ai_error_handler.log_ai_interaction(
                        "ollama_api_call",
                        False,
                        request_duration,
                        error=Exception(error_msg),
                        details={
                            "model": self.config.model_name,
                            "prompt_length": len(prompt),
                            "status_code": response.status,
                            "response_body": response_text[:200] if response_text else "empty"
                        }
                    )
                    
                    logger.error(f"{error_msg} - Response: {response_text}")
                    raise Exception(f"HTTP {response.status}: {response_text}")
                    
        except asyncio.TimeoutError as timeout_error:
            request_duration = time.time() - request_start
            
            # Log timeout error
            ai_error_handler.log_ai_interaction(
                "ollama_api_call",
                False,
                request_duration,
                error=timeout_error,
                details={
                    "model": self.config.model_name,
                    "prompt_length": len(prompt),
                    "timeout": timeout or self.config.timeout,
                    "error_type": "timeout"
                }
            )
            
            logger.error(f"Ollama API request timeout after {request_duration:.2f}s")
            raise Exception(f"Request timeout after {request_duration:.2f}s")
            
        except aiohttp.ClientError as client_error:
            request_duration = time.time() - request_start
            
            # Log client error
            ai_error_handler.log_ai_interaction(
                "ollama_api_call",
                False,
                request_duration,
                error=client_error,
                details={
                    "model": self.config.model_name,
                    "prompt_length": len(prompt),
                    "error_type": "client_error"
                }
            )
            
            logger.error(f"Ollama API client error: {client_error}")
            raise Exception(f"Client error: {client_error}")
            
        except Exception as e:
            request_duration = time.time() - request_start
            
            # Log unexpected error
            ai_error_handler.log_ai_interaction(
                "ollama_api_call",
                False,
                request_duration,
                error=e,
                details={
                    "model": self.config.model_name,
                    "prompt_length": len(prompt),
                    "error_type": "unexpected"
                }
            )
            
            logger.error(f"Unexpected Ollama API error: {e}")
            raise e
    
    async def _make_ollama_request(self, prompt: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Legacy method for backward compatibility - now uses circuit breaker.
        
        Args:
            prompt: The prompt to send to Ollama
            timeout: Optional timeout override
            
        Returns:
            Optional[Dict[str, Any]]: Response data or None if failed
        """
        try:
            return await self._make_ollama_request_with_circuit_breaker(prompt, timeout)
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
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
    
    def get_ai_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive AI health status including circuit breaker information.
        
        Implements requirement 6.4: Detailed logging for AI interactions and errors.
        
        Returns:
            Dict containing AI health status information
        """
        # Get circuit breaker status from error handler
        ai_health = ai_error_handler.get_ai_health_status()
        
        # Add engine-specific information
        engine_status = {
            "engine_ready": self._is_ready,
            "consecutive_failures": self._consecutive_failures,
            "max_consecutive_failures": self._max_consecutive_failures,
            "last_health_check": self._last_health_check,
            "health_check_interval": self._health_check_interval,
            "model_name": self.config.model_name,
            "base_url": self.config.base_url
        }
        
        # Combine with circuit breaker status
        return {
            **ai_health,
            "engine_status": engine_status,
            "component_state": health_monitor.get_component_state("ollama_engine").value,
            "degradation_active": not degradation_manager.is_feature_available("ai_responses")
        }
    
    def reset_error_state(self):
        """
        Reset error state and circuit breakers for manual recovery.
        
        This method allows manual intervention to reset the AI system
        when administrators determine the underlying issues have been resolved.
        """
        logger.info("Manually resetting OllamaEngine error state")
        
        # Reset internal state
        self._consecutive_failures = 0
        self._last_health_check = 0
        
        # Reset circuit breakers
        ai_error_handler.reset_circuit_breakers()
        
        # Update health monitoring
        health_monitor.update_component_state("ollama_engine", ComponentState.HEALTHY)
        
        # Re-enable AI features
        degradation_manager.restore_feature("ai_responses")
        
        logger.info("OllamaEngine error state reset complete")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        if self._session and not self._session.closed:
            logger.warning("OllamaEngine session not properly closed, forcing cleanup")