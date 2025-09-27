"""
Discord bot manager for handling voice channel operations and bot lifecycle.
"""

import asyncio
import logging
import os
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
        self.bot: Optional[commands.Bot] = None
        self.voice_client: Optional[nextcord.VoiceClient] = None
        self._ready = False
        self._logger = logging.getLogger(__name__)
        
        # Initialize bot with intents
        intents = nextcord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        self.bot = commands.Bot(
            command_prefix=config.command_prefix,
            intents=intents,
            help_command=None  # We'll use our custom help command
        )
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
        """Join a voice channel with comprehensive error handling.
        
        Implements graceful handling of Discord voice channel connection errors.
        Requirements 4.4: Handle Discord voice channel connection errors gracefully.
        
        Args:
            channel_id: ID of the voice channel to join
            
        Returns:
            bool: True if successfully joined, False otherwise
        """
        if not self.is_ready():
            self._logger.error("Bot is not ready - cannot join voice channel")
            return False
        
        try:
            # Get the voice channel with validation
            channel = self.bot.get_channel(channel_id)
            if not channel:
                self._logger.error(f"Voice channel {channel_id} not found - may have been deleted or bot lacks access")
                return False
                
            if not isinstance(channel, nextcord.VoiceChannel):
                self._logger.error(f"Channel {channel_id} is not a voice channel (type: {type(channel).__name__})")
                return False
            
            # Check bot permissions
            try:
                permissions = channel.permissions_for(channel.guild.me)
                if not permissions.connect:
                    self._logger.error(f"Bot lacks CONNECT permission for voice channel: {channel.name}")
                    return False
                if not permissions.speak:
                    self._logger.warning(f"Bot lacks SPEAK permission for voice channel: {channel.name}")
                    # Continue anyway as we might still be able to connect
                    
            except Exception as perm_error:
                self._logger.warning(f"Could not check permissions for voice channel: {perm_error}")
                # Continue anyway and let the connection attempt reveal permission issues
            
            # Check if channel is full
            if channel.user_limit and len(channel.members) >= channel.user_limit:
                # Check if bot has permission to bypass user limit
                try:
                    permissions = channel.permissions_for(channel.guild.me)
                    if not permissions.move_members:  # This permission allows bypassing user limits
                        self._logger.error(f"Voice channel {channel.name} is full ({len(channel.members)}/{channel.user_limit})")
                        return False
                except:
                    pass  # If we can't check, try anyway
            
            # Disconnect from current voice channel if connected
            if self.voice_client:
                try:
                    await asyncio.wait_for(self.voice_client.disconnect(), timeout=5.0)
                    self._logger.info("Disconnected from previous voice channel")
                except asyncio.TimeoutError:
                    self._logger.warning("Timeout disconnecting from previous voice channel")
                    self.voice_client = None
                except Exception as disconnect_error:
                    self._logger.warning(f"Error disconnecting from previous voice channel: {disconnect_error}")
                    self.voice_client = None
            
            # Connect to the new voice channel with timeout
            try:
                self._logger.info(f"Attempting to connect to voice channel: {channel.name} (ID: {channel_id})")
                self.voice_client = await asyncio.wait_for(
                    channel.connect(timeout=10.0),
                    timeout=15.0
                )
                
                # Verify connection was successful
                if not self.voice_client or not self.voice_client.is_connected():
                    self._logger.error("Voice connection established but client reports not connected")
                    return False
                
                self._logger.info(f"Successfully joined voice channel: {channel.name}")
                return True
                
            except asyncio.TimeoutError:
                self._logger.error(f"Timeout connecting to voice channel {channel.name} - connection took too long")
                return False
                
            except nextcord.ClientException as client_error:
                self._logger.error(f"Discord client error joining voice channel: {client_error}")
                error_str = str(client_error).lower()
                
                if "already connected" in error_str:
                    self._logger.error("Bot is already connected to a voice channel")
                elif "permission" in error_str or "forbidden" in error_str:
                    self._logger.error("Bot lacks permission to join this voice channel")
                elif "channel full" in error_str:
                    self._logger.error("Voice channel is full")
                else:
                    self._logger.error("Unknown Discord client error")
                
                return False
                
            except nextcord.opus.OpusNotLoaded as opus_error:
                self._logger.error(f"Opus codec not loaded - voice functionality unavailable: {opus_error}")
                self._logger.error("Install opus codec or check Discord.py voice dependencies")
                return False
                
            except Exception as connect_error:
                self._logger.error(f"Unexpected error connecting to voice channel: {connect_error}")
                error_str = str(connect_error).lower()
                
                if "network" in error_str or "connection" in error_str:
                    self._logger.error("Network connectivity issue - check internet connection")
                elif "rate limit" in error_str:
                    self._logger.error("Rate limited by Discord - try again later")
                
                return False
            
        except Exception as e:
            self._logger.error(f"Unexpected error in join_voice_channel: {e}")
            return False
    
    async def leave_voice_channel(self):
        """Leave the current voice channel with comprehensive error handling.
        
        Requirements 4.4: Handle Discord voice channel connection errors gracefully.
        """
        if not self.voice_client:
            self._logger.debug("No voice client to disconnect")
            return
        
        try:
            channel_name = "unknown"
            try:
                if self.voice_client.channel:
                    channel_name = self.voice_client.channel.name
            except:
                pass
            
            self._logger.info(f"Leaving voice channel: {channel_name}")
            
            # Stop any playing audio first
            try:
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                    self._logger.debug("Stopped audio playback before disconnecting")
            except Exception as stop_error:
                self._logger.warning(f"Error stopping audio before disconnect: {stop_error}")
            
            # Disconnect with timeout
            try:
                await asyncio.wait_for(self.voice_client.disconnect(), timeout=5.0)
                self._logger.info(f"Successfully left voice channel: {channel_name}")
                
            except asyncio.TimeoutError:
                self._logger.warning("Timeout leaving voice channel - forcing cleanup")
                # Force cleanup even if disconnect timed out
                
            except nextcord.ClientException as client_error:
                self._logger.warning(f"Discord client error leaving voice channel: {client_error}")
                # Continue with cleanup
                
            except Exception as disconnect_error:
                self._logger.error(f"Error disconnecting from voice channel: {disconnect_error}")
                # Continue with cleanup
                
        except Exception as e:
            self._logger.error(f"Unexpected error leaving voice channel: {e}")
            
        finally:
            # Always clean up the voice client reference
            self.voice_client = None
            self._logger.debug("Voice client reference cleared")
    
    async def play_audio(self, audio_path: str) -> bool:
        """Play an audio file in the current voice channel with comprehensive error handling.
        
        Requirements 4.4: Handle Discord voice channel connection errors gracefully.
        
        Args:
            audio_path: Path to the audio file to play
            
        Returns:
            bool: True if audio started playing, False otherwise
        """
        if not self.is_in_voice_channel():
            self._logger.error("Not connected to a voice channel - cannot play audio")
            return False
        
        # Validate audio file exists and is accessible
        if not os.path.exists(audio_path):
            self._logger.error(f"Audio file not found: {audio_path}")
            return False
        
        try:
            # Check file size and format
            file_size = os.path.getsize(audio_path)
            if file_size == 0:
                self._logger.error(f"Audio file is empty: {audio_path}")
                return False
            
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                self._logger.warning(f"Audio file is very large ({file_size / 1024 / 1024:.1f}MB): {audio_path}")
            
        except Exception as file_error:
            self._logger.error(f"Error checking audio file: {file_error}")
            return False
        
        try:
            # Verify voice client is still valid
            if not self.voice_client or not self.voice_client.is_connected():
                self._logger.error("Voice client is no longer connected")
                return False
            
            # Stop any currently playing audio with timeout
            if self.voice_client.is_playing():
                try:
                    self.voice_client.stop()
                    # Wait a moment for stop to take effect
                    await asyncio.sleep(0.1)
                    self._logger.debug("Stopped previous audio playback")
                except Exception as stop_error:
                    self._logger.warning(f"Error stopping previous audio: {stop_error}")
            
            # Create audio source with error handling
            try:
                # Use FFmpeg options for better compatibility and error handling
                ffmpeg_options = {
                    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    'options': '-vn -filter:a "volume=0.8"'  # Normalize volume
                }
                
                audio_source = nextcord.FFmpegPCMAudio(
                    audio_path,
                    **ffmpeg_options
                )
                
            except Exception as source_error:
                self._logger.error(f"Failed to create audio source: {source_error}")
                
                # Try fallback without options
                try:
                    audio_source = nextcord.FFmpegPCMAudio(audio_path)
                    self._logger.info("Created audio source with fallback method")
                except Exception as fallback_error:
                    self._logger.error(f"Fallback audio source creation failed: {fallback_error}")
                    return False
            
            # Play audio with error callback
            def after_playing(error):
                if error:
                    self._logger.error(f"Audio playback error: {error}")
                else:
                    self._logger.debug(f"Audio playback completed: {audio_path}")
            
            try:
                self.voice_client.play(audio_source, after=after_playing)
                
                # Verify playback started
                if not self.voice_client.is_playing():
                    self._logger.error("Audio playback did not start")
                    return False
                
                self._logger.info(f"Started playing audio: {os.path.basename(audio_path)}")
                return True
                
            except nextcord.ClientException as client_error:
                self._logger.error(f"Discord client error playing audio: {client_error}")
                error_str = str(client_error).lower()
                
                if "already playing" in error_str:
                    self._logger.error("Audio is already playing")
                elif "not connected" in error_str:
                    self._logger.error("Voice client is not connected")
                elif "source" in error_str:
                    self._logger.error("Invalid audio source")
                
                return False
                
            except Exception as play_error:
                self._logger.error(f"Unexpected error starting audio playback: {play_error}")
                return False
            
        except Exception as e:
            self._logger.error(f"Unexpected error in play_audio: {e}")
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