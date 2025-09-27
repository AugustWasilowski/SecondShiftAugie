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
        self.tts_engine: Optional[VoxCPMEngine] = None
        self.bot_manager: Optional[DiscordBotManager] = None
        self.audio_manager: Optional[AudioManager] = None
        self.message_router: Optional[MessageRouter] = None
        self.bot_commands: Optional[BotCommands] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info("SecondShiftAugie bot application initialized")
    
    def load_configuration(self) -> bool:
        """Load configuration from environment variables.
        
        Returns:
            bool: True if configuration loaded successfully, False otherwise
        """
        try:
            # Load environment variables from .env file
            load_dotenv()
            
            # Validate required environment variables
            required_vars = ['BOT_TOKEN', 'CHANNEL_ID']
            missing_vars = []
            
            for var in required_vars:
                if not os.getenv(var):
                    missing_vars.append(var)
            
            if missing_vars:
                logger.error(f"Missing required environment variables: {missing_vars}")
                return False
            
            # Load bot configuration
            try:
                self.config = BotConfig(
                    token=os.getenv('BOT_TOKEN'),
                    channel_id=int(os.getenv('CHANNEL_ID')),
                    voice_channel_id=int(os.getenv('VOICE_CHANNEL_ID')) if os.getenv('VOICE_CHANNEL_ID') else None,
                    save_path=os.getenv('SAVE_PATH', './temp_audio'),
                    command_prefix=os.getenv('COMMAND_PREFIX', '!')
                )
                logger.info("Bot configuration loaded successfully")
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid bot configuration: {e}")
                return False
            
            # Load TTS configuration
            self.tts_config = TTSConfig(
                model_path=os.getenv('VOXCPM_MODEL_PATH', 'openbmb/VoxCPM-0.5B'),
                prompt_wav_path=os.getenv('VOXCPM_PROMPT_WAV', 'assets/model.wav'),
                prompt_text_path=os.getenv('VOXCPM_PROMPT_TEXT', 'assets/transcript.txt'),
                cfg_value=float(os.getenv('VOXCPM_CFG_VALUE', '2.0')),
                inference_timesteps=int(os.getenv('VOXCPM_INFERENCE_STEPS', '10')),
                normalize=os.getenv('VOXCPM_NORMALIZE', 'true').lower() == 'true',
                denoise=os.getenv('VOXCPM_DENOISE', 'true').lower() == 'true',
                max_length=int(os.getenv('VOXCPM_MAX_LENGTH', '4096')),
                save_path=self.config.save_path
            )
            logger.info("TTS configuration loaded successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False
    
    def validate_startup_requirements(self) -> bool:
        """Validate startup requirements including reference files.
        
        Requirement 4.3: Validate reference files exist and log errors if missing
        
        Returns:
            bool: True if all requirements are met, False otherwise
        """
        try:
            # Check if reference audio file exists
            if not os.path.exists(self.tts_config.prompt_wav_path):
                logger.error(f"Reference audio file not found: {self.tts_config.prompt_wav_path}")
                logger.error("VoxCPM will be disabled - voice generation not available")
                return False
            
            # Check if reference text file exists
            if not os.path.exists(self.tts_config.prompt_text_path):
                logger.error(f"Reference text file not found: {self.tts_config.prompt_text_path}")
                logger.error("VoxCPM will be disabled - voice generation not available")
                return False
            
            # Validate reference text file is not empty
            try:
                with open(self.tts_config.prompt_text_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        logger.error("Reference text file is empty")
                        logger.error("VoxCPM will be disabled - voice generation not available")
                        return False
            except Exception as e:
                logger.error(f"Error reading reference text file: {e}")
                return False
            
            # Ensure save directory exists
            os.makedirs(self.tts_config.save_path, exist_ok=True)
            
            logger.info("Startup requirements validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Error validating startup requirements: {e}")
            return False
    
    async def initialize_components(self) -> bool:
        """Initialize all bot components.
        
        Returns:
            bool: True if all components initialized successfully, False otherwise
        """
        try:
            # Initialize audio manager first (no dependencies)
            logger.info("Initializing audio manager...")
            self.audio_manager = AudioManager(self.config.save_path)
            
            # Initialize VoxCPM TTS engine
            logger.info("Initializing VoxCPM TTS engine...")
            self.tts_engine = VoxCPMEngine(self.tts_config)
            
            # Attempt to initialize VoxCPM (Requirement 4.1: graceful fallback)
            tts_ready = await self.tts_engine.initialize()
            if not tts_ready:
                logger.warning("VoxCPM TTS engine failed to initialize - continuing in text-only mode")
                logger.warning("Voice responses will not be available")
            else:
                logger.info("VoxCPM TTS engine initialized successfully")
            
            # Initialize Discord bot manager
            logger.info("Initializing Discord bot manager...")
            self.bot_manager = DiscordBotManager(self.config)
            
            # Initialize message router
            logger.info("Initializing message router...")
            self.message_router = MessageRouter(
                self.tts_engine,
                self.audio_manager,
                self.bot_manager
            )
            
            # Initialize command system
            logger.info("Initializing command system...")
            self.bot_commands = BotCommands(
                self.bot_manager,
                self.tts_engine,
                self.audio_manager
            )
            
            # Set up Discord bot event handlers and commands
            self._setup_discord_handlers()
            
            logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
            return False
    
    def _setup_discord_handlers(self):
        """Set up Discord bot event handlers and commands."""
        bot = self.bot_manager.bot
        
        # Event handlers
        @bot.event
        async def on_ready():
            """Handle bot ready event."""
            logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
            
            # Set bot status
            activity = nextcord.Activity(
                type=nextcord.ActivityType.listening,
                name="voice commands | !help"
            )
            await bot.change_presence(
                status=nextcord.Status.online,
                activity=activity
            )
            
            # Send startup message to configured channel
            try:
                channel = bot.get_channel(self.config.channel_id)
                if channel:
                    startup_msg = (
                        "🤖 **SecondShiftAugie** reporting for duty!\n"
                        f"🎤 VoxCPM TTS: {'✅ Ready' if self.tts_engine.is_ready() else '❌ Disabled'}\n"
                        "💬 Mention me for responses, use `!help` for commands!"
                    )
                    await channel.send(startup_msg)
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")
        
        @bot.event
        async def on_message(message):
            """Handle incoming messages."""
            # Process commands first
            await bot.process_commands(message)
            
            # Route non-command messages through message router
            if not message.content.startswith(self.config.command_prefix):
                response = await self.message_router.route_message(message)
                
                # Send text response if available
                if response.text_response:
                    await message.reply(response.text_response, mention_author=True)
        
        @bot.event
        async def on_command_error(ctx, error):
            """Handle command errors."""
            if isinstance(error, commands.CommandNotFound):
                await ctx.send(f"❌ Unknown command. Use `{self.config.command_prefix}help` for available commands.")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ Missing required argument. Use `{self.config.command_prefix}help` for usage.")
            else:
                logger.error(f"Command error: {error}")
                await ctx.send("❌ An error occurred while processing the command.")
        
        # Register commands
        @bot.command(name='join')
        async def join_cmd(ctx):
            """Join user's voice channel."""
            await self.bot_commands.join_command(ctx)
        
        @bot.command(name='play')
        async def play_cmd(ctx):
            """Replay last generated audio."""
            await self.bot_commands.play_command(ctx)
        
        @bot.command(name='leave')
        async def leave_cmd(ctx):
            """Leave current voice channel."""
            await self.bot_commands.leave_command(ctx)
        
        @bot.command(name='help')
        async def help_cmd(ctx):
            """Show help message."""
            await self.bot_commands.help_command(ctx)
        
        @bot.command(name='status')
        async def status_cmd(ctx):
            """Show bot status."""
            await self.bot_commands.status_command(ctx)
    
    async def start(self) -> bool:
        """Start the bot application.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        try:
            logger.info("Starting SecondShiftAugie bot...")
            
            # Load configuration
            if not self.load_configuration():
                logger.error("Failed to load configuration")
                return False
            
            # Validate startup requirements
            if not self.validate_startup_requirements():
                logger.warning("Startup validation failed - continuing with limited functionality")
            
            # Initialize components
            if not await self.initialize_components():
                logger.error("Failed to initialize components")
                return False
            
            # Start the Discord bot
            logger.info("Starting Discord bot...")
            await self.bot_manager.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            return False
    
    async def stop(self):
        """Stop the bot application and cleanup resources."""
        try:
            logger.info("Stopping SecondShiftAugie bot...")
            
            # Stop Discord bot
            if self.bot_manager:
                await self.bot_manager.stop()
            
            # Cleanup TTS engine
            if self.tts_engine:
                await self.tts_engine.cleanup()
            
            # Cleanup audio files
            if self.audio_manager:
                await self.audio_manager.cleanup_old_files(max_age_hours=1)
            
            self._shutdown_event.set()
            logger.info("Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
    
    async def run(self):
        """Run the bot application with proper error handling."""
        try:
            # Start the bot
            success = await self.start()
            if not success:
                logger.error("Failed to start bot")
                return
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            await self.stop()


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