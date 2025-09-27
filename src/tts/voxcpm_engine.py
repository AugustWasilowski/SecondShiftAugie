"""VoxCPM TTS Engine for Discord bot integration."""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import soundfile as sf

from .config import TTSConfig, AudioResponse


logger = logging.getLogger(__name__)


class VoxCPMEngine:
    """VoxCPM TTS Engine for generating speech from text using reference voice model."""
    
    def __init__(self, config: TTSConfig):
        """Initialize VoxCPM engine with configuration.
        
        Args:
            config: TTSConfig instance with model and generation parameters
        """
        self.config = config
        self._model = None
        self._prompt_text = None
        self._is_ready = False
        
        # Ensure save directory exists
        os.makedirs(config.save_path, exist_ok=True)
        
    async def initialize(self) -> bool:
        """Initialize VoxCPM model and load reference files.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("Initializing VoxCPM engine...")
            
            # Validate reference files exist
            if not os.path.exists(self.config.prompt_wav_path):
                logger.error(f"Reference audio file not found: {self.config.prompt_wav_path}")
                return False
                
            if not os.path.exists(self.config.prompt_text_path):
                logger.error(f"Reference text file not found: {self.config.prompt_text_path}")
                return False
            
            # Load reference text
            with open(self.config.prompt_text_path, 'r', encoding='utf-8') as f:
                self._prompt_text = f.read().strip()
            
            if not self._prompt_text:
                logger.error("Reference text file is empty")
                return False
            
            # Initialize VoxCPM model in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(None, self._load_model)
            
            if self._model is None:
                logger.error("Failed to load VoxCPM model")
                return False
            
            self._is_ready = True
            logger.info("VoxCPM engine initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing VoxCPM engine: {e}")
            return False
    
    def _load_model(self):
        """Load VoxCPM model (runs in executor thread)."""
        try:
            # Import VoxCPM here to avoid import issues if not available
            from voxcpm import VoxCPM
            
            # Load model from pretrained or local path
            if os.path.isdir(self.config.model_path):
                # Local model path
                model = VoxCPM(
                    voxcpm_model_path=self.config.model_path,
                    enable_denoiser=self.config.denoise
                )
            else:
                # Hugging Face model ID
                model = VoxCPM.from_pretrained(
                    hf_model_id=self.config.model_path,
                    load_denoiser=self.config.denoise
                )
            
            logger.info("VoxCPM model loaded successfully")
            return model
            
        except ImportError as e:
            logger.error(f"VoxCPM not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading VoxCPM model: {e}")
            return None
    
    async def generate_speech(self, text: str) -> AudioResponse:
        """Generate speech from text using VoxCPM.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            AudioResponse: Response containing audio path and metadata
        """
        start_time = time.time()
        
        if not self._is_ready or self._model is None:
            return AudioResponse(
                text=text,
                audio_path=None,
                generation_time=0.0,
                success=False,
                error_message="VoxCPM engine not initialized"
            )
        
        if not text or not text.strip():
            return AudioResponse(
                text=text,
                audio_path=None,
                generation_time=0.0,
                success=False,
                error_message="Empty text provided"
            )
        
        try:
            # Generate unique filename
            audio_filename = f"voxcpm_{uuid.uuid4().hex[:8]}.wav"
            audio_path = os.path.join(self.config.save_path, audio_filename)
            
            # Generate audio in executor thread to avoid blocking
            loop = asyncio.get_event_loop()
            audio_array = await loop.run_in_executor(
                None, 
                self._generate_audio, 
                text.strip()
            )
            
            if audio_array is None:
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message="Audio generation failed"
                )
            
            # Save audio file
            sf.write(audio_path, audio_array, 16000)
            
            generation_time = time.time() - start_time
            logger.info(f"Generated audio for text (length: {len(text)}) in {generation_time:.2f}s")
            
            return AudioResponse(
                text=text,
                audio_path=audio_path,
                generation_time=generation_time,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Error generating speech: {e}")
            return AudioResponse(
                text=text,
                audio_path=None,
                generation_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    def _generate_audio(self, text: str):
        """Generate audio using VoxCPM (runs in executor thread)."""
        try:
            # Generate audio using reference voice
            audio_array = self._model.generate(
                text=text,
                prompt_wav_path=self.config.prompt_wav_path,
                prompt_text=self._prompt_text,
                cfg_value=self.config.cfg_value,
                inference_timesteps=self.config.inference_timesteps,
                normalize=self.config.normalize,
                denoise=self.config.denoise,
                max_length=self.config.max_length
            )
            
            return audio_array
            
        except Exception as e:
            logger.error(f"VoxCPM generation error: {e}")
            return None
    
    def is_ready(self) -> bool:
        """Check if engine is ready for generation.
        
        Returns:
            bool: True if engine is initialized and ready
        """
        return self._is_ready and self._model is not None
    
    async def cleanup(self):
        """Clean up resources."""
        try:
            self._model = None
            self._is_ready = False
            logger.info("VoxCPM engine cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")