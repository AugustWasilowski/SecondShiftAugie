"""
Audio Manager for VoxCPM TTS Integration

Handles audio file storage, cleanup, and tracking for the Discord bot.
Provides functionality to save generated audio files with unique names,
track the last generated file for replay, and implement cleanup to prevent
disk space issues. Includes audio queuing for handling multiple simultaneous requests.
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..bot.discord_manager import DiscordBotManager

logger = logging.getLogger(__name__)


class AudioManager:
    """Manages audio file storage and lifecycle for VoxCPM generated audio."""
    
    def __init__(self, save_path: str):
        """
        Initialize the AudioManager.
        
        Args:
            save_path: Directory path where audio files will be saved
        """
        self.save_path = Path(save_path)
        self.last_audio_path: Optional[str] = None
        
        # Audio playback queue for handling multiple simultaneous requests (Requirement 2.4)
        self._audio_queue = asyncio.Queue()
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._is_processing = False
        
        # Create save directory if it doesn't exist
        self.save_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"AudioManager initialized with save path: {self.save_path}")
        
        # Start the audio queue processor
        self._start_queue_processor()
    
    async def save_generated_audio(self, audio_data: bytes, text_content: str = "") -> str:
        """
        Save generated audio data to a file with a unique name.
        
        Args:
            audio_data: The audio data bytes to save
            text_content: Optional text content for filename reference
            
        Returns:
            str: Path to the saved audio file
            
        Raises:
            OSError: If file cannot be written
        """
        try:
            # Generate unique filename with timestamp and UUID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            
            # Create safe filename from text content (first 20 chars, alphanumeric only)
            safe_text = ""
            if text_content:
                safe_text = "".join(c for c in text_content[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_text = safe_text.replace(' ', '_')
                if safe_text:
                    safe_text = f"_{safe_text}"
            
            filename = f"voxcpm_{timestamp}_{unique_id}{safe_text}.wav"
            file_path = self.save_path / filename
            
            # Write audio data to file
            with open(file_path, 'wb') as f:
                f.write(audio_data)
            
            # Update last audio path for replay functionality
            self.last_audio_path = str(file_path)
            
            logger.info(f"Audio saved successfully: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")
            raise OSError(f"Could not save audio file: {e}")
    
    def get_last_audio_path(self) -> Optional[str]:
        """
        Get the path to the last generated audio file.
        
        Returns:
            Optional[str]: Path to last audio file, or None if no audio has been generated
        """
        if self.last_audio_path and os.path.exists(self.last_audio_path):
            return self.last_audio_path
        return None
    
    async def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up old audio files to prevent disk space issues.
        
        Args:
            max_age_hours: Maximum age in hours for files to keep (default: 24)
            
        Returns:
            int: Number of files deleted
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            deleted_count = 0
            
            # Iterate through all files in the save directory
            for file_path in self.save_path.glob("voxcpm_*.wav"):
                try:
                    # Get file modification time
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    # Delete if older than cutoff time
                    if file_mtime < cutoff_time:
                        # Don't delete the last audio file if it's still being tracked
                        if str(file_path) == self.last_audio_path:
                            logger.debug(f"Skipping deletion of last audio file: {file_path}")
                            continue
                            
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old audio file: {file_path}")
                        
                except Exception as e:
                    logger.warning(f"Could not delete file {file_path}: {e}")
                    continue
            
            if deleted_count > 0:
                logger.info(f"Cleanup completed: deleted {deleted_count} old audio files")
            else:
                logger.debug("Cleanup completed: no old files to delete")
                
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0
    
    def get_storage_info(self) -> dict:
        """
        Get information about current storage usage.
        
        Returns:
            dict: Storage information including file count and total size
        """
        try:
            audio_files = list(self.save_path.glob("voxcpm_*.wav"))
            file_count = len(audio_files)
            
            total_size = 0
            for file_path in audio_files:
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    continue
            
            return {
                "file_count": file_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "save_path": str(self.save_path),
                "last_audio_exists": self.get_last_audio_path() is not None
            }
            
        except Exception as e:
            logger.error(f"Error getting storage info: {e}")
            return {
                "file_count": 0,
                "total_size_bytes": 0,
                "total_size_mb": 0,
                "save_path": str(self.save_path),
                "last_audio_exists": False,
                "error": str(e)
            }
    
    def _start_queue_processor(self):
        """Start the audio queue processor task."""
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._queue_processor_task = asyncio.create_task(self._process_audio_queue())
            logger.info("Audio queue processor started")
    
    async def _process_audio_queue(self):
        """
        Process audio playback queue to handle multiple simultaneous requests.
        
        Implements Requirement 2.4: WHEN multiple audio requests are made simultaneously 
        THEN system SHALL queue them appropriately
        """
        logger.info("Audio queue processor running")
        
        while True:
            try:
                # Wait for audio playback request
                audio_request = await self._audio_queue.get()
                
                if audio_request is None:  # Shutdown signal
                    break
                
                bot_manager, audio_path, result_future = audio_request
                
                try:
                    # Process the audio playback request
                    success = await self._play_audio_immediate(bot_manager, audio_path)
                    result_future.set_result(success)
                    
                except Exception as e:
                    logger.error(f"Error processing queued audio request: {e}")
                    result_future.set_result(False)
                
                finally:
                    self._audio_queue.task_done()
                    
            except asyncio.CancelledError:
                logger.info("Audio queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in audio queue processor: {e}")
                await asyncio.sleep(1)  # Brief pause before continuing
    
    async def _play_audio_immediate(self, bot_manager: "DiscordBotManager", audio_path: str) -> bool:
        """
        Immediately play audio file without queuing.
        
        Args:
            bot_manager: Discord bot manager instance
            audio_path: Path to the audio file to play
            
        Returns:
            bool: True if audio was played successfully, False otherwise
        """
        try:
            if not os.path.exists(audio_path):
                logger.error(f"Audio file not found: {audio_path}")
                return False
            
            if not bot_manager.is_in_voice_channel():
                logger.warning("Bot is not in a voice channel, cannot play audio")
                return False
            
            # Wait for any currently playing audio to finish
            while bot_manager.is_playing_audio():
                await asyncio.sleep(0.1)
            
            success = await bot_manager.play_audio(audio_path)
            if success:
                logger.info(f"Successfully played queued audio: {audio_path}")
            else:
                logger.error(f"Failed to play queued audio: {audio_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error playing audio immediately: {e}")
            return False
    
    async def play_in_voice_channel(self, bot_manager: "DiscordBotManager", audio_path: str) -> bool:
        """
        Play audio file in Discord voice channel through the bot manager.
        
        Uses audio queuing to handle multiple simultaneous requests (Requirement 2.4).
        Implements comprehensive error handling for graceful degradation.
        
        Args:
            bot_manager: Discord bot manager instance
            audio_path: Path to the audio file to play
            
        Returns:
            bool: True if audio was played successfully, False otherwise
        """
        try:
            # Validate audio file exists and is accessible
            if not os.path.exists(audio_path):
                logger.error(f"Audio file not found: {audio_path}")
                return False
            
            # Check file size and format
            try:
                file_size = os.path.getsize(audio_path)
                if file_size == 0:
                    logger.error(f"Audio file is empty: {audio_path}")
                    return False
                if file_size > 100 * 1024 * 1024:  # 100MB limit
                    logger.error(f"Audio file too large ({file_size / 1024 / 1024:.1f}MB): {audio_path}")
                    return False
            except Exception as file_error:
                logger.error(f"Error checking audio file: {file_error}")
                return False
            
            # Validate bot manager state
            if not bot_manager:
                logger.error("Bot manager is None")
                return False
            
            if not bot_manager.is_in_voice_channel():
                logger.warning("Bot is not in a voice channel, cannot play audio")
                return False
            
            # Check if queue processor is running
            if not self._queue_processor_task or self._queue_processor_task.done():
                logger.warning("Audio queue processor not running, restarting...")
                self._start_queue_processor()
                # Give it a moment to start
                await asyncio.sleep(0.1)
            
            try:
                # Create a future to get the result with timeout
                result_future = asyncio.Future()
                
                # Add to queue for processing with timeout
                try:
                    await asyncio.wait_for(
                        self._audio_queue.put((bot_manager, audio_path, result_future)),
                        timeout=5.0
                    )
                    logger.debug(f"Added audio to queue: {os.path.basename(audio_path)}")
                except asyncio.TimeoutError:
                    logger.error("Timeout adding audio to queue - queue may be full")
                    return False
                
                # Wait for the result with timeout
                try:
                    success = await asyncio.wait_for(result_future, timeout=30.0)
                    return success
                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for audio playback result")
                    return False
                
            except Exception as queue_error:
                logger.error(f"Error with audio queue: {queue_error}")
                # Try direct playback as fallback
                logger.info("Attempting direct audio playback as fallback...")
                try:
                    return await self._play_audio_immediate(bot_manager, audio_path)
                except Exception as fallback_error:
                    logger.error(f"Fallback audio playback failed: {fallback_error}")
                    return False
            
        except Exception as e:
            logger.error(f"Unexpected error in play_in_voice_channel: {e}")
            return False
    
    async def stop_queue_processor(self):
        """Stop the audio queue processor."""
        if self._queue_processor_task and not self._queue_processor_task.done():
            # Send shutdown signal
            await self._audio_queue.put(None)
            
            try:
                await asyncio.wait_for(self._queue_processor_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Audio queue processor did not stop gracefully, cancelling")
                self._queue_processor_task.cancel()
                
            logger.info("Audio queue processor stopped")