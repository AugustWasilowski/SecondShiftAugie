"""
Slash command handler system for Discord bot.

Implements Discord slash commands that provide a modern user experience with
autocomplete and validation, delegating to existing BotCommands functionality.

Requirements addressed:
- 3.1: Show available bot commands when user types "/"
- 3.2: /join command joins user's voice channel
- 3.3: /leave command leaves current voice channel
- 3.4: /play command replays last generated audio
- 3.5: /health command shows bot and system status
- 3.6: /help command shows available commands and usage
"""

import logging
from typing import TYPE_CHECKING

import nextcord
from nextcord.ext import commands

if TYPE_CHECKING:
    from .commands import BotCommands

logger = logging.getLogger(__name__)


class SlashCommandHandler:
    """Handler for Discord slash commands with delegation to existing BotCommands."""
    
    def __init__(self, bot: commands.Bot, bot_commands: "BotCommands"):
        """Initialize slash command handler.
        
        Args:
            bot: Discord bot instance
            bot_commands: Existing BotCommands instance to delegate to
        """
        self.bot = bot
        self.bot_commands = bot_commands
        self._commands_registered = False
        
        logger.info("SlashCommandHandler initialized")
    
    def register_commands(self) -> None:
        """Register all slash commands with the Discord bot.
        
        Requirement 3.1: WHEN a user types "/" in Discord THEN the system SHALL show available bot commands
        """
        if self._commands_registered:
            logger.warning("Slash commands already registered")
            return
        
        try:
            # Register each slash command
            self._register_join_command()
            self._register_leave_command()
            self._register_play_command()
            self._register_health_command()
            self._register_help_command()
            self._register_reboot_command()
            
            self._commands_registered = True
            logger.info("All slash commands registered successfully")
            
        except Exception as e:
            logger.error(f"Error registering slash commands: {e}")
            raise
    
    def _register_join_command(self) -> None:
        """Register the /join slash command.
        
        Requirement 3.2: WHEN a user executes "/join" THEN the system SHALL join the user's voice channel
        """
        @self.bot.slash_command(
            name="join",
            description="Join your current voice channel"
        )
        async def join_slash(interaction: nextcord.Interaction):
            """Handle /join slash command."""
            await self.handle_join(interaction)
    
    def _register_leave_command(self) -> None:
        """Register the /leave slash command.
        
        Requirement 3.3: WHEN a user executes "/leave" THEN the system SHALL leave the current voice channel
        """
        @self.bot.slash_command(
            name="leave",
            description="Leave the current voice channel"
        )
        async def leave_slash(interaction: nextcord.Interaction):
            """Handle /leave slash command."""
            await self.handle_leave(interaction)
    
    def _register_play_command(self) -> None:
        """Register the /play slash command.
        
        Requirement 3.4: WHEN a user executes "/play" THEN the system SHALL replay the last generated audio
        """
        @self.bot.slash_command(
            name="play",
            description="Replay the last generated voice response"
        )
        async def play_slash(interaction: nextcord.Interaction):
            """Handle /play slash command."""
            await self.handle_play(interaction)
    
    def _register_health_command(self) -> None:
        """Register the /health slash command.
        
        Requirement 3.5: WHEN a user executes "/health" THEN the system SHALL show bot and system status
        """
        @self.bot.slash_command(
            name="health",
            description="Show detailed bot and system health status"
        )
        async def health_slash(interaction: nextcord.Interaction):
            """Handle /health slash command."""
            await self.handle_health(interaction)
    
    def _register_help_command(self) -> None:
        """Register the /help slash command.
        
        Requirement 3.6: WHEN a user executes "/help" THEN the system SHALL show available commands and usage
        """
        @self.bot.slash_command(
            name="help",
            description="Show available commands and usage information"
        )
        async def help_slash(interaction: nextcord.Interaction):
            """Handle /help slash command."""
            await self.handle_help(interaction)
    
    def _register_reboot_command(self) -> None:
        """Register the /reboot slash command for soft restart of AI components."""
        @self.bot.slash_command(
            name="reboot",
            description="Soft restart AI and TTS components without disconnecting from Discord"
        )
        async def reboot_slash(interaction: nextcord.Interaction):
            """Handle /reboot slash command."""
            await self.handle_reboot(interaction)
    
    async def handle_join(self, interaction: nextcord.Interaction) -> None:
        """Handle /join slash command interaction.
        
        Delegates to existing BotCommands.join_command functionality with proper
        error handling and user feedback for slash commands.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            # Defer response to prevent timeout for potentially slow operations
            await interaction.response.defer()
            
            # Create a mock context object that BotCommands expects
            # This allows us to reuse existing command logic
            mock_ctx = MockContext(interaction)
            
            # Delegate to existing join command logic
            await self.bot_commands.join_command(mock_ctx)
            
            # Send the response that was captured by MockContext
            if mock_ctx.response_sent:
                await interaction.followup.send(mock_ctx.last_response)
            else:
                await interaction.followup.send("✅ Join command completed")
                
        except Exception as e:
            logger.error(f"Error in /join slash command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing the join command.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while processing the join command.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /join: {followup_error}")
    
    async def handle_leave(self, interaction: nextcord.Interaction) -> None:
        """Handle /leave slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            await interaction.response.defer()
            
            mock_ctx = MockContext(interaction)
            await self.bot_commands.leave_command(mock_ctx)
            
            if mock_ctx.response_sent:
                await interaction.followup.send(mock_ctx.last_response)
            else:
                await interaction.followup.send("✅ Leave command completed")
                
        except Exception as e:
            logger.error(f"Error in /leave slash command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing the leave command.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while processing the leave command.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /leave: {followup_error}")
    
    async def handle_play(self, interaction: nextcord.Interaction) -> None:
        """Handle /play slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            await interaction.response.defer()
            
            mock_ctx = MockContext(interaction)
            await self.bot_commands.play_command(mock_ctx)
            
            if mock_ctx.response_sent:
                await interaction.followup.send(mock_ctx.last_response)
            else:
                await interaction.followup.send("✅ Play command completed")
                
        except Exception as e:
            logger.error(f"Error in /play slash command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing the play command.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while processing the play command.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /play: {followup_error}")
    
    async def handle_health(self, interaction: nextcord.Interaction) -> None:
        """Handle /health slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            await interaction.response.defer()
            
            mock_ctx = MockContext(interaction)
            await self.bot_commands.status_command(mock_ctx)
            
            if mock_ctx.response_sent:
                # For health command, we want to show the detailed status
                if mock_ctx.last_embed:
                    await interaction.followup.send(embed=mock_ctx.last_embed)
                else:
                    await interaction.followup.send(mock_ctx.last_response)
            else:
                await interaction.followup.send("✅ Health check completed")
                
        except Exception as e:
            logger.error(f"Error in /health slash command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while checking system health.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while checking system health.",
                        ephemeral=True
                    )
            except Exception as followup_error:
                logger.error(f"Error sending error response for /health: {followup_error}")
    
    async def handle_help(self, interaction: nextcord.Interaction) -> None:
        """Handle /help slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            await interaction.response.defer()
            
            # Check AI availability for dynamic help content
            ai_available = (self.bot_commands.ollama_engine and 
                          self.bot_commands.ollama_engine.is_ready())
            
            # Create updated help content for slash commands
            embed = nextcord.Embed(
                title="🤖 SecondShiftAugie Bot Commands",
                description="AI-powered Discord bot with intelligent conversations and voice responses",
                color=0x00ff00 if ai_available else 0xff9900
            )
            
            # Add slash command descriptions
            embed.add_field(
                name="🎤 Voice Commands",
                value=(
                    "`/join` - Join your current voice channel\n"
                    "`/play` - Replay the last generated voice response\n"
                    "`/leave` - Leave the current voice channel"
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
                name="ℹ️ System Commands",
                value=(
                    "`/help` - Show this help message\n"
                    "`/health` - Check detailed bot and system status\n"
                    "`/reboot` - Soft restart AI and TTS components"
                ),
                inline=False
            )
            
            # Add current status information including AI
            voice_status = "🟢 Connected" if self.bot_commands.bot_manager.is_in_voice_channel() else "🔴 Not connected"
            tts_status = "🟢 Ready" if self.bot_commands.tts_engine and self.bot_commands.tts_engine.is_ready() else "🔴 Not ready"
            
            if self.bot_commands.ollama_engine:
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
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in /help slash command: {e}")
            try:
                # Fallback to simple text message if embed fails
                ai_available = (self.bot_commands.ollama_engine and 
                              self.bot_commands.ollama_engine.is_ready())
                
                if ai_available:
                    help_text = (
                        "**SecondShiftAugie Bot Commands:**\n"
                        "🎤 `/join` - Join your voice channel\n"
                        "🔊 `/play` - Replay last voice response\n"
                        "👋 `/leave` - Leave voice channel\n"
                        "🤖 Mention me for intelligent AI conversations!\n"
                        "ℹ️ `/help` - Show this message\n"
                        "📊 `/health` - Check bot status\n"
                        "🔄 `/reboot` - Restart AI/TTS components"
                    )
                else:
                    help_text = (
                        "**SecondShiftAugie Bot Commands:**\n"
                        "🎤 `/join` - Join your voice channel\n"
                        "🔊 `/play` - Replay last voice response\n"
                        "👋 `/leave` - Leave voice channel\n"
                        "💬 Mention me for voice responses! (AI currently unavailable)\n"
                        "ℹ️ `/help` - Show this message\n"
                        "📊 `/health` - Check bot status\n"
                        "🔄 `/reboot` - Restart AI/TTS components"
                    )
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(help_text)
                else:
                    await interaction.followup.send(help_text)
                    
            except Exception as followup_error:
                logger.error(f"Error sending fallback help response: {followup_error}")
    
    async def handle_reboot(self, interaction: nextcord.Interaction) -> None:
        """Handle /reboot slash command for soft restart of AI components.
        
        Args:
            interaction: Discord slash command interaction
        """
        try:
            # Send initial "BRB" message
            await interaction.response.send_message("🔄 BRB, rebooting AI and TTS components...")
            
            # Get reference to the main bot app through the bot_commands
            main_app = getattr(self.bot_commands, '_main_app', None)
            if not main_app:
                await interaction.followup.send("❌ Cannot access main application for reboot")
                return
            
            # Perform soft reboot
            reboot_success = await self._perform_soft_reboot(main_app)
            
            if reboot_success:
                await interaction.followup.send("✅ Back online! AI and TTS components restarted successfully.")
            else:
                await interaction.followup.send("⚠️ Reboot completed with some issues. Check `/health` for details.")
                
        except Exception as e:
            logger.error(f"Error in /reboot slash command: {e}")
            try:
                await interaction.followup.send(
                    f"❌ Reboot failed: {str(e)}",
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending reboot error response: {followup_error}")
    
    async def _perform_soft_reboot(self, main_app) -> bool:
        """Perform the actual soft reboot of AI and TTS components.
        
        Args:
            main_app: Reference to the main SecondShiftAugieBot application
            
        Returns:
            bool: True if reboot was successful, False otherwise
        """
        try:
            logger.info("Starting soft reboot of AI and TTS components...")
            
            # Cleanup existing components
            if main_app.ollama_engine:
                await main_app.ollama_engine.cleanup()
                logger.info("Ollama engine cleaned up")
            
            if main_app.tts_engine:
                await main_app.tts_engine.cleanup()
                logger.info("TTS engine cleaned up")
            
            # Reinitialize Ollama engine
            if main_app.ollama_config:
                from src.ai.ollama_engine import OllamaEngine
                main_app.ollama_engine = OllamaEngine(main_app.ollama_config, main_app.system_prompt_manager)
                
                ollama_success = await main_app.ollama_engine.initialize()
                if ollama_success:
                    logger.info("Ollama engine reinitialized successfully")
                else:
                    logger.warning("Ollama engine failed to reinitialize")
            
            # Reinitialize TTS engine
            if main_app.tts_config:
                from src.tts.voxcpm_engine import VoxCPMEngine
                main_app.tts_engine = VoxCPMEngine(main_app.tts_config)
                
                tts_success = await main_app.tts_engine.initialize()
                if tts_success:
                    logger.info("TTS engine reinitialized successfully")
                else:
                    logger.warning("TTS engine failed to reinitialize")
            
            # Update bot_commands references
            self.bot_commands.ollama_engine = main_app.ollama_engine
            self.bot_commands.tts_engine = main_app.tts_engine
            
            logger.info("Soft reboot completed")
            return True
            
        except Exception as e:
            logger.error(f"Error during soft reboot: {e}")
            return False


class MockContext:
    """Mock context object to bridge slash commands with existing command handlers.
    
    This allows us to reuse existing BotCommands logic that expects a commands.Context
    object while working with slash command interactions.
    """
    
    def __init__(self, interaction: nextcord.Interaction):
        """Initialize mock context from slash command interaction.
        
        Args:
            interaction: Discord slash command interaction
        """
        self.interaction = interaction
        self.author = interaction.user
        self.channel = interaction.channel
        self.guild = interaction.guild
        self.bot = interaction.client
        
        # Track responses for delegation
        self.response_sent = False
        self.last_response = ""
        self.last_embed = None
    
    async def send(self, content=None, *, embed=None, **kwargs):
        """Mock send method that captures the response.
        
        Args:
            content: Message content
            embed: Message embed
            **kwargs: Additional arguments
        """
        self.response_sent = True
        if content:
            self.last_response = str(content)
        if embed:
            self.last_embed = embed
        
        # Log what would be sent for debugging
        logger.debug(f"MockContext captured response: {content}")
        if embed:
            logger.debug(f"MockContext captured embed: {embed.title}")