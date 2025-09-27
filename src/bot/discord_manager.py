"""
Discord bot manager for handling voice channel operations and bot lifecycle.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import nextcord
from nextcord.ext import commands

from .config import BotConfig


class DiscordBotManager:
    """Manages Discord bot lifecycle and voice channel operations."""
    
    def __init__(self, config: BotConfig):
        """Initialize the Discord bot manager.
        
        Args:
            config: Bot configuration containing token and channel settings
        """
        self.config = config
        self.bot: Optional[nextcord.Client] = None
        self.voice_client: Optional[nextcord.VoiceClient] = None
        self._ready = False
        self._logger = logging.getLogger(__name__)
        
        # Initialize bot with intents
        intents = nextcord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        self.bot = nextcord.Client(intents=intents)
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """Set up Discord bot event handlers."""
        
        @self.bot.event
        async def on_ready():
            """Handle bot ready event."""
            self._ready = True
            self._logger.info(f"Bot logged in as {self.bot.user}")
            
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """Handle voice state updates."""
            # Log voice state changes for debugging
            if member == self.bot.user:
                if before.channel != after.channel:
                    self._logger.info(f"Bot voice state changed: {before.channel} -> {after.channel}")
    
    async def start(self):
        """Start the Discord bot.
        
        Returns:
            bool: True if bot started successfully, False otherwise
        """
        try:
            await self.bot.start(self.config.token)
            return True
        except Exception as e:
            self._logger.error(f"Failed to start bot: {e}")
            return False
    
    async def stop(self):
        """Stop the Discord bot and cleanup resources."""
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        
        if self.bot:
            await self.bot.close()
        
        self._ready = False
    
    def is_ready(self) -> bool:
        """Check if the bot is ready and connected.
        
        Returns:
            bool: True if bot is ready, False otherwise
        """
        return self._ready and self.bot is not None
    
    def is_in_voice_channel(self) -> bool:
        """Check if the bot is currently in a voice channel.
        
        Returns:
            bool: True if in voice channel, False otherwise
        """
        return self.voice_client is not None and self.voice_client.is_connected()
    
    def is_playing_audio(self) -> bool:
        """Check if the bot is currently playing audio.
        
        Returns:
            bool: True if playing audio, False otherwise
        """
        return (self.voice_client is not None and 
                self.voice_client.is_playing())
    
    async def join_voice_channel(self, channel_id: int) -> bool:
        """Join a voice channel.
        
        Args:
            channel_id: ID of the voice channel to join
            
        Returns:
            bool: True if successfully joined, False otherwise
        """
        if not self.is_ready():
            self._logger.error("Bot is not ready")
            return False
        
        try:
            # Get the voice channel
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, nextcord.VoiceChannel):
                self._logger.error(f"Voice channel {channel_id} not found or invalid")
                return False
            
            # Disconnect from current voice channel if connected
            if self.voice_client:
                await self.voice_client.disconnect()
            
            # Connect to the new voice channel
            self.voice_client = await channel.connect()
            self._logger.info(f"Joined voice channel: {channel.name}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to join voice channel {channel_id}: {e}")
            return False
    
    async def leave_voice_channel(self):
        """Leave the current voice channel."""
        if self.voice_client:
            try:
                await self.voice_client.disconnect()
                self._logger.info("Left voice channel")
            except Exception as e:
                self._logger.error(f"Error leaving voice channel: {e}")
            finally:
                self.voice_client = None
    
    async def play_audio(self, audio_path: str) -> bool:
        """Play an audio file in the current voice channel.
        
        Args:
            audio_path: Path to the audio file to play
            
        Returns:
            bool: True if audio started playing, False otherwise
        """
        if not self.is_in_voice_channel():
            self._logger.error("Not connected to a voice channel")
            return False
        
        try:
            # Stop any currently playing audio
            if self.voice_client.is_playing():
                self.voice_client.stop()
            
            # Create audio source and play
            audio_source = nextcord.FFmpegPCMAudio(audio_path)
            self.voice_client.play(audio_source)
            
            self._logger.info(f"Started playing audio: {audio_path}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to play audio {audio_path}: {e}")
            return False
    
    def stop_audio(self):
        """Stop any currently playing audio."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            self._logger.info("Stopped audio playback")
    
    def get_voice_channel_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current voice channel.
        
        Returns:
            Dict with channel info if connected, None otherwise
        """
        if not self.is_in_voice_channel():
            return None
        
        channel = self.voice_client.channel
        return {
            "id": channel.id,
            "name": channel.name,
            "member_count": len(channel.members),
            "bitrate": channel.bitrate,
            "user_limit": channel.user_limit
        }
    
    def get_bot_user(self) -> Optional[nextcord.User]:
        """Get the bot user object.
        
        Returns:
            Bot user if ready, None otherwise
        """
        return self.bot.user if self.is_ready() else None