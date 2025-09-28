"""
Message Router for VoxCPM TTS Integration with Ollama AI

Handles routing of Discord messages and mentions, determines when to generate
voice responses, and coordinates between text responses and audio generation.
Integrates with Ollama AI engine for intelligent response generation.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING
import nextcord
from nextcord.ext import commands

from src.utils.error_handler import ai_error_handler, degradation_manager

if TYPE_CHECKING:
    from ..tts.voxcpm_engine import VoxCPMEngine
    from ..audio.audio_manager import AudioManager
    from .discord_manager import DiscordBotManager
    from ..ai.ollama_engine import OllamaEngine

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
    """Routes Discord messages and coordinates text/voice responses with AI integration."""
    
    def __init__(self, tts_engine: "VoxCPMEngine", audio_manager: "AudioManager", bot_manager: "DiscordBotManager", ollama_engine: Optional["OllamaEngine"] = None):
        """
        Initialize the message router.
        
        Args:
            tts_engine: VoxCPM TTS engine for audio generation
            audio_manager: Audio manager for file operations
            bot_manager: Discord bot manager for voice operations
            ollama_engine: Optional Ollama AI engine for intelligent responses
        """
        self.tts_engine = tts_engine
        self.audio_manager = audio_manager
        self.bot_manager = bot_manager
        self.ollama_engine = ollama_engine
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
        Handle messages that mention the bot with integrated AI response pipeline.
        
        Implements requirements:
        - 4.1: Update message flow to pass AI responses to VoxCPM TTS engine
        - 4.2: Ensure proper coordination between text and audio responses
        - 4.4: Add audio indicator when both text and voice responses are sent
        - 4.5: Handle TTS failures gracefully with text-only fallback
        
        Args:
            message: Discord message containing bot mention
            
        Returns:
            MessageResponse: Response with text and potential audio coordination
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
            
            # Process through complete AI response pipeline (Requirements 4.1, 4.2, 4.4, 4.5)
            self._logger.info(f"Processing mention through AI response pipeline: '{content[:50]}...'")
            
            response = await self.process_ai_response_pipeline(content, message.author.display_name)
            
            # Log pipeline completion
            if response.should_play_audio:
                self._logger.info("Mention processed: AI response with audio delivered")
            elif response.audio_response:
                self._logger.info("Mention processed: AI response text-only (audio generation attempted)")
            else:
                self._logger.info("Mention processed: AI response text-only")
            
            return response
            
        except Exception as e:
            # Handle any unexpected errors in mention processing
            self._logger.error(f"Unexpected error processing mention: {e}")
            return MessageResponse(
                text_response="Sorry, I had trouble processing your message.", 
                should_play_audio=False
            )
    
    async def _generate_response(self, content: str, user_name: str) -> str:
        """
        Generate a text response to user input using AI when available.
        
        Implements requirements:
        - 1.1: Send message content to Ollama and receive AI response
        - 4.1: Generate AI responses for user messages
        - 6.3: Truncate responses appropriately for TTS
        - 6.5: Indicate when AI features are unavailable
        
        Args:
            content: User message content
            user_name: Display name of the user
            
        Returns:
            str: Generated response text optimized for TTS
        """
        # Try to use Ollama AI engine if available and ready
        if self.ollama_engine and self.ollama_engine.is_ready():
            try:
                self._logger.debug(f"Generating AI response for user {user_name}: '{content[:50]}...'")
                
                # Add user context optimized for voice synthesis
                context = (
                    f"The user's name is {user_name}. "
                    f"Respond in a friendly, conversational manner suitable for voice synthesis. "
                    f"Keep responses concise and natural-sounding for text-to-speech conversion."
                )
                
                # Generate AI response
                ai_response = await self.ollama_engine.generate_response(content, context)
                
                if ai_response.success:
                    # Validate and optimize response for TTS pipeline (Requirement 6.3)
                    validated_text, was_truncated = self._validate_and_truncate_response(ai_response.text)
                    
                    if was_truncated and not ai_response.truncated:
                        self._logger.info("AI response further truncated for TTS compatibility")
                    
                    self._logger.debug(f"AI response ready for TTS pipeline (AI truncated: {ai_response.truncated}, TTS truncated: {was_truncated})")
                    return validated_text
                else:
                    # AI generation failed, log and fall back (Requirement 6.5)
                    self._logger.warning(f"AI response generation failed: {ai_response.error_message}")
                    self._logger.debug("Falling back to simple response generation")
                    
            except Exception as e:
                # Unexpected error in AI generation
                self._logger.error(f"Unexpected error in AI response generation: {e}")
                self._logger.debug("Falling back to simple response generation")
        
        elif self.ollama_engine and not self.ollama_engine.is_ready():
            # AI engine exists but not ready (Requirement 6.5)
            self._logger.debug("Ollama engine not ready, using fallback responses")
        
        else:
            # No AI engine configured (Requirement 6.5)
            self._logger.debug("No Ollama engine configured, using simple response generation")
        
        # Fallback to simple response generation when AI is unavailable
        return self._generate_fallback_response(content, user_name)
    
    def _generate_fallback_response(self, content: str, user_name: str) -> str:
        """
        Generate a simple fallback response when AI is unavailable.
        
        Args:
            content: User message content
            user_name: Display name of the user
            
        Returns:
            str: Generated fallback response text
        """
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
    
    def is_ai_available(self) -> bool:
        """
        Check if AI functionality is available considering circuit breaker state.
        
        Implements requirement 6.5: Indicate when AI features are unavailable.
        
        Returns:
            bool: True if AI is available and ready, False otherwise
        """
        if not self.ollama_engine or not self.ollama_engine.is_ready():
            return False
        
        # Check circuit breaker state
        return ai_error_handler.should_use_ai()
    
    async def get_ai_status(self) -> dict:
        """
        Get detailed AI status information including circuit breaker status.
        
        Implements requirement 6.4: Detailed logging for AI interactions and errors.
        
        Returns:
            dict: AI status information including availability, health, and circuit breaker status
        """
        if not self.ollama_engine:
            return {
                "available": False,
                "ready": False,
                "healthy": False,
                "error": "AI engine not configured",
                "circuit_breakers": None,
                "degradation_active": True
            }
        
        try:
            # Get comprehensive AI health status
            ai_health_status = self.ollama_engine.get_ai_health_status()
            
            ready = self.ollama_engine.is_ready()
            
            # Perform basic health check if ready
            health_ok = False
            if ready:
                try:
                    health_ok = await self.ollama_engine.health_check()
                except Exception as e:
                    self._logger.warning(f"AI health check failed: {e}")
            
            return {
                "available": True,
                "ready": ready,
                "healthy": health_ok,
                "overall_health": ai_health_status.get("overall_health", "UNKNOWN"),
                "circuit_breakers": ai_health_status.get("circuit_breakers", {}),
                "error_counts": ai_health_status.get("error_counts", {}),
                "recent_error_rate": ai_health_status.get("recent_error_rate", 0),
                "degradation_active": ai_health_status.get("degradation_active", False),
                "error": None if ready and health_ok else "AI engine not ready or unhealthy"
            }
            
        except Exception as e:
            self._logger.error(f"Error getting AI status: {e}")
            return {
                "available": True,
                "ready": False,
                "healthy": False,
                "error": f"Status check failed: {str(e)[:50]}",
                "circuit_breakers": None,
                "degradation_active": True
            }
    
    async def process_ai_response_pipeline(self, content: str, user_name: str) -> MessageResponse:
        """
        Process complete AI response pipeline from text generation to audio playback.
        
        Implements requirements:
        - 4.1: Update message flow to pass AI responses to VoxCPM TTS engine
        - 4.2: Ensure proper coordination between text and audio responses
        - 4.4: Add audio indicator when both text and voice responses are sent
        - 4.5: Handle TTS failures gracefully with text-only fallback
        
        Args:
            content: User message content
            user_name: Display name of the user
            
        Returns:
            MessageResponse: Complete response with text and audio coordination
        """
        try:
            # Step 1: Generate AI response text
            response_text = await self._generate_response(content, user_name)
            
            # Step 2: Determine audio generation strategy
            should_attempt_audio = self._should_generate_audio()
            
            if not should_attempt_audio:
                # Text-only response - no audio generation needed
                self._logger.debug("Audio generation not attempted - returning text-only response")
                return MessageResponse(
                    text_response=response_text,
                    audio_response=None,
                    should_play_audio=False
                )
            
            # Step 3: Generate and coordinate audio response (Requirements 4.1, 4.2)
            self._logger.info("Processing AI response through TTS pipeline")
            
            try:
                # Generate TTS audio from AI response (Requirement 4.1)
                audio_response = await self.tts_engine.generate_speech(response_text)
                
                if audio_response.success and audio_response.audio_path:
                    # Step 4: Attempt audio playback (Requirement 4.2)
                    try:
                        audio_played = await self.audio_manager.play_in_voice_channel(
                            self.bot_manager, 
                            audio_response.audio_path
                        )
                        
                        if audio_played:
                            # Success: Both text and audio available (Requirement 4.4)
                            self._logger.info("AI response pipeline successful: text + audio")
                            return MessageResponse(
                                text_response=response_text,
                                audio_response=audio_response,
                                should_play_audio=True
                            )
                        else:
                            # Audio generation succeeded but playback failed (Requirement 4.5)
                            self._logger.warning("Audio generated but playback failed - text-only fallback")
                            return MessageResponse(
                                text_response=response_text,
                                audio_response=audio_response,  # Include for failure indicator
                                should_play_audio=False
                            )
                            
                    except Exception as playback_error:
                        # Audio playback error (Requirement 4.5)
                        self._logger.error(f"Audio playback error in pipeline: {playback_error}")
                        return MessageResponse(
                            text_response=response_text,
                            audio_response=audio_response,  # Include for failure indicator
                            should_play_audio=False
                        )
                
                else:
                    # TTS generation failed (Requirement 4.5)
                    self._logger.warning(f"TTS generation failed in pipeline: {audio_response.error_message if audio_response else 'Unknown error'}")
                    return MessageResponse(
                        text_response=response_text,
                        audio_response=audio_response,  # Include for failure indicator
                        should_play_audio=False
                    )
                    
            except Exception as tts_error:
                # TTS engine error (Requirement 4.5)
                self._logger.error(f"TTS engine error in pipeline: {tts_error}")
                return MessageResponse(
                    text_response=response_text,
                    audio_response=None,
                    should_play_audio=False
                )
        
        except Exception as e:
            # Pipeline error - return basic fallback
            self._logger.error(f"AI response pipeline error: {e}")
            return MessageResponse(
                text_response="Sorry, I encountered an error processing your message.",
                audio_response=None,
                should_play_audio=False
            )
    
    def _validate_and_truncate_response(self, response_text: str, max_length: int = 500) -> tuple[str, bool]:
        """
        Validate and truncate response text for TTS compatibility.
        
        Implements requirement 6.3: Truncate AI responses appropriately for TTS
        
        Args:
            response_text: Original response text
            max_length: Maximum allowed length for TTS
            
        Returns:
            tuple[str, bool]: (processed_text, was_truncated)
        """
        if not response_text:
            return "I'm sorry, I couldn't generate a response.", False
        
        # Remove excessive whitespace and newlines for better TTS
        cleaned_text = " ".join(response_text.split())
        
        # Remove problematic characters for TTS
        cleaned_text = cleaned_text.replace('\n', ' ').replace('\t', ' ')
        
        if len(cleaned_text) <= max_length:
            return cleaned_text, False
        
        # Truncate at sentence boundary if possible (better for TTS)
        sentences = cleaned_text.split('. ')
        truncated = ""
        
        for sentence in sentences:
            if len(truncated + sentence + '. ') <= max_length - 3:  # Leave room for "..."
                truncated += sentence + '. '
            else:
                break
        
        if truncated:
            result = truncated.rstrip() + "..."
            self._logger.info(f"Response truncated at sentence boundary for TTS: {len(cleaned_text)} -> {len(result)} chars")
            return result, True
        
        # If no complete sentences fit, truncate at word boundary
        words = cleaned_text.split()
        truncated = ""
        
        for word in words:
            if len(truncated + word + " ") <= max_length - 3:
                truncated += word + " "
            else:
                break
        
        result = truncated.rstrip() + "..."
        self._logger.info(f"Response truncated at word boundary for TTS: {len(cleaned_text)} -> {len(result)} chars")
        return result, True
    
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
        # Check if AI is available to customize help message
        ai_available = self.ollama_engine and self.ollama_engine.is_ready()
        
        help_text = """
**SecondShiftAugie Commands:**

`!join` - Join your current voice channel
`!play` - Replay the last generated audio response
`!help` - Show this help message
`!status` - Show bot status and capabilities

**Voice & AI Features:**
- Mention me (@SecondShiftAugie) to get intelligent AI responses
- I use VoxCPM TTS to generate speech with a consistent voice
- Audio is automatically played when I'm connected to voice"""
        
        if ai_available:
            help_text += "\n- AI-powered conversations using Ollama with Qwen2.5 model"
        else:
            help_text += "\n- AI features currently unavailable (using simple responses)"
        
        help_text = help_text.strip()
        
        return CommandResponse(
            success=True,
            message=help_text
        )
    
    async def _handle_status_command(self, ctx: commands.Context) -> CommandResponse:
        """
        Handle !status command to show bot status including AI capabilities.
        
        Implements requirements:
        - 3.5: Show bot status including AI capabilities
        - 6.4: Include AI status in health reporting
        - 6.5: Indicate when AI features are unavailable
        """
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
            
            # Add AI status information
            if self.ollama_engine:
                ai_ready = self.ollama_engine.is_ready()
                status_parts.append(f"🤖 AI Engine: {'✅ Ready' if ai_ready else '❌ Not Ready'}")
                
                # Test AI response generation if ready
                if ai_ready:
                    try:
                        test_response = await self.ollama_engine.generate_response("Hello", None)
                        if test_response.success:
                            status_parts.append(f"🧠 AI Response Test: ✅ Working")
                        else:
                            status_parts.append(f"🧠 AI Response Test: ⚠️ Failed ({test_response.error_message})")
                    except Exception as ai_error:
                        status_parts.append(f"🧠 AI Response Test: ❌ Error ({str(ai_error)[:50]})")
                else:
                    status_parts.append(f"🧠 AI Response Test: ❌ Engine Not Ready")
            else:
                status_parts.append(f"🤖 AI Engine: ❌ Not Configured")
            
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
    
    async def get_pipeline_status(self) -> dict:
        """
        Get comprehensive status of the AI response pipeline.
        
        Returns:
            dict: Pipeline status including all components
        """
        try:
            # Get AI status
            ai_status = await self.get_ai_status()
            
            # Get TTS status
            tts_status = {
                "ready": self.tts_engine.is_ready(),
                "available": self.tts_engine is not None
            }
            
            # Get voice channel status
            voice_status = {
                "connected": self.bot_manager.is_in_voice_channel(),
                "info": self.bot_manager.get_voice_channel_info() if self.bot_manager.is_in_voice_channel() else None
            }
            
            # Get audio manager status
            audio_status = self.audio_manager.get_storage_info()
            
            # Determine pipeline capabilities
            can_generate_text = ai_status.get("ready", False) or True  # Fallback always available
            can_generate_audio = tts_status["ready"] and voice_status["connected"]
            
            return {
                "ai": ai_status,
                "tts": tts_status,
                "voice": voice_status,
                "audio": audio_status,
                "capabilities": {
                    "text_responses": can_generate_text,
                    "audio_responses": can_generate_audio,
                    "ai_powered": ai_status.get("ready", False)
                },
                "pipeline_ready": can_generate_text  # Pipeline is ready if we can at least generate text
            }
            
        except Exception as e:
            self._logger.error(f"Error getting pipeline status: {e}")
            return {
                "error": str(e),
                "pipeline_ready": False
            }