"""
Core data models for the memory system.

This module implements the core data structures used throughout the memory system,
including thread context, messages, and memory representations.

Requirements addressed:
- 4.1: Configurable memory system with per-guild scoping
- 4.3: Configuration validation and default values
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ThreadCtx:
    """
    Thread context for scoping memory operations.
    
    Provides the necessary context to scope memory operations to specific
    Discord threads (guild + channel + user combination).
    """
    guild_id: str
    channel_id: str
    user_id: str
    
    def __post_init__(self):
        """Validate thread context fields."""
        if not self.guild_id or not self.guild_id.strip():
            raise ValueError("guild_id cannot be empty")
        if not self.channel_id or not self.channel_id.strip():
            raise ValueError("channel_id cannot be empty")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id cannot be empty")
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"ThreadCtx(guild={self.guild_id}, channel={self.channel_id}, user={self.user_id})"


@dataclass
class Msg:
    """
    Message representation for STM operations.
    
    Represents a single message in the conversation context with role
    and optional token estimation for budget management.
    """
    role: Literal['user', 'assistant', 'system']
    content: str
    tokens: Optional[int] = None
    
    def __post_init__(self):
        """Validate message fields."""
        if self.role not in ('user', 'assistant', 'system'):
            raise ValueError(f"Invalid role: {self.role}. Must be 'user', 'assistant', or 'system'")
        if not self.content or not self.content.strip():
            raise ValueError("Message content cannot be empty")
        if self.tokens is not None and self.tokens < 0:
            raise ValueError("Token count cannot be negative")
    
    def estimate_tokens(self) -> int:
        """
        Estimate token count for the message if not already set.
        
        Uses a simple heuristic: ~4 characters per token for English text.
        This is a rough approximation and should be replaced with actual
        tokenizer calls for production use.
        
        Returns:
            int: Estimated token count
        """
        if self.tokens is not None:
            return self.tokens
        
        # Simple token estimation: ~4 characters per token
        # Add some overhead for role and formatting
        estimated = len(self.content) // 4 + 5
        return max(1, estimated)  # Minimum 1 token
    
    def __str__(self) -> str:
        """String representation for logging."""
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Msg(role={self.role}, tokens={self.estimate_tokens()}, content='{content_preview}')"


@dataclass
class NewMemory:
    """
    New memory item for LTM storage.
    
    Represents a memory item to be stored in long-term memory with
    categorization and importance scoring.
    """
    kind: Literal['episodic', 'semantic', 'entity', 'artifact']
    text: str
    importance: Literal[1, 2, 3, 4, 5]
    
    def __post_init__(self):
        """Validate memory fields."""
        valid_kinds = ('episodic', 'semantic', 'entity', 'artifact')
        if self.kind not in valid_kinds:
            raise ValueError(f"Invalid memory kind: {self.kind}. Must be one of {valid_kinds}")
        
        if not self.text or not self.text.strip():
            raise ValueError("Memory text cannot be empty")
        
        if self.importance not in (1, 2, 3, 4, 5):
            raise ValueError(f"Invalid importance: {self.importance}. Must be 1-5")
    
    def __str__(self) -> str:
        """String representation for logging."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"NewMemory(kind={self.kind}, importance={self.importance}, text='{text_preview}')"


@dataclass
class MemoryHit:
    """
    Memory retrieval result with scoring metadata.
    
    Represents a memory item retrieved from LTM with similarity,
    importance, and temporal metadata for ranking.
    """
    id: str
    text: str
    importance: int
    similarity: float
    created_at: str
    kind: Optional[str] = None
    
    def __post_init__(self):
        """Validate memory hit fields."""
        if not self.id or not self.id.strip():
            raise ValueError("Memory ID cannot be empty")
        
        if not self.text or not self.text.strip():
            raise ValueError("Memory text cannot be empty")
        
        if not isinstance(self.importance, int) or self.importance < 1 or self.importance > 5:
            raise ValueError(f"Invalid importance: {self.importance}. Must be integer 1-5")
        
        if not isinstance(self.similarity, (int, float)) or self.similarity < 0.0 or self.similarity > 1.0:
            raise ValueError(f"Invalid similarity: {self.similarity}. Must be float 0.0-1.0")
        
        if not self.created_at or not self.created_at.strip():
            raise ValueError("created_at cannot be empty")
    
    def get_combined_score(self, similarity_weight: float = 0.7, 
                          recency_weight: float = 0.2, 
                          importance_weight: float = 0.1) -> float:
        """
        Calculate combined relevance score.
        
        Args:
            similarity_weight: Weight for similarity score (default 0.7)
            recency_weight: Weight for recency score (default 0.2)
            importance_weight: Weight for importance score (default 0.1)
            
        Returns:
            float: Combined score for ranking
        """
        # Normalize importance to 0-1 scale
        importance_normalized = self.importance / 5.0
        
        # Simple recency calculation (would need actual datetime parsing in production)
        # For now, assume more recent items have higher recency
        recency_score = 0.5  # Placeholder - would calculate from created_at
        
        combined = (similarity_weight * self.similarity + 
                   recency_weight * recency_score + 
                   importance_weight * importance_normalized)
        
        return min(1.0, max(0.0, combined))  # Clamp to 0-1 range
    
    def __str__(self) -> str:
        """String representation for logging."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return (f"MemoryHit(id={self.id}, similarity={self.similarity:.3f}, "
                f"importance={self.importance}, text='{text_preview}')")