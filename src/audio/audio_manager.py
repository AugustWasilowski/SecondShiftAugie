"""
Audio Manager for VoxCPM TTS Integration

Handles audio file storage, cleanup, and tracking for the Discord bot.
Provides functionality to save generated audio files with unique names,
track the last generated file for replay, and implement cleanup to prevent
disk space issues.
"""

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
        
        # Create save directory if it doesn't exist
        self.save_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"AudioManager initialized with save path: {self.save_path}")
    
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
    
    async def play_in_voice_channel(self, bot_manager: "DiscordBotManager", audio_path: str) -> bool:
        """
        Play audio file in Discord voice channel through the bot manager.
        
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
            
            success = await bot_manager.play_audio(audio_path)
            if success:
                logger.info(f"Successfully played audio: {audio_path}")
            else:
                logger.error(f"Failed to play audio: {audio_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error playing audio in voice channel: {e}")
            return False