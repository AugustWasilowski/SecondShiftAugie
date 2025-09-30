"""
Embedding client for Ollama integration.

This module implements the EmbeddingClient class that interfaces with Ollama
for generating text embeddings with retry logic, timeout handling, and health checks.

Requirements addressed:
- 6.2: Embedding generation with acceptable performance
- 5.5: Error handling with graceful degradation
"""

import asyncio
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import aiohttp
import json

from .config import MemoryConfig


logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Exception raised when embedding operations fail."""
    pass


class OllamaConnectionError(EmbeddingError):
    """Exception raised when Ollama connection fails."""
    pass


class EmbeddingTimeoutError(EmbeddingError):
    """Exception raised when embedding operations timeout."""
    pass


@dataclass
class EmbeddingResponse:
    """Response from Ollama embedding API."""
    embedding: List[float]
    model: str
    prompt_eval_count: Optional[int] = None
    
    def __post_init__(self):
        """Validate embedding response."""
        if not self.embedding:
            raise ValueError("Embedding cannot be empty")
        if not all(isinstance(x, (int, float)) for x in self.embedding):
            raise ValueError("Embedding must contain only numeric values")
        if not self.model:
            raise ValueError("Model name cannot be empty")


class EmbeddingClient:
    """
    Ollama embedding client with retry logic and error handling.
    
    Provides async methods for generating text embeddings using Ollama's API
    with built-in retry logic, timeout handling, and health checks.
    """
    
    def __init__(self, config: MemoryConfig):
        """
        Initialize the embedding client.
        
        Args:
            config: Memory configuration containing Ollama settings
        """
        self.config = config
        self.base_url = config.embed_ollama_url.rstrip('/')
        self.model = config.embed_model
        
        # Retry configuration
        self.max_retries = 3
        self.base_delay = 1.0  # Base delay for exponential backoff
        self.max_delay = 30.0  # Maximum delay between retries
        self.timeout = 30.0    # Request timeout in seconds
        
        # Connection session (will be created lazily)
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"Initialized EmbeddingClient for {self.base_url} with model {self.model}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_session(self) -> None:
        """Ensure HTTP session is created."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'Content-Type': 'application/json'}
            )
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def health_check(self) -> bool:
        """
        Check if Ollama is available and responsive.
        
        Returns:
            bool: True if Ollama is healthy, False otherwise
        """
        try:
            await self._ensure_session()
            
            # Try to get the list of available models
            url = f"{self.base_url}/api/tags"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get('models', [])
                    
                    # Check if our configured model is available
                    model_names = [model.get('name', '') for model in models]
                    
                    # Check for exact match or with :latest suffix
                    model_available = (self.model in model_names or 
                                     f"{self.model}:latest" in model_names or
                                     any(name.startswith(f"{self.model}:") for name in model_names))
                    
                    if model_available:
                        logger.debug(f"Health check passed: model {self.model} is available")
                        return True
                    else:
                        logger.warning(f"Health check warning: model {self.model} not found in available models: {model_names}")
                        # Still return True as Ollama is responsive, model might be pullable
                        return True
                else:
                    logger.warning(f"Health check failed: HTTP {response.status}")
                    return False
                    
        except asyncio.TimeoutError:
            logger.warning("Health check failed: timeout")
            return False
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List[float]: Embedding vector
            
        Raises:
            EmbeddingError: If embedding generation fails
            EmbeddingTimeoutError: If request times out
            OllamaConnectionError: If Ollama is unreachable
        """
        if not text or not text.strip():
            raise EmbeddingError("Text cannot be empty")
        
        start_time = time.time()
        
        try:
            response = await self._embed_with_retry(text)
            
            elapsed = time.time() - start_time
            logger.debug(f"Generated embedding for text ({len(text)} chars) in {elapsed:.3f}s")
            
            return response.embedding
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to generate embedding after {elapsed:.3f}s: {e}")
            raise
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
            
        Raises:
            EmbeddingError: If embedding generation fails
            EmbeddingTimeoutError: If request times out
            OllamaConnectionError: If Ollama is unreachable
        """
        if not texts:
            return []
        
        # Filter out empty texts
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            raise EmbeddingError("No valid texts to embed")
        
        start_time = time.time()
        
        try:
            # Process texts concurrently with semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
            
            async def embed_single(text: str) -> List[float]:
                async with semaphore:
                    return await self.embed_text(text)
            
            # Create tasks for all texts
            tasks = [embed_single(text) for text in valid_texts]
            embeddings = await asyncio.gather(*tasks)
            
            elapsed = time.time() - start_time
            logger.debug(f"Generated {len(embeddings)} embeddings in {elapsed:.3f}s")
            
            return embeddings
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to generate batch embeddings after {elapsed:.3f}s: {e}")
            raise
    
    async def _embed_with_retry(self, text: str) -> EmbeddingResponse:
        """
        Generate embedding with retry logic.
        
        Args:
            text: Text to embed
            
        Returns:
            EmbeddingResponse: Embedding response from Ollama
            
        Raises:
            EmbeddingError: If all retries fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await self._make_embedding_request(text)
                
            except asyncio.TimeoutError as e:
                last_exception = EmbeddingTimeoutError(f"Request timed out after {self.timeout}s")
                logger.warning(f"Embedding request timeout (attempt {attempt + 1}/{self.max_retries + 1})")
                
            except aiohttp.ClientConnectorError as e:
                last_exception = OllamaConnectionError(f"Cannot connect to Ollama at {self.base_url}: {e}")
                logger.warning(f"Ollama connection failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                
            except aiohttp.ClientResponseError as e:
                if e.status >= 500:
                    # Server error - retry
                    last_exception = EmbeddingError(f"Ollama server error: HTTP {e.status}")
                    logger.warning(f"Ollama server error (attempt {attempt + 1}/{self.max_retries + 1}): HTTP {e.status}")
                else:
                    # Client error - don't retry
                    raise EmbeddingError(f"Ollama client error: HTTP {e.status} - {e.message}")
                    
            except Exception as e:
                last_exception = EmbeddingError(f"Unexpected error: {e}")
                logger.warning(f"Unexpected embedding error (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
            
            # Calculate delay for next retry (exponential backoff with jitter)
            if attempt < self.max_retries:
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                # Add jitter to prevent thundering herd
                jitter = delay * 0.1 * (0.5 - asyncio.get_event_loop().time() % 1)
                delay += jitter
                
                logger.debug(f"Retrying embedding request in {delay:.2f}s")
                await asyncio.sleep(delay)
        
        # All retries failed
        if last_exception:
            raise last_exception
        else:
            raise EmbeddingError("All embedding retries failed")
    
    async def _make_embedding_request(self, text: str) -> EmbeddingResponse:
        """
        Make a single embedding request to Ollama.
        
        Args:
            text: Text to embed
            
        Returns:
            EmbeddingResponse: Embedding response
            
        Raises:
            Various aiohttp exceptions
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        async with self._session.post(url, json=payload) as response:
            response.raise_for_status()
            
            data = await response.json()
            
            # Validate response structure
            if 'embedding' not in data:
                raise EmbeddingError("Invalid response: missing 'embedding' field")
            
            embedding = data['embedding']
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingError("Invalid response: 'embedding' must be a non-empty list")
            
            return EmbeddingResponse(
                embedding=embedding,
                model=data.get('model', self.model),
                prompt_eval_count=data.get('prompt_eval_count')
            )
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the configured embedding model.
        
        Returns:
            dict: Model configuration information
        """
        return {
            "model": self.model,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "max_delay": self.max_delay
        }
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"EmbeddingClient(model={self.model}, url={self.base_url})"