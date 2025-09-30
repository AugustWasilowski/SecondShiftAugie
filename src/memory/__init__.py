"""Memory system for SecondShiftAugie bot."""

from .models import ThreadCtx, Msg, NewMemory, MemoryHit
from .config import MemoryConfig, MemoryConfigError
from .embedding_client import EmbeddingClient, EmbeddingError, OllamaConnectionError, EmbeddingTimeoutError

__all__ = [
    'ThreadCtx', 'Msg', 'NewMemory', 'MemoryHit', 
    'MemoryConfig', 'MemoryConfigError',
    'EmbeddingClient', 'EmbeddingError', 'OllamaConnectionError', 'EmbeddingTimeoutError'
]