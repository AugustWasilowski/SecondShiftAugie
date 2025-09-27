"""
Configuration classes for Discord bot management.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BotConfig:
    """Configuration for Discord bot operations."""
    
    token: str
    channel_id: int
    voice_channel_id: Optional[int] = None
    save_path: str = "./temp_audio"
    command_prefix: str = "!"
    
    def __post_init__(self):
        """Validate configuration values."""
        if not self.token:
            raise ValueError("Bot token cannot be empty")
        if self.channel_id <= 0:
            raise ValueError("Channel ID must be positive")
        if self.voice_channel_id is not None and self.voice_channel_id <= 0:
            raise ValueError("Voice channel ID must be positive if provided")
        if not self.save_path:
            raise ValueError("Save path cannot be empty")