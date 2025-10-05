"""
Memory system configuration with environment variable parsing.

This module implements configuration loading and validation for the memory system,
including database settings, embedding configuration, and memory behavior settings.

Requirements addressed:
- 4.1: Configurable memory system with per-guild scoping
- 4.3: Configuration validation and default values
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path


logger = logging.getLogger(__name__)


class MemoryConfigError(Exception):
    """Exception raised when memory configuration is invalid."""
    pass


@dataclass
class MemoryConfig:
    """
    Configuration for the memory system.
    
    Handles all memory-related configuration including database connection,
    embedding settings, STM/LTM behavior, and retrieval parameters.
    """
    
    # Database Configuration
    pg_dsn: str
    pg_pool_min: int = 2
    pg_pool_max: int = 10
    
    # Embedding Configuration
    embed_model: str = "nomic-embed-text"
    embed_ollama_url: str = "http://localhost:11434"
    
    # STM Behavior
    stm_max_tokens: int = 2400
    stm_keep_last: int = 2
    
    # Retrieval Configuration
    retrieve_top_k: int = 6
    recency_window_days: int = 7
    boost_similarity: float = 0.7
    boost_recency: float = 0.2
    boost_importance: float = 0.1
    
    # Policy Configuration
    memory_min_importance: int = 2
    memory_export_dir: str = "./exports"
    memory_enabled: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_config()
    
    def _validate_config(self) -> None:
        """
        Validate all configuration values.
        
        Raises:
            MemoryConfigError: If any configuration value is invalid
        """
        errors = []
        
        # Validate database configuration
        if not self.pg_dsn or not self.pg_dsn.strip():
            errors.append("pg_dsn cannot be empty")
        elif not self.pg_dsn.startswith(('postgres://', 'postgresql://')):
            errors.append("pg_dsn must start with 'postgres://' or 'postgresql://'")
        
        if self.pg_pool_min < 1:
            errors.append("pg_pool_min must be at least 1")
        if self.pg_pool_max < self.pg_pool_min:
            errors.append("pg_pool_max must be >= pg_pool_min")
        if self.pg_pool_max > 50:
            errors.append("pg_pool_max should not exceed 50 for typical deployments")
        
        # Validate embedding configuration
        if not self.embed_model or not self.embed_model.strip():
            errors.append("embed_model cannot be empty")
        
        if not self.embed_ollama_url or not self.embed_ollama_url.strip():
            errors.append("embed_ollama_url cannot be empty")
        elif not self.embed_ollama_url.startswith(('http://', 'https://')):
            errors.append("embed_ollama_url must start with 'http://' or 'https://'")
        
        # Validate STM configuration
        if self.stm_max_tokens < 100:
            errors.append("stm_max_tokens must be at least 100")
        elif self.stm_max_tokens > 10000:
            errors.append("stm_max_tokens should not exceed 10000 for performance")
        
        if self.stm_keep_last < 1:
            errors.append("stm_keep_last must be at least 1")
        elif self.stm_keep_last > 10:
            errors.append("stm_keep_last should not exceed 10 for typical use")
        
        # Validate retrieval configuration
        if self.retrieve_top_k < 1:
            errors.append("retrieve_top_k must be at least 1")
        elif self.retrieve_top_k > 50:
            errors.append("retrieve_top_k should not exceed 50 for performance")
        
        if self.recency_window_days < 1:
            errors.append("recency_window_days must be at least 1")
        elif self.recency_window_days > 365:
            errors.append("recency_window_days should not exceed 365")
        
        # Validate boost weights (should sum to ~1.0)
        total_boost = self.boost_similarity + self.boost_recency + self.boost_importance
        if abs(total_boost - 1.0) > 0.1:
            errors.append(f"Boost weights should sum to ~1.0, got {total_boost:.3f}")
        
        if not (0.0 <= self.boost_similarity <= 1.0):
            errors.append("boost_similarity must be between 0.0 and 1.0")
        if not (0.0 <= self.boost_recency <= 1.0):
            errors.append("boost_recency must be between 0.0 and 1.0")
        if not (0.0 <= self.boost_importance <= 1.0):
            errors.append("boost_importance must be between 0.0 and 1.0")
        
        # Validate policy configuration
        if not (1 <= self.memory_min_importance <= 5):
            errors.append("memory_min_importance must be between 1 and 5")
        
        if not self.memory_export_dir or not self.memory_export_dir.strip():
            errors.append("memory_export_dir cannot be empty")
        
        if errors:
            raise MemoryConfigError(f"Memory configuration validation failed: {'; '.join(errors)}")
    
    @classmethod
    def from_environment(cls, env_prefix: str = "MEMORY_") -> "MemoryConfig":
        """
        Create MemoryConfig from environment variables.
        
        Args:
            env_prefix: Prefix for environment variables (default: "MEMORY_")
            
        Returns:
            MemoryConfig: Configured memory settings
            
        Raises:
            MemoryConfigError: If required configuration is missing or invalid
        """
        try:
            # Database Configuration
            pg_dsn = os.getenv("PG_DSN")
            if not pg_dsn:
                raise MemoryConfigError("PG_DSN environment variable is required")
            
            pg_pool_min = int(os.getenv("PG_POOL_MIN", "2"))
            pg_pool_max = int(os.getenv("PG_POOL_MAX", "10"))
            
            # Embedding Configuration
            embed_model = os.getenv("EMBED_MODEL", "nomic-embed-text")
            embed_ollama_url = os.getenv("EMBED_OLLAMA_URL", "http://localhost:11434")
            
            # STM Behavior
            stm_max_tokens = int(os.getenv("STM_MAX_TOKENS", "2400"))
            stm_keep_last = int(os.getenv("STM_KEEP_LAST", "2"))
            
            # Retrieval Configuration
            retrieve_top_k = int(os.getenv("RETRIEVE_TOP_K", "6"))
            recency_window_days = int(os.getenv("RECENCY_WINDOW_DAYS", "7"))
            boost_similarity = float(os.getenv("BOOST_SIMILARITY", "0.7"))
            boost_recency = float(os.getenv("BOOST_RECENCY", "0.2"))
            boost_importance = float(os.getenv("BOOST_IMPORTANCE", "0.1"))
            
            # Policy Configuration
            memory_min_importance = int(os.getenv("MEMORY_MIN_IMPORTANCE", "2"))
            memory_export_dir = os.getenv("MEMORY_EXPORT_DIR", "./exports")
            memory_enabled = os.getenv("MEMORY_ENABLED", "true").lower() in ("true", "1", "yes", "on")
            
            return cls(
                pg_dsn=pg_dsn,
                pg_pool_min=pg_pool_min,
                pg_pool_max=pg_pool_max,
                embed_model=embed_model,
                embed_ollama_url=embed_ollama_url,
                stm_max_tokens=stm_max_tokens,
                stm_keep_last=stm_keep_last,
                retrieve_top_k=retrieve_top_k,
                recency_window_days=recency_window_days,
                boost_similarity=boost_similarity,
                boost_recency=boost_recency,
                boost_importance=boost_importance,
                memory_min_importance=memory_min_importance,
                memory_export_dir=memory_export_dir,
                memory_enabled=memory_enabled
            )
            
        except ValueError as e:
            raise MemoryConfigError(f"Invalid environment variable type: {e}")
        except Exception as e:
            raise MemoryConfigError(f"Error loading memory configuration: {e}")
    
    def get_database_config(self) -> Dict[str, Any]:
        """
        Get database configuration dictionary.
        
        Returns:
            dict: Database configuration for connection pooling
        """
        return {
            "dsn": self.pg_dsn,
            "min_size": self.pg_pool_min,
            "max_size": self.pg_pool_max
        }
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """
        Get embedding configuration dictionary.
        
        Returns:
            dict: Embedding configuration for Ollama client
        """
        return {
            "model": self.embed_model,
            "base_url": self.embed_ollama_url
        }
    
    def get_retrieval_config(self) -> Dict[str, Any]:
        """
        Get retrieval configuration dictionary.
        
        Returns:
            dict: Retrieval configuration for memory search
        """
        return {
            "top_k": self.retrieve_top_k,
            "recency_window_days": self.recency_window_days,
            "similarity_weight": self.boost_similarity,
            "recency_weight": self.boost_recency,
            "importance_weight": self.boost_importance
        }
    
    def ensure_export_directory(self) -> Path:
        """
        Ensure the memory export directory exists.
        
        Returns:
            Path: Path to the export directory
            
        Raises:
            MemoryConfigError: If directory cannot be created
        """
        try:
            export_path = Path(self.memory_export_dir)
            export_path.mkdir(parents=True, exist_ok=True)
            return export_path
        except Exception as e:
            raise MemoryConfigError(f"Cannot create export directory {self.memory_export_dir}: {e}")
    
    def is_feature_enabled(self, feature: str) -> bool:
        """
        Check if a memory feature is enabled.
        
        Args:
            feature: Feature name to check (e.g., 'stm', 'ltm', 'embeddings', 'export')
            
        Returns:
            bool: True if feature is enabled
        """
        if not self.memory_enabled:
            return False
        
        # Feature-specific checks
        feature_checks = {
            'stm': lambda: True,  # STM always available if memory enabled
            'ltm': lambda: bool(self.pg_dsn and self.embed_ollama_url),
            'embeddings': lambda: bool(self.embed_ollama_url and self.embed_model),
            'export': lambda: bool(self.memory_export_dir),
            'summarization': lambda: True,  # Available if memory enabled
            'vector_search': lambda: bool(self.pg_dsn and self.embed_ollama_url),
        }
        
        check_func = feature_checks.get(feature.lower())
        if check_func:
            return check_func()
        
        # Default: enabled if memory system is enabled
        return True
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the configuration for validation/debugging.
        
        Returns:
            dict: Configuration summary (without sensitive data)
        """
        return {
            "memory_enabled": self.memory_enabled,
            "database_configured": bool(self.pg_dsn),
            "embedding_model": self.embed_model,
            "stm_max_tokens": self.stm_max_tokens,
            "retrieve_top_k": self.retrieve_top_k,
            "min_importance": self.memory_min_importance,
            "export_dir_exists": Path(self.memory_export_dir).exists()
        }
    
    def __str__(self) -> str:
        """String representation for logging (without sensitive data)."""
        return (f"MemoryConfig(enabled={self.memory_enabled}, "
                f"model={self.embed_model}, "
                f"stm_tokens={self.stm_max_tokens}, "
                f"top_k={self.retrieve_top_k})")