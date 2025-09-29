"""
Command system with voice integration for VoxCPM Discord bot.

Implements Discord bot commands that integrate with VoxCPM TTS functionality,
including voice channel management and audio playback commands.
"""

import logging
from typing import TYPE_CHECKING, Optional

import nextcord
from nextcord.ext import commands

if TYPE_CHECKING:
    from .discord_manager import DiscordBotManager
    from ..tts.voxcpm_engine import VoxCPMEngine
    from ..audio.audio_manager import AudioManager
    from ..ai.ollama_engine import OllamaEngine

logger = logging.getLogger(__name__)


class BotCommands:
    """Command handlers for Discord bot with VoxCPM integration."""
    
    def __init__(
        self, 
        bot_manager: "DiscordBotManager", 
        tts_engine: "VoxCPMEngine", 
        audio_manager: "AudioManager",
        ollama_engine: Optional["OllamaEngine"] = None,
        main_app=None
    ):
        """Initialize command system.
        
        Args:
            bot_manager: Discord bot manager instance
            tts_engine: VoxCPM TTS engine instance
            audio_manager: Audio file manager instance
            ollama_engine: Optional Ollama AI engine for intelligent responses
            main_app: Reference to main SecondShiftAugieBot application for reboot functionality
        """
        self.bot_manager = bot_manager
        self.tts_engine = tts_engine
        self.audio_manager = audio_manager
        self.ollama_engine = ollama_engine
        self._main_app = main_app
        
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
        
        Requirement 3.5: Update help command to reflect new AI capabilities
        
        Args:
            ctx: Discord command context
        """
        try:
            # Check AI availability for dynamic help content
            ai_available = self.ollama_engine and self.ollama_engine.is_ready()
            
            # Create embed with bot functionality
            embed = nextcord.Embed(
                title="🤖 SecondShiftAugie Bot Commands",
                description="AI-powered Discord bot with intelligent conversations and voice responses",
                color=0x00ff00 if ai_available else 0xff9900
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
            
            # Dynamic chat features based on AI availability
            if ai_available:
                chat_features = (
                    "• Mention me (@SecondShiftAugie) for intelligent AI conversations\n"
                    "• I use Ollama with Qwen2.5 model for smart responses\n"
                    "• Responses are converted to speech using VoxCPM TTS\n"
                    "• Voice responses play automatically when I'm in a voice channel"
                )
            else:
                chat_features = (
                    "• Mention me (@SecondShiftAugie) for voice responses\n"
                    "• AI features currently unavailable (using simple responses)\n"
                    "• I'll generate speech using VoxCPM TTS\n"
                    "• Voice responses play automatically when I'm in a voice channel"
                )
            
            embed.add_field(
                name="💬 Chat Features",
                value=chat_features,
                inline=False
            )
            
            embed.add_field(
                name="ℹ️ Information Commands",
                value=(
                    "`!help` - Show this help message\n"
                    "`!status` - Check bot, TTS, and AI engine status"
                ),
                inline=False
            )
            
            # Add status information including AI
            voice_status = "🟢 Connected" if self.bot_manager.is_in_voice_channel() else "🔴 Not connected"
            tts_status = "🟢 Ready" if self.tts_engine.is_ready() else "🔴 Not ready"
            
            if self.ollama_engine:
                ai_status = "🟢 Ready" if ai_available else "🔴 Not ready"
                status_text = (
                    f"Voice Channel: {voice_status}\n"
                    f"TTS Engine: {tts_status}\n"
                    f"AI Engine: {ai_status}"
                )
            else:
                status_text = (
                    f"Voice Channel: {voice_status}\n"
                    f"TTS Engine: {tts_status}\n"
                    f"AI Engine: ❌ Not configured"
                )
            
            embed.add_field(
                name="📊 Current Status",
                value=status_text,
                inline=False
            )
            
            # Dynamic footer based on AI availability
            if ai_available:
                footer_text = "💡 Tip: Join a voice channel and mention me for intelligent AI conversations!"
            else:
                footer_text = "💡 Tip: Join a voice channel and mention me to hear voice responses!"
            
            embed.set_footer(text=footer_text)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            # Fallback to simple text message if embed fails
            ai_available = self.ollama_engine and self.ollama_engine.is_ready()
            
            if ai_available:
                help_text = (
                    "**SecondShiftAugie Bot Commands:**\n"
                    "🎤 `!join` - Join your voice channel\n"
                    "🔊 `!play` - Replay last voice response\n"
                    "🤖 Mention me for intelligent AI conversations!\n"
                    "ℹ️ `!help` - Show this message\n"
                    "📊 `!status` - Check bot, TTS, and AI status"
                )
            else:
                help_text = (
                    "**SecondShiftAugie Bot Commands:**\n"
                    "🎤 `!join` - Join your voice channel\n"
                    "🔊 `!play` - Replay last voice response\n"
                    "💬 Mention me for voice responses! (AI currently unavailable)\n"
                    "ℹ️ `!help` - Show this message\n"
                    "📊 `!status` - Check bot status"
                )
            
            await ctx.send(help_text)
    
    async def status_command(self, ctx: commands.Context) -> None:
        """Handle !status command to show bot and engine status.
        
        Requirements:
        - 3.5: Show bot status including AI capabilities
        - 6.4: Include AI status in health reporting
        - 6.5: Indicate when AI features are unavailable
        
        Args:
            ctx: Discord command context
        """
        try:
            # Gather basic status information
            bot_ready = self.bot_manager.is_ready()
            in_voice = self.bot_manager.is_in_voice_channel()
            tts_ready = self.tts_engine.is_ready()
            
            # Get voice channel info if connected
            voice_info = self.bot_manager.get_voice_channel_info()
            
            # Get audio storage info
            storage_info = self.audio_manager.get_storage_info()
            
            # Get comprehensive AI status information
            ai_ready = False
            ai_health_ok = False
            ai_test_result = None
            ai_error = None
            ai_health_details = None
            
            if self.ollama_engine:
                ai_ready = self.ollama_engine.is_ready()
                
                # Get comprehensive AI health status
                try:
                    ai_health_details = self.ollama_engine.get_ai_health_status()
                    overall_health = ai_health_details.get("overall_health", "UNKNOWN")
                    
                    if overall_health == "HEALTHY":
                        ai_health_ok = True
                    elif overall_health == "DEGRADED":
                        ai_health_ok = False
                        ai_error = "AI in degraded mode"
                    else:
                        ai_health_ok = False
                        ai_error = "AI health check failed"
                        
                    logger.debug(f"AI comprehensive health status: {overall_health}")
                    
                except Exception as health_error:
                    logger.warning(f"AI health status check failed: {health_error}")
                    ai_error = f"Health status failed: {str(health_error)[:50]}"
                
                # Perform basic health check if ready
                if ai_ready and ai_health_ok:
                    try:
                        basic_health = await self.ollama_engine.health_check()
                        logger.debug(f"AI basic health check result: {basic_health}")
                        
                        if not basic_health:
                            ai_health_ok = False
                            ai_error = "Basic health check failed"
                            
                    except Exception as health_error:
                        logger.warning(f"AI basic health check failed: {health_error}")
                        ai_health_ok = False
                        ai_error = f"Health check failed: {str(health_error)[:50]}"
                
                # Test AI response generation if healthy
                if ai_ready and ai_health_ok:
                    try:
                        logger.info("Testing AI response generation for status command")
                        test_response = await self.ollama_engine.generate_response(
                            "Hello, this is a test message for status checking.", 
                            "Respond briefly that the test was successful."
                        )
                        
                        if test_response.success:
                            ai_test_result = "✅ Working"
                            logger.info("AI response generation test successful")
                        else:
                            ai_test_result = f"⚠️ Failed"
                            ai_error = test_response.error_message or "Unknown error"
                            logger.warning(f"AI response test failed: {ai_error}")
                            
                    except Exception as test_error:
                        ai_test_result = "❌ Error"
                        ai_error = str(test_error)[:50]
                        logger.error(f"AI response test error: {test_error}")
                elif ai_ready:
                    ai_test_result = "❌ Health check failed"
                else:
                    ai_test_result = "❌ Engine not ready"
            
            # Determine overall status color
            all_systems_ok = bot_ready and tts_ready and (not self.ollama_engine or ai_health_ok)
            embed_color = 0x00ff00 if all_systems_ok else 0xff9900
            
            # Create status embed
            embed = nextcord.Embed(
                title="📊 Bot Status Report",
                color=embed_color
            )
            
            # Core system status
            bot_status = "🟢 Online" if bot_ready else "🔴 Offline"
            embed.add_field(name="Bot Status", value=bot_status, inline=True)
            
            tts_status = "🟢 Ready" if tts_ready else "🔴 Not Ready"
            embed.add_field(name="TTS Engine", value=tts_status, inline=True)
            
            # AI Engine status with detailed information
            if self.ollama_engine:
                if ai_ready and ai_health_ok:
                    ai_status = "🟢 Ready & Healthy"
                elif ai_ready:
                    ai_status = "🟡 Ready (Health Issues)"
                else:
                    ai_status = "🔴 Not Ready"
                
                embed.add_field(name="AI Engine", value=ai_status, inline=True)
                
                # AI response test results
                if ai_test_result:
                    embed.add_field(name="AI Response Test", value=ai_test_result, inline=True)
                
                # Circuit breaker status if available
                if ai_health_details and "circuit_breakers" in ai_health_details:
                    cb_status = ai_health_details["circuit_breakers"]
                    ollama_cb = cb_status.get("ollama_api", {})
                    response_cb = cb_status.get("ai_response", {})
                    
                    cb_text = f"API: {ollama_cb.get('state', 'UNKNOWN')}"
                    if ollama_cb.get('failure_count', 0) > 0:
                        cb_text += f" ({ollama_cb['failure_count']} fails)"
                    
                    cb_text += f"\nResp: {response_cb.get('state', 'UNKNOWN')}"
                    if response_cb.get('failure_count', 0) > 0:
                        cb_text += f" ({response_cb['failure_count']} fails)"
                    
                    embed.add_field(name="Circuit Breakers", value=cb_text, inline=True)
                
                # Show AI error if any
                if ai_error:
                    error_text = ai_error if len(ai_error) <= 50 else ai_error[:47] + "..."
                    embed.add_field(name="AI Error", value=f"⚠️ {error_text}", inline=True)
                
                # Show error rate if available
                if ai_health_details and "recent_error_rate" in ai_health_details:
                    error_rate = ai_health_details["recent_error_rate"]
                    if error_rate > 0:
                        embed.add_field(name="Recent Errors", value=f"⚠️ {error_rate}/hour", inline=True)
                        
            else:
                embed.add_field(name="AI Engine", value="❌ Not Configured", inline=True)
                embed.add_field(name="AI Features", value="❌ Unavailable", inline=True)
            
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
            
            # Feature availability summary
            features = []
            if tts_ready:
                features.append("✅ Text-to-Speech")
            else:
                features.append("❌ Text-to-Speech")
            
            if in_voice:
                features.append("✅ Voice Playback")
            else:
                features.append("❌ Voice Playback")
            
            if self.ollama_engine and ai_ready and ai_health_ok:
                features.append("✅ AI Conversations")
            elif self.ollama_engine:
                features.append("⚠️ AI Conversations")
            else:
                features.append("❌ AI Conversations")
            
            embed.add_field(
                name="Available Features",
                value="\n".join(features),
                inline=False
            )
            
            # Add comprehensive health monitoring information if available
            try:
                from src.utils.health_monitoring import health_monitoring_service
                health_report = health_monitoring_service.get_system_health_report()
                
                if health_report and health_report.get("monitoring_active"):
                    monitoring_status = "🟢 Active" if health_report["monitoring_active"] else "🔴 Inactive"
                    embed.add_field(name="Health Monitoring", value=monitoring_status, inline=True)
                    
                    # Add circuit breaker information
                    ai_health = health_report.get("ai_health", {})
                    if ai_health and "circuit_breakers" in ai_health:
                        cb_info = ai_health["circuit_breakers"]
                        cb_status = []
                        
                        for cb_name, cb_data in cb_info.items():
                            state = cb_data.get("state", "UNKNOWN")
                            if state == "CLOSED":
                                cb_status.append(f"✅ {cb_name.replace('_', ' ').title()}")
                            elif state == "HALF_OPEN":
                                cb_status.append(f"🟡 {cb_name.replace('_', ' ').title()}")
                            else:
                                cb_status.append(f"🔴 {cb_name.replace('_', ' ').title()}")
                        
                        if cb_status:
                            embed.add_field(
                                name="Circuit Breakers",
                                value="\n".join(cb_status[:3]),  # Limit to 3 items
                                inline=True
                            )
                            
            except Exception as monitoring_error:
                logger.debug(f"Could not get health monitoring info: {monitoring_error}")
            
            # Add helpful footer based on status
            if not all_systems_ok:
                if not ai_ready and self.ollama_engine:
                    footer_text = "💡 AI features degraded - using simple responses. Check Ollama service."
                elif not tts_ready:
                    footer_text = "💡 TTS unavailable - text responses only."
                elif not in_voice:
                    footer_text = "💡 Use !join to enable voice responses."
                else:
                    footer_text = "💡 Some features may be limited."
            else:
                footer_text = "✅ All systems operational!"
            
            embed.set_footer(text=footer_text)
            
            # Add timestamp
            embed.timestamp = nextcord.utils.utcnow()
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            # Graceful fallback when embed creation fails
            try:
                # Simple text status as fallback
                ai_status = "Not configured"
                if self.ollama_engine:
                    ai_status = "Ready" if self.ollama_engine.is_ready() else "Not ready"
                
                fallback_text = (
                    f"**Bot Status:**\n"
                    f"🤖 Bot: {'Online' if self.bot_manager.is_ready() else 'Offline'}\n"
                    f"🎤 TTS: {'Ready' if self.tts_engine.is_ready() else 'Not ready'}\n"
                    f"🧠 AI: {ai_status}\n"
                    f"🔊 Voice: {'Connected' if self.bot_manager.is_in_voice_channel() else 'Not connected'}"
                )
                await ctx.send(fallback_text)
            except Exception as fallback_error:
                logger.error(f"Fallback status also failed: {fallback_error}")
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