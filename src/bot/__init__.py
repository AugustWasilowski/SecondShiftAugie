"""
Bot module for VoxCPM TTS Integration.

This module contains the Discord bot components including:
- DiscordBotManager: Handles Discord bot lifecycle and voice operations
- MessageRouter: Routes messages and coordinates text/voice responses
- Configuration classes for bot setup
"""

from .discord_manager import DiscordBotManager
from .message_router import MessageRouter, MessageResponse, CommandResponse, ChatResponse
from .config import BotConfig

__all__ = [
    'DiscordBotManager',
    'MessageRouter', 
    'MessageResponse',
    'CommandResponse',
    'ChatResponse',
    'BotConfig'
]