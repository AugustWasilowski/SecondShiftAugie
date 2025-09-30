"""
Thread summarization functionality for the memory system.

This module implements the Summarizer class that generates rolling summaries
of conversation threads using LLM integration with proper error handling.

Requirements addressed:
- 1.2: Create rolling summaries when token budget exceeded
- 1.4: Update summaries with new conversation context
"""

import logging
import time
from typing import List, Optional
import json

import aiohttp

from .models import ThreadCtx, Msg
from .config import MemoryConfig


logger = logging.getLogger(__name__)


class SummarizerError(Exception):
    """Exception raised when summarization operations fail."""
    pass


class Summarizer:
    """
    Handles thread summarization using LLM integration.
    
    The Summarizer generates rolling summaries of conversation threads
    to maintain context while staying within token budgets.
    """
    
    def __init__(self, config: MemoryConfig):
        """
        Initialize the Summarizer.
        
        Args:
            config: Memory configuration containing LLM settings
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Summarization prompt template
        self.summary_prompt = (
            "Summarize the latest exchange for future context. "
            "Keep decisions, user preferences, facts, action items, unresolved questions. "
            "Return 5–10 bullet points, terse."
        )
        
        logger.info("Summarizer initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize the HTTP session for LLM requests.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)  # 30 second timeout for summaries
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Test connectivity to Ollama
            if not await self._check_ollama_connectivity():
                logger.error("Failed to connect to Ollama for summarization")
                return False
            
            logger.info("Summarizer initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during Summarizer initialization: {e}")
            return False
    
    async def generate_summary(self, ctx: ThreadCtx, messages: List[Msg], 
                             existing_summary: Optional[str] = None) -> str:
        """
        Generate a rolling summary of the conversation.
        
        Args:
            ctx: Thread context for scoping
            messages: List of messages to summarize
            existing_summary: Optional existing summary to update
            
        Returns:
            str: Generated summary text
            
        Raises:
            SummarizerError: If summary generation fails
        """
        if not ctx:
            raise SummarizerError("Thread context cannot be None")
        if not messages:
            raise SummarizerError("Messages list cannot be empty")
        
        start_time = time.time()
        
        try:
            # Build the prompt for summarization
            prompt = self._build_summary_prompt(messages, existing_summary)
            
            # Generate summary using Ollama
            summary = await self._generate_summary_with_llm(prompt)
            
            if not summary or not summary.strip():
                raise SummarizerError("Generated summary is empty")
            
            elapsed = time.time() - start_time
            logger.debug(f"Generated summary for {ctx} in {elapsed:.3f}s")
            
            return summary.strip()
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to generate summary for {ctx} after {elapsed:.3f}s: {e}")
            
            # Return a fallback summary if LLM fails
            if existing_summary:
                logger.info("Using existing summary as fallback")
                return existing_summary
            else:
                # Create a basic fallback summary
                fallback = self._create_fallback_summary(messages)
                logger.info("Created fallback summary")
                return fallback
    
    async def cleanup(self):
        """Clean up resources and close connections."""
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info("Summarizer cleanup completed")
    
    async def _check_ollama_connectivity(self) -> bool:
        """
        Check if Ollama instance is accessible.
        
        Returns:
            bool: True if accessible, False otherwise
        """
        try:
            if not self._session:
                return False
            
            async with self._session.get(f"{self.config.embed_ollama_url}/api/tags") as response:
                return response.status == 200
                
        except Exception as e:
            logger.debug(f"Ollama connectivity check failed: {e}")
            return False
    
    def _build_summary_prompt(self, messages: List[Msg], existing_summary: Optional[str] = None) -> str:
        """
        Build the prompt for summary generation.
        
        Args:
            messages: List of messages to summarize
            existing_summary: Optional existing summary to update
            
        Returns:
            str: Complete prompt for LLM
        """
        prompt_parts = [self.summary_prompt]
        
        if existing_summary:
            prompt_parts.append(f"\nPrevious summary:\n{existing_summary}")
            prompt_parts.append("\nNew conversation to incorporate:")
        else:
            prompt_parts.append("\nConversation to summarize:")
        
        # Add the conversation messages
        for msg in messages:
            role_label = msg.role.capitalize()
            prompt_parts.append(f"{role_label}: {msg.content}")
        
        prompt_parts.append("\nSummary:")
        
        return "\n".join(prompt_parts)
    
    async def _generate_summary_with_llm(self, prompt: str) -> str:
        """
        Generate summary using the LLM.
        
        Args:
            prompt: Complete prompt for summary generation
            
        Returns:
            str: Generated summary text
            
        Raises:
            SummarizerError: If LLM request fails
        """
        if not self._session:
            raise SummarizerError("HTTP session not initialized")
        
        request_data = {
            "model": self.config.embed_model,  # Use the same model as embeddings for consistency
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower temperature for more consistent summaries
                "max_tokens": 500    # Limit summary length
            }
        }
        
        try:
            async with self._session.post(
                f"{self.config.embed_ollama_url}/api/generate",
                json=request_data
            ) as response:
                
                if response.status == 200:
                    response_data = await response.json()
                    summary = response_data.get('response', '').strip()
                    
                    if not summary:
                        raise SummarizerError("Empty response from LLM")
                    
                    return summary
                else:
                    response_text = await response.text()
                    raise SummarizerError(f"LLM request failed: HTTP {response.status} - {response_text}")
                    
        except aiohttp.ClientError as e:
            raise SummarizerError(f"HTTP client error: {e}")
        except Exception as e:
            raise SummarizerError(f"Unexpected error in LLM request: {e}")
    
    def _create_fallback_summary(self, messages: List[Msg]) -> str:
        """
        Create a basic fallback summary when LLM is unavailable.
        
        Args:
            messages: List of messages to summarize
            
        Returns:
            str: Basic fallback summary
        """
        if not messages:
            return "Empty conversation"
        
        # Count messages by role
        user_count = sum(1 for msg in messages if msg.role == 'user')
        assistant_count = sum(1 for msg in messages if msg.role == 'assistant')
        
        # Get the last user message for context
        last_user_msg = None
        for msg in reversed(messages):
            if msg.role == 'user':
                last_user_msg = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                break
        
        # Create basic summary
        summary_parts = [
            f"• Conversation with {user_count} user messages and {assistant_count} assistant responses"
        ]
        
        if last_user_msg:
            summary_parts.append(f"• Last user message: {last_user_msg}")
        
        summary_parts.append("• Summary generated in fallback mode due to LLM unavailability")
        
        return "\n".join(summary_parts)
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"Summarizer(model={self.config.embed_model})"