"""
Example usage of AudioManager for VoxCPM TTS integration.
This demonstrates how to use the AudioManager in the Discord bot context.
"""

import asyncio
import os
from audio_manager import AudioManager


async def example_usage():
    """Example of how to use AudioManager."""
    
    # Initialize with save path from environment or default
    save_path = os.getenv('SAVE_PATH', './temp_audio')
    audio_manager = AudioManager(save_path)
    
    # Example: Save generated audio from VoxCPM
    # (In real usage, this would come from VoxCPM TTS engine)
    fake_audio_data = b"example_audio_data_from_voxcpm"
    response_text = "Hello! This is a test response."
    
    # Save the audio file
    audio_path = await audio_manager.save_generated_audio(fake_audio_data, response_text)
    print(f"Audio saved to: {audio_path}")
    
    # Get last audio for replay functionality
    last_audio = audio_manager.get_last_audio_path()
    print(f"Last audio available at: {last_audio}")
    
    # Check storage info
    storage_info = audio_manager.get_storage_info()
    print(f"Storage info: {storage_info}")
    
    # Example: Play in voice channel (requires bot_manager)
    # if bot_manager and bot_manager.is_in_voice_channel():
    #     success = await audio_manager.play_in_voice_channel(bot_manager, audio_path)
    #     print(f"Audio playback success: {success}")
    
    # Cleanup old files (run periodically)
    deleted_count = await audio_manager.cleanup_old_files(max_age_hours=24)
    print(f"Cleaned up {deleted_count} old files")


if __name__ == "__main__":
    asyncio.run(example_usage())