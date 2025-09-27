#!/usr/bin/env python3
"""Test script for VoxCPM engine functionality."""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from tts.config import TTSConfig
from tts.voxcpm_engine import VoxCPMEngine

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_voxcpm_engine():
    """Test VoxCPM engine initialization and generation."""
    
    # Create test configuration
    config = TTSConfig(
        model_path="openbmb/VoxCPM-0.5B",
        prompt_wav_path="assets/model.wav",
        prompt_text_path="assets/transcript.txt",
        save_path="./temp_audio"
    )
    
    # Initialize engine
    engine = VoxCPMEngine(config)
    
    logger.info("Testing VoxCPM engine initialization...")
    success = await engine.initialize()
    
    if not success:
        logger.error("Failed to initialize VoxCPM engine")
        return False
    
    logger.info("VoxCPM engine initialized successfully")
    
    # Test speech generation
    test_text = "Hello, this is a test of the VoxCPM text-to-speech engine."
    logger.info(f"Testing speech generation with text: {test_text}")
    
    response = await engine.generate_speech(test_text)
    
    if response.success:
        logger.info(f"Speech generation successful!")
        logger.info(f"Audio saved to: {response.audio_path}")
        logger.info(f"Generation time: {response.generation_time:.2f}s")
        
        # Verify file exists
        if response.audio_path and os.path.exists(response.audio_path):
            file_size = os.path.getsize(response.audio_path)
            logger.info(f"Audio file size: {file_size} bytes")
        else:
            logger.error("Audio file was not created")
            return False
    else:
        logger.error(f"Speech generation failed: {response.error_message}")
        return False
    
    # Test error handling with empty text
    logger.info("Testing error handling with empty text...")
    empty_response = await engine.generate_speech("")
    
    if not empty_response.success:
        logger.info("Empty text handling works correctly")
    else:
        logger.warning("Empty text should have failed")
    
    # Cleanup
    await engine.cleanup()
    logger.info("Test completed successfully")
    return True


if __name__ == "__main__":
    asyncio.run(test_voxcpm_engine())