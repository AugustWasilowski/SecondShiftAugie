"""
Main bot application with VoxCPM integration.

This is the main entry point for the SecondShiftAugie Discord bot with VoxCPM TTS integration.
It initializes all components, loads configuration from environment variables, and manages
the bot startup sequence including VoxCPM model loading.

Requirements addressed:
- 4.1: Graceful fallback when VoxCPM is not available
- 4.2: Configurable TTS behavior and quality settings
- 4.3: Error handling for missing reference files
- 5.1: Bot startup and initialization
"""

import asyncio
import logging
import os
import sys
import signal
from pathlib import Path
from typing import Optional

import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv

# Import our components
from src.tts.voxcpm_engine import VoxCPMEngine
from src.tts.config import TTSConfig
from src.bot.discord_manager import DiscordBotManager
from src.bot.config import BotConfig
from src.bot.message_router import MessageRouter
from src.bot.commands import BotCommands
from src.audio.audio_manager import AudioManager

# Import AI components
from src.ai.ollama_engine import OllamaEngine
from src.ai.system_prompt_manager import SystemPromptManager
from src.bot.slash_commands import SlashCommandHandler

# Import configuration and validation system
from src.config import ConfigLoader, ConfigValidationError, StartupValidator, ValidationResult
from src.config.ollama_config import OllamaConfig

# Import error handling utilities
from src.utils.error_handler import (
    health_monitor, degradation_manager, log_component_error, log_component_recovery,
    ErrorSeverity, ComponentState, retry_with_backoff, ai_error_handler
)

# Import health monitoring service
from src.utils.health_monitoring import health_monitoring_service


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class SecondShiftAugieBot:
    """Main bot application class that coordinates all components."""
    
    def __init__(self):
        """Initialize the bot application."""
        self.config: Optional[BotConfig] = None
        self.tts_config: Optional[TTSConfig] = None
        self.ollama_config: Optional[OllamaConfig] = None
        self.tts_engine: Optional[VoxCPMEngine] = None
        self.ollama_engine: Optional[OllamaEngine] = None
        self.system_prompt_manager: Optional[SystemPromptManager] = None
        self.bot_manager: Optional[DiscordBotManager] = None
        self.audio_manager: Optional[AudioManager] = None
        self.message_router: Optional[MessageRouter] = None
        self.bot_commands: Optional[BotCommands] = None
        self.slash_command_handler: Optional[SlashCommandHandler] = None
        self._shutdown_event = asyncio.Event()
        self._shutdown_requested = False
        
        # Initialize component health monitoring
        health_monitor.update_component_state("main_app", ComponentState.HEALTHY)
        
        # Register health check functions
        self._register_health_checks()
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("SecondShiftAugie bot application initialized")
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_requested = True
            if not self._shutdown_event.is_set():
                asyncio.create_task(self._trigger_shutdown())
        
        # Set up signal handlers (Windows compatible)
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            if hasattr(signal, 'SIGBREAK'):  # Windows
                signal.signal(signal.SIGBREAK, signal_handler)
        except Exception as e:
            logger.warning(f"Could not set up signal handlers: {e}")
    
    async def _trigger_shutdown(self):
        """Trigger shutdown event."""
        self._shutdown_event.set()
    
    def _register_health_checks(self):
        """Register health check functions for all components."""
        logger.info("Registering component health checks")
        
        # Register health checks that will be available after initialization
        # These will be registered properly in initialize_components
        pass
    
    def _register_component_health_checks(self):
        """Register health checks for initialized components."""
        logger.info("Registering health checks for initialized components")
        
        # Register TTS engine health check
        if self.tts_engine:
            async def tts_health_check():
                try:
                    return self.tts_engine.is_ready()
                except Exception as e:
                    logger.debug(f"TTS health check error: {e}")
                    return False
            
            health_monitoring_service.register_health_check("tts_engine", tts_health_check)
        
        # Register Ollama AI engine health check
        if self.ollama_engine:
            async def ollama_health_check():
                try:
                    return await self.ollama_engine.health_check()
                except Exception as e:
                    logger.debug(f"Ollama health check error: {e}")
                    return False
            
            health_monitoring_service.register_health_check("ollama_engine", ollama_health_check)
        
        # Register Discord bot manager health check
        if self.bot_manager:
            async def discord_health_check():
                try:
                    return self.bot_manager.is_ready()
                except Exception as e:
                    logger.debug(f"Discord health check error: {e}")
                    return False
            
            health_monitoring_service.register_health_check("discord_manager", discord_health_check)
        
        # Register audio manager health check
        if self.audio_manager:
            async def audio_health_check():
                try:
                    # Audio manager doesn't have a specific health check, so check if it exists
                    storage_info = self.audio_manager.get_storage_info()
                    return storage_info is not None
                except Exception as e:
                    logger.debug(f"Audio manager health check error: {e}")
                    return False
            
            health_monitoring_service.register_health_check("audio_manager", audio_health_check)
        
        logger.info("Component health checks registered successfully")
    
    def load_configuration(self) -> bool:
        """
        Load configuration using the new configuration system.
        
        Requirements 4.2, 4.3, 5.4: Comprehensive configuration loading with validation.
        
        Returns:
            bool: True if configuration loaded successfully, False otherwise
        """
        try:
            logger.info("Loading configuration using ConfigLoader...")
            
            # Initialize configuration loader
            config_loader = ConfigLoader()
            
            # Load all configurations with validation
            self.config, self.tts_config, self.ollama_config = config_loader.load_all_configs()
            
            # Log configuration summary
            summary = config_loader.get_validation_summary()
            logger.info(f"Configuration loaded successfully: {summary}")
            
            return True
            
        except ConfigValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            if e.errors:
                for error in e.errors:
                    logger.error(f"  - {error}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}")
            return False
    
    def validate_startup_requirements(self) -> bool:
        """
        Validate startup requirements using the new validation system.
        
        Requirements 4.2, 4.3, 5.4: Comprehensive startup validation including reference files
        and VoxCPM model accessibility.
        
        Returns:
            bool: True if critical requirements are met, False otherwise
        """
        try:
            logger.info("Running comprehensive startup validation...")
            
            # Initialize startup validator
            validator = StartupValidator(self.config, self.tts_config, self.ollama_config)
            
            # Run all validations
            validation_result = validator.run_all_validations()
            
            # Log all validation results
            validator.log_validation_results()
            
            # Check if bot can start
            if not validation_result.can_start:
                logger.error("Critical validation failures prevent bot startup")
                return False
            
            # Log summary
            summary = validation_result.summary
            logger.info(f"Startup validation summary: {summary}")
            
            # Warn about disabled features
            if not summary.get('voice_features_available', True):
                logger.warning("Voice features will be disabled due to validation issues")
                degradation_manager.disable_feature("voice_generation", "Startup validation failed")
                degradation_manager.enable_degraded_mode("bot_responses", "text-only responses")
            
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error during startup validation: {e}")
            return False
    
    async def initialize_components(self) -> bool:
        """Initialize all bot components with comprehensive error handling.
        
        Requirements 4.1, 4.2: Graceful fallback and proper error logging.
        
        Returns:
            bool: True if critical components initialized successfully, False otherwise
        """
        try:
            # Initialize audio manager first (no dependencies)
            logger.info("Initializing audio manager...")
            try:
                self.audio_manager = AudioManager(self.config.save_path)
                health_monitor.update_component_state("audio_manager", ComponentState.HEALTHY)
                log_component_recovery("audio_manager", "initialization")
            except Exception as e:
                log_component_error("audio_manager", "initialization", e, ErrorSeverity.HIGH)
                logger.error("Audio manager initialization failed - audio features will be unavailable")
                degradation_manager.disable_feature("audio_playback", "Audio manager initialization failed")
                return False  # Audio manager is critical
            
            # Initialize system prompt manager
            logger.info("Initializing system prompt manager...")
            try:
                self.system_prompt_manager = SystemPromptManager(self.ollama_config.system_prompt_file)
                health_monitor.update_component_state("system_prompt_manager", ComponentState.HEALTHY)
                log_component_recovery("system_prompt_manager", "initialization")
            except Exception as e:
                log_component_error("system_prompt_manager", "initialization", e, ErrorSeverity.MEDIUM)
                logger.warning("System prompt manager initialization failed - using default prompts")
                health_monitor.update_component_state("system_prompt_manager", ComponentState.FAILED)
                # Continue without system prompt manager - not critical
            
            # Initialize Ollama AI engine with graceful degradation
            logger.info("Initializing Ollama AI engine...")
            try:
                self.ollama_engine = OllamaEngine(self.ollama_config, self.system_prompt_manager)
                
                # Attempt to initialize Ollama (Requirement 1.5: verify connectivity)
                async def init_ollama():
                    return await self.ollama_engine.initialize()
                
                ollama_ready = await retry_with_backoff(
                    init_ollama,
                    max_retries=2,
                    base_delay=2.0
                )
                
                if not ollama_ready:
                    logger.warning("Ollama AI engine failed to initialize - continuing without AI features")
                    health_monitor.update_component_state("ollama_engine", ComponentState.FAILED)
                    degradation_manager.disable_feature("ai_responses", "Ollama initialization failed")
                else:
                    logger.info("Ollama AI engine initialized successfully")
                    health_monitor.update_component_state("ollama_engine", ComponentState.HEALTHY)
                    log_component_recovery("ollama_engine", "initialization")
                    
            except Exception as e:
                log_component_error("ollama_engine", "initialization", e, ErrorSeverity.MEDIUM)
                logger.warning("Ollama AI engine initialization failed - continuing without AI features")
                health_monitor.update_component_state("ollama_engine", ComponentState.FAILED)
                degradation_manager.disable_feature("ai_responses", f"AI initialization error: {str(e)}")
                # Continue without AI - not critical for basic bot operation
            
            # Initialize VoxCPM TTS engine with graceful degradation
            logger.info("Initializing VoxCPM TTS engine...")
            try:
                self.tts_engine = VoxCPMEngine(self.tts_config)
                
                # Attempt to initialize VoxCPM (Requirement 4.1: graceful fallback)
                async def init_tts():
                    return await self.tts_engine.initialize()
                
                tts_ready = await retry_with_backoff(
                    init_tts,
                    max_retries=2,
                    base_delay=2.0
                )
                
                if not tts_ready:
                    logger.warning("VoxCPM TTS engine failed to initialize - continuing in text-only mode")
                    health_monitor.update_component_state("tts_engine", ComponentState.FAILED)
                    degradation_manager.disable_feature("voice_generation", "VoxCPM initialization failed")
                    degradation_manager.enable_degraded_mode("bot_responses", "text-only responses")
                else:
                    logger.info("VoxCPM TTS engine initialized successfully")
                    health_monitor.update_component_state("tts_engine", ComponentState.HEALTHY)
                    log_component_recovery("tts_engine", "initialization")
                    
            except Exception as e:
                log_component_error("tts_engine", "initialization", e, ErrorSeverity.MEDIUM)
                logger.warning("VoxCPM TTS engine initialization failed - continuing in text-only mode")
                health_monitor.update_component_state("tts_engine", ComponentState.FAILED)
                degradation_manager.disable_feature("voice_generation", f"TTS initialization error: {str(e)}")
                degradation_manager.enable_degraded_mode("bot_responses", "text-only responses")
                # Continue without TTS - not critical for basic bot operation
            
            # Initialize Discord bot manager (critical component)
            logger.info("Initializing Discord bot manager...")
            try:
                self.bot_manager = DiscordBotManager(self.config)
                health_monitor.update_component_state("discord_manager", ComponentState.HEALTHY)
                log_component_recovery("discord_manager", "initialization")
            except Exception as e:
                log_component_error("discord_manager", "initialization", e, ErrorSeverity.CRITICAL)
                logger.error("Discord bot manager initialization failed - cannot continue")
                return False  # Discord manager is critical
            
            # Initialize message router with AI integration
            logger.info("Initializing message router...")
            try:
                self.message_router = MessageRouter(
                    self.tts_engine,
                    self.audio_manager,
                    self.bot_manager,
                    self.ollama_engine  # Add AI engine to message router
                )
                health_monitor.update_component_state("message_router", ComponentState.HEALTHY)
                log_component_recovery("message_router", "initialization")
            except Exception as e:
                log_component_error("message_router", "initialization", e, ErrorSeverity.CRITICAL)
                logger.error("Message router initialization failed - cannot continue")
                return False  # Message router is critical
            
            # Initialize command system with AI integration
            logger.info("Initializing command system...")
            try:
                self.bot_commands = BotCommands(
                    self.bot_manager,
                    self.tts_engine,
                    self.audio_manager,
                    self.ollama_engine  # Add AI engine to commands
                )
                health_monitor.update_component_state("command_system", ComponentState.HEALTHY)
                log_component_recovery("command_system", "initialization")
            except Exception as e:
                log_component_error("command_system", "initialization", e, ErrorSeverity.HIGH)
                logger.warning("Command system initialization failed - commands may not work properly")
                degradation_manager.disable_feature("bot_commands", f"Command system error: {str(e)}")
                # Continue without full command system - basic functionality may still work
            
            # Initialize slash command handler
            logger.info("Initializing slash command handler...")
            try:
                self.slash_command_handler = SlashCommandHandler(
                    self.bot_manager.bot,
                    self.bot_commands
                )
                # Register slash commands (Requirement 3.7: integrate slash command registration)
                self.slash_command_handler.register_commands()
                health_monitor.update_component_state("slash_commands", ComponentState.HEALTHY)
                log_component_recovery("slash_commands", "initialization")
                logger.info("Slash commands registered successfully")
            except Exception as e:
                log_component_error("slash_commands", "initialization", e, ErrorSeverity.MEDIUM)
                logger.warning("Slash command handler initialization failed - slash commands unavailable")
                health_monitor.update_component_state("slash_commands", ComponentState.FAILED)
                degradation_manager.disable_feature("slash_commands", f"Slash command error: {str(e)}")
                # Continue without slash commands - prefix commands still work
            
            # Set up Discord bot event handlers and commands
            try:
                self._setup_discord_handlers()
                logger.info("Discord event handlers set up successfully")
            except Exception as e:
                log_component_error("discord_handlers", "setup", e, ErrorSeverity.HIGH)
                logger.error("Discord event handler setup failed - bot may not respond properly")
                # Continue anyway - some functionality might still work
            
            # Log final component status
            health_summary = health_monitor.get_system_health_summary()
            logger.info(f"Component initialization complete - System health: {health_summary['overall_health']}")
            logger.info(f"Components: {health_summary['healthy']} healthy, {health_summary['degraded']} degraded, {health_summary['failed']} failed")
            
            # Log feature availability
            if not degradation_manager.is_feature_available("voice_generation"):
                logger.warning("Voice generation disabled - bot will operate in text-only mode")
            if not degradation_manager.is_feature_available("audio_playback"):
                logger.warning("Audio playback disabled - no voice channel functionality")
            
            # Register health checks for initialized components
            self._register_component_health_checks()
            
            return True
            
        except Exception as e:
            log_component_error("main_app", "component_initialization", e, ErrorSeverity.CRITICAL)
            logger.error(f"Critical error initializing components: {e}")
            return False
    
    def _setup_discord_handlers(self):
        """Set up Discord bot event handlers and commands."""
        bot = self.bot_manager.bot
        
        # Event handlers
        @bot.event
        async def on_ready():
            """Handle bot ready event with comprehensive error handling.
            
            Requirements 4.2: Proper error logging for debugging.
            """
            try:
                logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
                logger.info(f"Bot is in {len(bot.guilds)} guilds")
                
                # Set bot status with error handling
                try:
                    activity = nextcord.Activity(
                        type=nextcord.ActivityType.listening,
                        name="voice commands | /help"
                    )
                    await bot.change_presence(
                        status=nextcord.Status.online,
                        activity=activity
                    )
                    logger.info("Bot status set successfully")
                except Exception as status_error:
                    logger.warning(f"Could not set bot status: {status_error}")
                
                # Send startup message to configured channel
                try:
                    channel = bot.get_channel(self.config.channel_id)
                    if channel:
                        # Check if we have permission to send messages
                        try:
                            permissions = channel.permissions_for(channel.guild.me)
                            if not permissions.send_messages:
                                logger.warning(f"Bot lacks permission to send messages in channel: {channel.name}")
                                return
                        except Exception as perm_error:
                            logger.warning(f"Could not check channel permissions: {perm_error}")
                        
                        startup_msg = "Second Shift Augie reporting for duty."
                        
                        await channel.send(startup_msg)
                        logger.info(f"Startup message sent to channel: {channel.name}")
                        
                    else:
                        logger.warning(f"Configured channel not found: {self.config.channel_id}")
                        
                except nextcord.HTTPException as http_error:
                    logger.warning(f"HTTP error sending startup message: {http_error}")
                except nextcord.Forbidden:
                    logger.warning("Bot lacks permission to send startup message")
                except Exception as startup_error:
                    logger.warning(f"Could not send startup message: {startup_error}")
                
            except Exception as ready_error:
                logger.error(f"Error in on_ready handler: {ready_error}")
        
        @bot.event
        async def on_disconnect():
            """Handle bot disconnect event."""
            logger.warning("Bot disconnected from Discord")
        
        @bot.event
        async def on_resumed():
            """Handle bot resume event."""
            logger.info("Bot connection resumed")
        
        @bot.event
        async def on_error(event, *args, **kwargs):
            """Handle Discord.py errors.
            
            Requirements 4.2: Proper error logging for debugging.
            """
            logger.error(f"Discord.py error in event '{event}': {args}")
            import traceback
            logger.error(traceback.format_exc())
        
        @bot.event
        async def on_message(message):
            """Handle incoming messages with comprehensive error handling.
            
            Requirements 4.2: Proper error logging for debugging.
            """
            try:
                # Route all non-bot messages through message router (no prefix commands)
                # All commands are now handled via slash commands
                if message.author != bot.user:
                    try:
                        response = await self.message_router.route_message(message)
                        
                        # Send text response with proper audio coordination (Requirement 4.4)
                        if response.text_response:
                            try:
                                # Prepare text response with audio indicator (Requirement 4.4)
                                text_to_send = response.text_response
                                
                                # Add audio indicator when both text and voice responses are sent (Requirement 4.4)
                                if response.should_play_audio and response.audio_response and response.audio_response.success:
                                    text_to_send += " 🎤"  # Indicate audio was successfully played
                                    logger.debug("Added audio success indicator to text response")
                                elif response.audio_response and not response.audio_response.success:
                                    # TTS generation attempted but failed - add failure indicator (Requirement 4.5)
                                    text_to_send += " ⚠️"  # Indicate audio generation failed
                                    logger.debug("Added audio failure indicator to text response")
                                elif self.bot_manager.is_in_voice_channel() and not self.tts_engine.is_ready():
                                    # In voice channel but TTS not ready
                                    text_to_send += " 🔇"  # Indicate TTS unavailable
                                    logger.debug("Added TTS unavailable indicator to text response")
                                
                                await message.reply(text_to_send, mention_author=True)
                                
                            except nextcord.HTTPException as http_error:
                                logger.error(f"HTTP error sending message reply: {http_error}")
                                # Try sending without reply if reply fails
                                try:
                                    await message.channel.send(response.text_response)
                                except Exception as fallback_error:
                                    logger.error(f"Failed to send fallback message: {fallback_error}")
                                    
                            except nextcord.Forbidden:
                                logger.error("Bot lacks permission to send messages in this channel")
                                
                            except Exception as send_error:
                                logger.error(f"Error sending message reply: {send_error}")
                        
                    except Exception as route_error:
                        logger.error(f"Error routing message: {route_error}")
                        # Try to send an error message to the user
                        try:
                            if message.author != bot.user:  # Don't reply to ourselves
                                await message.reply("Sorry, I encountered an error processing your message.", mention_author=True)
                        except:
                            pass  # If we can't send error message, just log it
                            
            except Exception as message_error:
                logger.error(f"Unexpected error in on_message handler: {message_error}")
                # Don't try to send a message here as it might cause recursion
        
        # Command error handler removed - bot now uses slash commands only
        # Slash command errors are handled within the SlashCommandHandler class
        
        # Legacy prefix commands have been removed - bot now uses slash commands only
        # All command functionality is available through slash commands:
        # /join, /play, /leave, /help, /health
            try:
                # Get system health summary
                health_summary = health_monitor.get_system_health_summary()
                
                # Create detailed health report
                embed = nextcord.Embed(
                    title="🏥 System Health Report",
                    color=0x00ff00 if health_summary['overall_health'] == 'HEALTHY' else 
                          0xff9900 if health_summary['overall_health'] == 'DEGRADED' else 0xff0000
                )
                
                # Overall health
                embed.add_field(
                    name="Overall Health",
                    value=f"**{health_summary['overall_health']}**",
                    inline=False
                )
                
                # Component summary
                embed.add_field(
                    name="Components",
                    value=(
                        f"✅ Healthy: {health_summary['healthy']}\n"
                        f"⚠️ Degraded: {health_summary['degraded']}\n"
                        f"❌ Failed: {health_summary['failed']}"
                    ),
                    inline=True
                )
                
                # Feature availability
                features_status = []
                for feature in ["voice_generation", "audio_playback", "bot_commands", "bot_responses"]:
                    status = degradation_manager.get_feature_status(feature)
                    icon = "✅" if status == "NORMAL" else "⚠️" if status == "DEGRADED" else "❌"
                    features_status.append(f"{icon} {feature.replace('_', ' ').title()}: {status}")
                
                embed.add_field(
                    name="Features",
                    value="\n".join(features_status),
                    inline=True
                )
                
                # Add timestamp
                embed.timestamp = nextcord.utils.utcnow()
                embed.set_footer(text="Health check performed")
                
                await ctx.send(embed=embed)
                
            except Exception as e:
                logger.error(f"Error in health command: {e}")
                await ctx.send("❌ Error retrieving health information.")
    
    async def start(self) -> bool:
        """Start the bot application with comprehensive error handling.
        
        Requirements 4.1, 4.2: Graceful fallback and proper error logging.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        try:
            logger.info("Starting SecondShiftAugie bot...")
            logger.info(f"Python version: {sys.version}")
            logger.info(f"Platform: {sys.platform}")
            
            # Load configuration with detailed error reporting
            logger.info("Loading configuration...")
            if not self.load_configuration():
                logger.error("Failed to load configuration - cannot continue")
                logger.error("Please check your .env file and environment variables")
                return False
            
            logger.info("Configuration loaded successfully")
            logger.info("Bot will use slash commands only (no prefix commands)")
            logger.info(f"Target channel ID: {self.config.channel_id}")
            
            # Validate startup requirements (non-blocking for graceful degradation)
            logger.info("Validating startup requirements...")
            requirements_valid = self.validate_startup_requirements()
            if not requirements_valid:
                logger.warning("Startup validation failed - continuing with limited functionality")
                logger.warning("VoxCPM features will be disabled, but basic Discord functionality will work")
            else:
                logger.info("All startup requirements validated successfully")
            
            # Initialize components with error handling
            logger.info("Initializing bot components...")
            if not await self.initialize_components():
                logger.error("Failed to initialize critical components - cannot continue")
                return False
            
            logger.info("All components initialized successfully")
            
            # Start the Discord bot with connection retry logic
            logger.info("Connecting to Discord...")
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    await self.bot_manager.start()
                    logger.info("Successfully connected to Discord")
                    return True
                    
                except nextcord.LoginFailure as login_error:
                    logger.error(f"Discord login failed: {login_error}")
                    logger.error("Please check your bot token in the .env file")
                    return False
                    
                except nextcord.HTTPException as http_error:
                    logger.error(f"Discord HTTP error (attempt {attempt + 1}/{max_retries}): {http_error}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error("Max retries exceeded - giving up")
                        return False
                        
                except Exception as connect_error:
                    logger.error(f"Unexpected connection error (attempt {attempt + 1}/{max_retries}): {connect_error}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error("Max retries exceeded - giving up")
                        return False
            
            return False
            
        except KeyboardInterrupt:
            logger.info("Startup interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting bot: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def stop(self):
        """Stop the bot application and cleanup resources."""
        try:
            logger.info("Stopping SecondShiftAugie bot...")
            
            # Stop Discord bot
            if self.bot_manager:
                await self.bot_manager.stop()
            
            # Cleanup AI components
            if self.ollama_engine:
                await self.ollama_engine.cleanup()
                logger.info("Ollama engine cleaned up")
            
            if self.system_prompt_manager:
                self.system_prompt_manager.cleanup()
                logger.info("System prompt manager cleaned up")
            
            # Cleanup TTS engine
            if self.tts_engine:
                await self.tts_engine.cleanup()
            
            # Cleanup audio files and stop queue processor
            if self.audio_manager:
                await self.audio_manager.stop_queue_processor()
                await self.audio_manager.cleanup_old_files(max_age_hours=1)
            
            self._shutdown_event.set()
            logger.info("Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
    
    async def run(self):
        """Run the bot application with comprehensive error handling and monitoring."""
        try:
            logger.info("Starting bot application run cycle...")
            
            # Start the bot
            success = await self.start()
            if not success:
                logger.error("Failed to start bot - exiting")
                health_monitor.update_component_state("main_app", ComponentState.FAILED)
                return
            
            logger.info("Bot started successfully - entering main loop")
            health_monitor.update_component_state("main_app", ComponentState.HEALTHY)
            
            # Start comprehensive health monitoring service
            await health_monitoring_service.start_monitoring()
            
            # Start periodic health monitoring (legacy)
            health_task = asyncio.create_task(self._periodic_health_check())
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())
            
            try:
                # Wait for shutdown signal or health task completion
                done, pending = await asyncio.wait(
                    [shutdown_task, health_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                if self._shutdown_requested:
                    logger.info("Shutdown requested - stopping bot")
                else:
                    logger.info("Main loop completed")
                    
            except Exception as loop_error:
                logger.error(f"Error in main loop: {loop_error}")
                health_monitor.update_component_state("main_app", ComponentState.FAILED)
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self._shutdown_requested = True
        except Exception as e:
            logger.error(f"Unexpected error in run method: {e}")
            health_monitor.update_component_state("main_app", ComponentState.FAILED)
            import traceback
            logger.error(traceback.format_exc())
        finally:
            logger.info("Initiating bot shutdown...")
            
            # Stop health monitoring service
            try:
                await health_monitoring_service.stop_monitoring()
            except Exception as e:
                logger.error(f"Error stopping health monitoring: {e}")
            
            await self.stop()
    
    async def _periodic_health_check(self):
        """Perform periodic health checks and component monitoring."""
        check_interval = 300  # 5 minutes
        
        while not self._shutdown_requested:
            try:
                await asyncio.sleep(check_interval)
                
                if self._shutdown_requested:
                    break
                
                logger.debug("Performing periodic health check...")
                
                # Check component health
                await self._check_component_health()
                
                # Log health summary
                health_summary = health_monitor.get_system_health_summary()
                logger.info(f"Health check: {health_summary['overall_health']} "
                          f"({health_summary['healthy']}H/{health_summary['degraded']}D/{health_summary['failed']}F)")
                
            except asyncio.CancelledError:
                logger.debug("Health check task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic health check: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _check_component_health(self):
        """Check the health of all components including AI systems.
        
        Requirement 2.4, 2.5: Add AI component health monitoring to periodic health checks
        """
        try:
            # Check Ollama AI engine (Requirement 2.4: health monitoring)
            if self.ollama_engine:
                try:
                    ollama_healthy = await self.ollama_engine.health_check()
                    if ollama_healthy:
                        health_monitor.update_component_state("ollama_engine", ComponentState.HEALTHY)
                        # Re-enable AI features if they were disabled
                        if not degradation_manager.is_feature_available("ai_responses"):
                            degradation_manager.enable_feature("ai_responses")
                            logger.info("AI responses re-enabled after successful health check")
                    else:
                        health_monitor.update_component_state("ollama_engine", ComponentState.FAILED)
                        # Disable AI features if health check fails
                        if degradation_manager.is_feature_available("ai_responses"):
                            degradation_manager.disable_feature("ai_responses", "Ollama health check failed")
                            logger.warning("AI responses disabled due to health check failure")
                except Exception as e:
                    logger.warning(f"Ollama health check failed: {e}")
                    health_monitor.update_component_state("ollama_engine", ComponentState.FAILED)
                    if degradation_manager.is_feature_available("ai_responses"):
                        degradation_manager.disable_feature("ai_responses", f"Ollama health check error: {str(e)}")
            
            # Check system prompt manager
            if self.system_prompt_manager:
                try:
                    # Simple check - verify current prompt is available
                    current_prompt = self.system_prompt_manager.get_current_prompt()
                    if current_prompt and len(current_prompt.strip()) > 0:
                        health_monitor.update_component_state("system_prompt_manager", ComponentState.HEALTHY)
                    else:
                        health_monitor.update_component_state("system_prompt_manager", ComponentState.DEGRADED)
                        logger.warning("System prompt manager has empty prompt")
                except Exception as e:
                    logger.warning(f"System prompt manager health check failed: {e}")
                    health_monitor.update_component_state("system_prompt_manager", ComponentState.FAILED)
            
            # Check TTS engine
            if self.tts_engine:
                if self.tts_engine.is_ready():
                    health_monitor.update_component_state("tts_engine", ComponentState.HEALTHY)
                else:
                    health_monitor.update_component_state("tts_engine", ComponentState.FAILED)
            
            # Check Discord bot manager
            if self.bot_manager:
                if self.bot_manager.is_ready():
                    health_monitor.update_component_state("discord_manager", ComponentState.HEALTHY)
                else:
                    health_monitor.update_component_state("discord_manager", ComponentState.DEGRADED)
            
            # Check audio manager queue
            if self.audio_manager:
                # Simple health check - if queue processor is running
                if (self.audio_manager._queue_processor_task and 
                    not self.audio_manager._queue_processor_task.done()):
                    health_monitor.update_component_state("audio_manager", ComponentState.HEALTHY)
                else:
                    health_monitor.update_component_state("audio_manager", ComponentState.DEGRADED)
                    logger.warning("Audio queue processor not running - attempting restart")
                    try:
                        self.audio_manager._start_queue_processor()
                    except Exception as e:
                        logger.error(f"Failed to restart audio queue processor: {e}")
            
        except Exception as e:
            logger.error(f"Error checking component health: {e}")


async def main():
    """Main entry point for the application."""
    # Create and run the bot application
    bot_app = SecondShiftAugieBot()
    
    try:
        await bot_app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Handle Windows event loop policy
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run the application
    asyncio.run(main())