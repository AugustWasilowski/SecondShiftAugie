"""
Command system with voice integration for VoxCPM Discord bot.

Implements Discord bot commands that integrate with VoxCPM TTS functionality,
including voice channel management and audio playback commands.
"""

import logging
from typing import TYPE_CHECKING

import nextcord
from nextcord.ext import commands

if TYPE_CHECKING:
    from .discord_manager import DiscordBotManager
    from ..tts.voxcpm_engine import VoxCPMEngine
    from ..audio.audio_manager import AudioManager

logger = logging.getLogger(__name__)


class BotCommands:
    """Command handlers for Discord bot with VoxCPM integration."""
    
    def __init__(
        self, 
        bot_manager: "DiscordBotManager", 
        tts_engine: "VoxCPMEngine", 
        audio_manager: "AudioManager"
    ):
        """Initialize command system.
        
        Args:
            bot_manager: Discord bot manager instance
            tts_engine: VoxCPM TTS engine instance
            audio_manager: Audio file manager instance
        """
        self.bot_manager = bot_manager
        self.tts_engine = tts_engine
        self.audio_manager = audio_manager
        
        logger.info("BotCommands initialized")
    
    async def join_command(self, ctx: commands.Context) -> None:
        """Handle !join command to connect bot to user's voice channel.
        
        Requirement 3.1: WHEN a user calls !join command THEN the bot SHALL connect to the user's current voice channel
        Requirement 3.2: WHEN the bot joins a voice channel THEN the system SHALL play the existing greeting audio file
        
        Args:
            ctx: Discord command context
        """
        try:
            # Check if user is in a voice channel
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send("❌ You need to be in a voice channel for me to join!")
                return
            
            user_channel = ctx.author.voice.channel
            
            # Check if bot is already in the same voice channel
            if (self.bot_manager.is_in_voice_channel() and 
                self.bot_manager.voice_client.channel.id == user_channel.id):
                await ctx.send(f"✅ I'm already in {user_channel.name}!")
                return
            
            # Attempt to join the voice channel
            success = await self.bot_manager.join_voice_channel(user_channel.id)
            
            if success:
                await ctx.send(f"✅ Joined {user_channel.name}! I can now play voice responses.")
                
                # Play greeting audio if available (Requirement 3.2)
                greeting_files = [
                    "SecondShiftAugieReportingForDuty.mp3",
                    "GettingDownToBusiness.mp3"
                ]
                
                for greeting_file in greeting_files:
                    try:
                        import os
                        if os.path.exists(greeting_file):
                            await self.bot_manager.play_audio(greeting_file)
                            logger.info(f"Played greeting audio: {greeting_file}")
                            break
                    except Exception as e:
                        logger.warning(f"Could not play greeting audio {greeting_file}: {e}")
                        continue
                
            else:
                await ctx.send("❌ Failed to join voice channel. Please check my permissions.")
                
        except Exception as e:
            logger.error(f"Error in join command: {e}")
            await ctx.send("❌ An error occurred while trying to join the voice channel.")
    
    async def play_command(self, ctx: commands.Context) -> None:
        """Handle !play command to replay last generated audio.
        
        Requirement 3.4: WHEN a user calls !play command THEN the bot SHALL replay the last generated voice response
        
        Args:
            ctx: Discord command context
        """
        try:
            # Check if bot is in a voice channel
            if not self.bot_manager.is_in_voice_channel():
                await ctx.send("❌ I need to be in a voice channel to play audio. Use `!join` first!")
                return
            
            # Get last generated audio file
            last_audio_path = self.audio_manager.get_last_audio_path()
            
            if not last_audio_path:
                await ctx.send("❌ No audio to replay. Generate some voice responses first by mentioning me!")
                return
            
            # Play the last audio file
            success = await self.audio_manager.play_in_voice_channel(
                self.bot_manager, 
                last_audio_path
            )
            
            if success:
                await ctx.send("🔊 Replaying last voice response...")
                logger.info(f"Replayed audio: {last_audio_path}")
            else:
                await ctx.send("❌ Failed to play audio. The file might be corrupted or missing.")
                
        except Exception as e:
            logger.error(f"Error in play command: {e}")
            await ctx.send("❌ An error occurred while trying to play audio.")
    
    async def help_command(self, ctx: commands.Context) -> None:
        """Handle !help command with updated functionality description.
        
        Args:
            ctx: Discord command context
        """
        try:
            # Create embed with bot functionality
            embed = nextcord.Embed(
                title="🤖 SecondShiftAugie Bot Commands",
                description="Voice-enabled Discord bot with VoxCPM text-to-speech integration",
                color=0x00ff00
            )
            
            # Add command descriptions
            embed.add_field(
                name="🎤 Voice Commands",
                value=(
                    "`!join` - Join your current voice channel\n"
                    "`!play` - Replay the last generated voice response\n"
                    "`!leave` - Leave the current voice channel"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💬 Chat Features",
                value=(
                    "• Mention me (@SecondShiftAugie) for voice responses\n"
                    "• I'll generate speech using VoxCPM TTS\n"
                    "• Voice responses play automatically when I'm in a voice channel"
                ),
                inline=False
            )
            
            embed.add_field(
                name="ℹ️ Information Commands",
                value=(
                    "`!help` - Show this help message\n"
                    "`!status` - Check bot and TTS engine status"
                ),
                inline=False
            )
            
            # Add status information
            voice_status = "🟢 Connected" if self.bot_manager.is_in_voice_channel() else "🔴 Not connected"
            tts_status = "🟢 Ready" if self.tts_engine.is_ready() else "🔴 Not ready"
            
            embed.add_field(
                name="📊 Current Status",
                value=(
                    f"Voice Channel: {voice_status}\n"
                    f"TTS Engine: {tts_status}"
                ),
                inline=False
            )
            
            # Add footer with additional info
            embed.set_footer(
                text="💡 Tip: Join a voice channel and mention me to hear voice responses!"
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            # Fallback to simple text message if embed fails
            help_text = (
                "**SecondShiftAugie Bot Commands:**\n"
                "🎤 `!join` - Join your voice channel\n"
                "🔊 `!play` - Replay last voice response\n"
                "💬 Mention me for voice responses!\n"
                "ℹ️ `!help` - Show this message\n"
                "📊 `!status` - Check bot status"
            )
            await ctx.send(help_text)
    
    async def status_command(self, ctx: commands.Context) -> None:
        """Handle !status command to show bot and engine status.
        
        Args:
            ctx: Discord command context
        """
        try:
            # Gather status information
            bot_ready = self.bot_manager.is_ready()
            in_voice = self.bot_manager.is_in_voice_channel()
            tts_ready = self.tts_engine.is_ready()
            
            # Get voice channel info if connected
            voice_info = self.bot_manager.get_voice_channel_info()
            
            # Get audio storage info
            storage_info = self.audio_manager.get_storage_info()
            
            # Create status embed
            embed = nextcord.Embed(
                title="📊 Bot Status",
                color=0x00ff00 if (bot_ready and tts_ready) else 0xff9900
            )
            
            # Bot status
            bot_status = "🟢 Online" if bot_ready else "🔴 Offline"
            embed.add_field(name="Bot Status", value=bot_status, inline=True)
            
            # TTS Engine status
            tts_status = "🟢 Ready" if tts_ready else "🔴 Not Ready"
            embed.add_field(name="TTS Engine", value=tts_status, inline=True)
            
            # Voice channel status
            if in_voice and voice_info:
                voice_status = f"🟢 Connected to **{voice_info['name']}**\n({voice_info['member_count']} members)"
            else:
                voice_status = "🔴 Not connected"
            embed.add_field(name="Voice Channel", value=voice_status, inline=True)
            
            # Audio storage info
            storage_text = (
                f"Files: {storage_info['file_count']}\n"
                f"Size: {storage_info['total_size_mb']} MB\n"
                f"Last audio: {'✅' if storage_info['last_audio_exists'] else '❌'}"
            )
            embed.add_field(name="Audio Storage", value=storage_text, inline=True)
            
            # Add timestamp
            embed.timestamp = nextcord.utils.utcnow()
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await ctx.send("❌ Error retrieving status information.")
    
    async def leave_command(self, ctx: commands.Context) -> None:
        """Handle !leave command to disconnect from voice channel.
        
        Args:
            ctx: Discord command context
        """
        try:
            if not self.bot_manager.is_in_voice_channel():
                await ctx.send("❌ I'm not in a voice channel!")
                return
            
            # Get current channel name for confirmation message
            channel_name = "voice channel"
            voice_info = self.bot_manager.get_voice_channel_info()
            if voice_info:
                channel_name = voice_info['name']
            
            # Leave the voice channel
            await self.bot_manager.leave_voice_channel()
            await ctx.send(f"👋 Left {channel_name}")
            
        except Exception as e:
            logger.error(f"Error in leave command: {e}")
            await ctx.send("❌ An error occurred while leaving the voice channel.")