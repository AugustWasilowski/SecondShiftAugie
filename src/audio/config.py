"""
Configuration classes for audio management.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioConfig:
    """Configuration for audio file management."""
    
    save_path: str = "./temp_audio"
    cleanup_hours: int = 24
    max_file_size_mb: int = 50
    audio_format: str = "wav"
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.cleanup_hours < 0:
            raise ValueError("cleanup_hours must be non-negative")
        if self.max_file_size_mb <= 0:
            raise ValueError("max_file_size_mb must be positive")
        if not self.save_path:
            raise ValueError("save_path cannot be empty")