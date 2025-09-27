#!/usr/bin/env python3
"""Basic test for VoxCPM engine without model loading."""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from tts.config import TTSConfig, AudioResponse
from tts.voxcpm_engine import VoxCPMEngine

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_basic_functionality():
    """Test basic VoxCPM engine functionality without model loading."""
    
    logger.info("Testing VoxCPM engine basic functionality...")
    
    # Test configuration creation
    config = TTSConfig(
        model_path="openbmb/VoxCPM-0.5B",
        prompt_wav_path="assets/model.wav",
        prompt_text_path="assets/transcript.txt",
        save_path="./temp_audio"
    )
    
    logger.info("✓ TTSConfig created successfully")
    logger.info(f"  Model path: {config.model_path}")
    logger.info(f"  Prompt wav: {config.prompt_wav_path}")
    logger.info(f"  Prompt text: {config.prompt_text_path}")
    logger.info(f"  Save path: {config.save_path}")
    
    # Test engine creation
    engine = VoxCPMEngine(config)
    logger.info("✓ VoxCPMEngine created successfully")
    
    # Test is_ready before initialization
    if not engine.is_ready():
        logger.info("✓ Engine correctly reports not ready before initialization")
    else:
        logger.error("✗ Engine should not be ready before initialization")
        return False
    
    # Test file validation
    if os.path.exists(config.prompt_wav_path):
        logger.info("✓ Reference audio file exists")
    else:
        logger.error("✗ Reference audio file missing")
        return False
    
    if os.path.exists(config.prompt_text_path):
        logger.info("✓ Reference text file exists")
    else:
        logger.error("✗ Reference text file missing")
        return False
    
    # Test save directory creation
    if os.path.exists(config.save_path):
        logger.info("✓ Save directory exists or was created")
    else:
        logger.error("✗ Save directory not created")
        return False
    
    # Test AudioResponse creation
    response = AudioResponse(
        text="test",
        audio_path=None,
        generation_time=0.0,
        success=False,
        error_message="test error"
    )
    logger.info("✓ AudioResponse created successfully")
    
    # Test error handling for uninitialized engine
    response = await engine.generate_speech("test text")
    if not response.success and "not initialized" in response.error_message:
        logger.info("✓ Uninitialized engine error handling works correctly")
    else:
        logger.error("✗ Uninitialized engine should return error")
        return False
    
    # Test empty text handling
    response = await engine.generate_speech("")
    if not response.success and "Empty text" in response.error_message:
        logger.info("✓ Empty text error handling works correctly")
    else:
        logger.error("✗ Empty text should return error")
        return False
    
    logger.info("✓ All basic functionality tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    if success:
        logger.info("🎉 Basic tests completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Basic tests failed!")
        sys.exit(1)