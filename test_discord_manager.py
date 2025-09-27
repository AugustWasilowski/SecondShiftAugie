"""
Test script for Discord Bot Manager functionality.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bot.discord_manager import DiscordBotManager
from bot.config import BotConfig


async def test_discord_manager():
    """Test Discord bot manager basic functionality."""
    
    # Create test configuration
    config = BotConfig(
        token="test_token",
        channel_id=123456789,
        voice_channel_id=987654321,
        save_path="./temp_audio"
    )
    
    # Initialize bot manager
    bot_manager = DiscordBotManager(config)
    
    # Test initialization
    print("✓ DiscordBotManager initialized successfully")
    
    # Test configuration validation
    assert config.token == "test_token"
    assert config.channel_id == 123456789
    assert config.voice_channel_id == 987654321
    print("✓ Configuration validation passed")
    
    # Test initial state
    assert not bot_manager.is_ready()
    assert not bot_manager.is_in_voice_channel()
    assert not bot_manager.is_playing_audio()
    print("✓ Initial state checks passed")
    
    # Test voice channel info when not connected
    assert bot_manager.get_voice_channel_info() is None
    print("✓ Voice channel info returns None when not connected")
    
    print("\n✅ All Discord bot manager tests passed!")


def test_config_validation():
    """Test configuration validation."""
    
    # Test valid config
    config = BotConfig(
        token="valid_token",
        channel_id=123456789
    )
    print("✓ Valid configuration created successfully")
    
    # Test invalid token
    try:
        BotConfig(token="", channel_id=123456789)
        assert False, "Should have raised ValueError for empty token"
    except ValueError:
        print("✓ Empty token validation works")
    
    # Test invalid channel ID
    try:
        BotConfig(token="valid_token", channel_id=0)
        assert False, "Should have raised ValueError for invalid channel ID"
    except ValueError:
        print("✓ Invalid channel ID validation works")
    
    # Test invalid voice channel ID
    try:
        BotConfig(token="valid_token", channel_id=123456789, voice_channel_id=-1)
        assert False, "Should have raised ValueError for invalid voice channel ID"
    except ValueError:
        print("✓ Invalid voice channel ID validation works")


if __name__ == "__main__":
    print("Testing Discord Bot Manager...")
    print("=" * 50)
    
    # Test configuration validation
    test_config_validation()
    print()
    
    # Test async functionality
    asyncio.run(test_discord_manager())