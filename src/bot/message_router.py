"""
Message Router for VoxCPM TTS Integration

Handles routing of Discord messages and mentions, determines when to generate
voice responses, and coordinates between text responses and audio generation.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING
import nextcord
from nextcord.ext import commands

if TYPE_CHECKING:
    from ..tts.voxcpm_engine import VoxCPMEngine
    from ..audio.audio_manager import AudioManager
    from .discord_manager import DiscordBotManager

logger = logging.getLogger(__name__)


class MessageResponse:
    """Response data for processed messages."""
    
    def __init__(self, text_response: str, audio_response=None, should_play_audio: bool = False):
        self.text_response = text_response
        self.audio_response = audio_response
        self.should_play_audio = should_play_audio


class CommandResponse:
    """Response data for processed commands."""
    
    def __init__(self, success: bool, message: str, audio_played: bool = False):
        self.success = success
        self.message = message
        self.audio_played = audio_played


class ChatResponse:
    """Response data for chat interactions."""
    
    def __init__(self, text: str, audio_generated: bool = False, audio_played: bool = False):
        self.text = text
        self.audio_generated = audio_generated
        self.audio_played = audio_played


class MessageRouter:
    """Routes Discord messages and coordinates text/voice responses."""
    
    def __init__(self, tts_engine: "VoxCPMEngine", audio_manager: "AudioManager", bot_manager: "DiscordBotManager"):
        """
        Initialize the message router.
        
        Args:
            tts_engine: VoxCPM TTS engine for audio generation
            audio_manager: Audio manager for file operations
            bot_manager: Discord bot manager for voice operations
        """
        self.tts_engine = tts_engine
        self.audio_manager = audio_manager
        self.bot_manager = bot_manager
        self._logger = logging.getLogger(__name__)
    
    async def route_message(self, message: nextcord.Message) -> MessageResponse:
        """
        Route incoming Discord message to appropriate handler.
        
        Args:
            message: Discord message to process
            
        Returns:
            MessageResponse: Response containing text and audio information
        """
        try:
            # Skip messages from the bot itself
            if message.author == self.bot_manager.get_bot_user():
                return MessageResponse("", should_play_audio=False)
            
            # Check if message is a command (starts with command prefix)
            if message.content.startswith("!"):
                # Commands are handled separately, return empty response
                return MessageResponse("", should_play_audio=False)
            
            # Check if bot is mentioned in the message
            bot_user = self.bot_manager.get_bot_user()
            if bot_user and bot_user in message.mentions:
                return await self._handle_mention(message)
            
            # For non-mention messages, no response needed
            return MessageResponse("", should_play_audio=False)
            
        except Exception as e:
            self._logger.error(f"Error routing message: {e}")
            return MessageResponse("Sorry, I encountered an error processing your message.", should_play_audio=False)
    
    async def _handle_mention(self, message: nextcord.Message) -> MessageResponse:
        """
        Handle messages that mention the bot.
        
        Args:
            message: Discord message containing bot mention
            
        Returns:
            MessageResponse: Response with text and potential audio
        """
        try:
            # Extract the actual message content without the mention
            content = message.content
            bot_user = self.bot_manager.get_bot_user()
            
            if bot_user:
                # Remove bot mention from content
                content = content.replace(f"<@{bot_user.id}>", "").strip()
                content = content.replace(f"<@!{bot_user.id}>", "").strip()
            
            if not content:
                content = "Hello! How can I help you?"
            
            # Generate a simple response (in a real implementation, this would use AI)
            response_text = await self._generate_response(content, message.author.display_name)
            
            # Determine if we should generate and play audio
            should_generate_audio = self._should_generate_audio()
            audio_response = None
            
            if should_generate_audio and self.tts_engine.is_ready():
                # Generate audio for the response
                audio_response = await self.tts_engine.generate_speech(response_text)
                
                if audio_response.success and self.bot_manager.is_in_voice_channel():
                    # Play audio in voice channel
                    await self.audio_manager.play_in_voice_channel(
                        self.bot_manager, 
                        audio_response.audio_path
                    )
                    return MessageResponse(
                        text_response=response_text,
                        audio_response=audio_response,
                        should_play_audio=True
                    )
            
            return MessageResponse(
                text_response=response_text,
                audio_response=audio_response,
                should_play_audio=False
            )
            
        except Exception as e:
            self._logger.error(f"Error handling mention: {e}")
            return MessageResponse("Sorry, I had trouble processing your message.", should_play_audio=False)
    
    async def _generate_response(self, content: str, user_name: str) -> str:
        """
        Generate a text response to user input.
        
        Args:
            content: User message content
            user_name: Display name of the user
            
        Returns:
            str: Generated response text
        """
        # Simple response generation (in a real implementation, this would use AI/LLM)
        content_lower = content.lower()
        
        if any(greeting in content_lower for greeting in ["hello", "hi", "hey", "greetings"]):
            return f"Hello {user_name}! How can I assist you today?"
        
        elif any(question in content_lower for question in ["how are you", "how's it going", "what's up"]):
            return f"I'm doing great, {user_name}! Thanks for asking. How can I help you?"
        
        elif any(thanks in content_lower for thanks in ["thank", "thanks", "appreciate"]):
            return f"You're very welcome, {user_name}! Happy to help."
        
        elif any(goodbye in content_lower for goodbye in ["bye", "goodbye", "see you", "farewell"]):
            return f"Goodbye {user_name}! Have a great day!"
        
        elif "voice" in content_lower or "speak" in content_lower or "talk" in content_lower:
            if self.bot_manager.is_in_voice_channel():
                return f"I'm currently in a voice channel and can speak! Try mentioning me again to hear my voice."
            else:
                return f"I can speak when I'm in a voice channel! Use the !join command to have me join your voice channel."
        
        elif "help" in content_lower:
            return ("I'm SecondShiftAugie! I can respond with both text and voice. "
                   "Use !join to have me join your voice channel, then mention me to hear my responses!")
        
        else:
            # Generic response for other messages
            responses = [
                f"That's interesting, {user_name}! Tell me more.",
                f"I understand, {user_name}. What would you like to know?",
                f"Thanks for sharing that, {user_name}! How can I help?",
                f"I hear you, {user_name}. What can I do for you?",
                f"Got it, {user_name}! What else would you like to discuss?"
            ]
            # Simple hash-based selection for consistency
            response_index = hash(content) % len(responses)
            return responses[response_index]
    
    def _should_generate_audio(self) -> bool:
        """
        Determine if audio should be generated for the current context.
        
        Returns:
            bool: True if audio should be generated, False otherwise
        """
        # Generate audio if:
        # 1. TTS engine is ready
        # 2. Bot is in a voice channel (Requirement 2.1)
        return (self.tts_engine.is_ready() and 
                self.bot_manager.is_in_voice_channel())
    
    async def handle_command(self, ctx: commands.Context, command_name: str, *args) -> CommandResponse:
        """
        Handle Discord bot commands.
        
        Args:
            ctx: Discord command context
            command_name: Name of the command to execute
            *args: Command arguments
            
        Returns:
            CommandResponse: Response indicating command result
        """
        try:
            if command_name == "join":
                return await self._handle_join_command(ctx)
            
            elif command_name == "play":
                return await self._handle_play_command(ctx)
            
            elif command_name == "help":
                return await self._handle_help_command(ctx)
            
            elif command_name == "status":
                return await self._handle_status_command(ctx)
            
            else:
                return CommandResponse(
                    success=False,
                    message=f"Unknown command: {command_name}. Use !help for available commands."
                )
                
        except Exception as e:
            self._logger.error(f"Error handling command {command_name}: {e}")
            return CommandResponse(
                success=False,
                message="Sorry, I encountered an error processing that command."
            )
    
    async def _handle_join_command(self, ctx: commands.Context) -> CommandResponse:
        """Handle !join command to connect bot to user's voice channel."""
        try:
            # Check if user is in a voice channel
            if not ctx.author.voice or not ctx.author.voice.channel:
                return CommandResponse(
                    success=False,
                    message="You need to be in a voice channel for me to join!"
                )
            
            user_channel = ctx.author.voice.channel
            
            # Join the user's voice channel
            success = await self.bot_manager.join_voice_channel(user_channel.id)
            
            if success:
                # Play greeting audio if available
                greeting_path = "SecondShiftAugieReportingForDuty.mp3"
                audio_played = False
                
                if self.bot_manager.is_in_voice_channel():
                    try:
                        await self.bot_manager.play_audio(greeting_path)
                        audio_played = True
                    except Exception as e:
                        self._logger.warning(f"Could not play greeting audio: {e}")
                
                return CommandResponse(
                    success=True,
                    message=f"Joined {user_channel.name}! Mention me to hear my voice responses.",
                    audio_played=audio_played
                )
            else:
                return CommandResponse(
                    success=False,
                    message="Sorry, I couldn't join your voice channel. Please try again."
                )
                
        except Exception as e:
            self._logger.error(f"Error in join command: {e}")
            return CommandResponse(
                success=False,
                message="An error occurred while trying to join the voice channel."
            )
    
    async def _handle_play_command(self, ctx: commands.Context) -> CommandResponse:
        """Handle !play command to replay last generated audio."""
        try:
            if not self.bot_manager.is_in_voice_channel():
                return CommandResponse(
                    success=False,
                    message="I need to be in a voice channel to play audio. Use !join first!"
                )
            
            last_audio = self.audio_manager.get_last_audio_path()
            if not last_audio:
                return CommandResponse(
                    success=False,
                    message="No audio to replay. Mention me first to generate some audio!"
                )
            
            success = await self.audio_manager.play_in_voice_channel(
                self.bot_manager, 
                last_audio
            )
            
            if success:
                return CommandResponse(
                    success=True,
                    message="Replaying last audio response!",
                    audio_played=True
                )
            else:
                return CommandResponse(
                    success=False,
                    message="Sorry, I couldn't play the audio. Please try again."
                )
                
        except Exception as e:
            self._logger.error(f"Error in play command: {e}")
            return CommandResponse(
                success=False,
                message="An error occurred while trying to play audio."
            )
    
    async def _handle_help_command(self, ctx: commands.Context) -> CommandResponse:
        """Handle !help command to show available commands."""
        help_text = """
**SecondShiftAugie Commands:**

`!join` - Join your current voice channel
`!play` - Replay the last generated audio response
`!help` - Show this help message
`!status` - Show bot status and capabilities

**Voice Features:**
- Mention me (@SecondShiftAugie) to get voice responses when I'm in a voice channel
- I use VoxCPM TTS to generate speech with a consistent voice
- Audio is automatically played when I'm connected to voice
        """.strip()
        
        return CommandResponse(
            success=True,
            message=help_text
        )
    
    async def _handle_status_command(self, ctx: commands.Context) -> CommandResponse:
        """Handle !status command to show bot status."""
        try:
            # Gather status information
            tts_ready = self.tts_engine.is_ready()
            in_voice = self.bot_manager.is_in_voice_channel()
            voice_info = self.bot_manager.get_voice_channel_info()
            storage_info = self.audio_manager.get_storage_info()
            
            status_parts = [
                f"**Bot Status:**",
                f"🎤 TTS Engine: {'✅ Ready' if tts_ready else '❌ Not Ready'}",
                f"🔊 Voice Channel: {'✅ Connected' if in_voice else '❌ Not Connected'}"
            ]
            
            if voice_info:
                status_parts.append(f"📍 Current Channel: {voice_info['name']} ({voice_info['member_count']} members)")
            
            status_parts.extend([
                f"💾 Audio Files: {storage_info['file_count']} files ({storage_info['total_size_mb']} MB)",
                f"🎵 Last Audio: {'✅ Available' if storage_info['last_audio_exists'] else '❌ None'}"
            ])
            
            return CommandResponse(
                success=True,
                message="\n".join(status_parts)
            )
            
        except Exception as e:
            self._logger.error(f"Error in status command: {e}")
            return CommandResponse(
                success=False,
                message="Error retrieving status information."
            )
    
    async def handle_mention(self, message: nextcord.Message) -> ChatResponse:
        """
        Handle bot mentions and generate appropriate responses.
        
        Args:
            message: Discord message containing bot mention
            
        Returns:
            ChatResponse: Response with text and audio status
        """
        try:
            response = await self._handle_mention(message)
            
            return ChatResponse(
                text=response.text_response,
                audio_generated=response.audio_response is not None and response.audio_response.success,
                audio_played=response.should_play_audio
            )
            
        except Exception as e:
            self._logger.error(f"Error handling mention: {e}")
            return ChatResponse(
                text="Sorry, I encountered an error processing your mention.",
                audio_generated=False,
                audio_played=False
            )