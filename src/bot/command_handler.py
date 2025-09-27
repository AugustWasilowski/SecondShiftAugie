"""
Command Handler for VoxCPM Discord Bot

Integrates BotCommands with Discord.py command framework and handles
command registration and execution with proper error handling.
"""

import logging
from typing import TYPE_CHECKING

import nextcord
from nextcord.ext import commands

from .commands import BotCommands

if TYPE_CHECKING:
    from .discord_manager import DiscordBotManager
    from ..tts.voxcpm_engine import VoxCPMEngine
    from ..audio.audio_manager import AudioManager

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles Discord bot command registration and execution."""
    
    def __init__(
        self,
        bot: commands.Bot,
        bot_manager: "DiscordBotManager",
        tts_engine: "VoxCPMEngine", 
        audio_manager: "AudioManager"
    ):
        """Initialize command handler.
        
        Args:
            bot: Discord bot instance
            bot_manager: Discord bot manager
            tts_engine: VoxCPM TTS engine
            audio_manager: Audio manager
        """
        self.bot = bot
        self.bot_commands = BotCommands(bot_manager, tts_engine, audio_manager)
        
        # Register commands
        self._register_commands()
        
        logger.info("CommandHandler initialized and commands registered")
    
    def _register_commands(self):
        """Register all bot commands with the Discord bot."""
        
        @self.bot.command(name='join', help='Join your current voice channel')
        async def join(ctx):
            """Join command wrapper."""
            await self.bot_commands.join_command(ctx)
        
        @self.bot.command(name='play', help='Replay the last generated voice response')
        async def play(ctx):
            """Play command wrapper."""
            await self.bot_commands.play_command(ctx)
        
        @self.bot.command(name='help', help='Show bot commands and features')
        async def help_cmd(ctx):
            """Help command wrapper."""
            await self.bot_commands.help_command(ctx)
        
        @self.bot.command(name='status', help='Show bot and TTS engine status')
        async def status(ctx):
            """Status command wrapper."""
            await self.bot_commands.status_command(ctx)
        
        @self.bot.command(name='leave', help='Leave the current voice channel')
        async def leave(ctx):
            """Leave command wrapper."""
            await self.bot_commands.leave_command(ctx)
        
        # Override default help command to use our custom one
        self.bot.remove_command('help')
        
        logger.info("All commands registered successfully")
    
    def get_command_list(self) -> list:
        """Get list of available commands.
        
        Returns:
            list: List of command names
        """
        return ['join', 'play', 'help', 'status', 'leave']