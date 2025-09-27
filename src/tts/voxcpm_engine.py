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
        
        Implements graceful degradation for VoxCPM initialization failures.
        Requirements 4.1, 4.3: Fallback to text-only mode when VoxCPM fails or reference files missing.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("Initializing VoxCPM engine...")
            
            # Validate reference files exist (Requirement 4.3)
            if not os.path.exists(self.config.prompt_wav_path):
                logger.error(f"Reference audio file not found: {self.config.prompt_wav_path}")
                logger.error("VoxCPM initialization failed - falling back to text-only mode")
                self._set_fallback_mode("Reference audio file missing")
                return False
                
            if not os.path.exists(self.config.prompt_text_path):
                logger.error(f"Reference text file not found: {self.config.prompt_text_path}")
                logger.error("VoxCPM initialization failed - falling back to text-only mode")
                self._set_fallback_mode("Reference text file missing")
                return False
            
            # Validate reference files are readable and valid
            try:
                # Check audio file accessibility
                import soundfile as sf
                with sf.SoundFile(self.config.prompt_wav_path) as f:
                    if f.frames == 0:
                        logger.error("Reference audio file is empty or corrupted")
                        self._set_fallback_mode("Reference audio file corrupted")
                        return False
                    logger.debug(f"Reference audio: {f.frames} frames, {f.samplerate} Hz, {f.channels} channels")
                    
            except Exception as audio_error:
                logger.error(f"Reference audio file validation failed: {audio_error}")
                self._set_fallback_mode("Reference audio file validation failed")
                return False
            
            # Load and validate reference text
            try:
                with open(self.config.prompt_text_path, 'r', encoding='utf-8') as f:
                    self._prompt_text = f.read().strip()
                
                if not self._prompt_text:
                    logger.error("Reference text file is empty")
                    self._set_fallback_mode("Reference text file empty")
                    return False
                    
                if len(self._prompt_text) < 10:
                    logger.warning(f"Reference text is very short ({len(self._prompt_text)} chars) - this may affect voice quality")
                    
                logger.debug(f"Reference text loaded: {len(self._prompt_text)} characters")
                
            except UnicodeDecodeError as e:
                logger.error(f"Reference text file encoding error: {e}")
                self._set_fallback_mode("Reference text file encoding error")
                return False
            except Exception as text_error:
                logger.error(f"Reference text file validation failed: {text_error}")
                self._set_fallback_mode("Reference text file validation failed")
                return False
            
            # Initialize VoxCPM model in a separate thread to avoid blocking
            try:
                loop = asyncio.get_event_loop()
                self._model = await asyncio.wait_for(
                    loop.run_in_executor(None, self._load_model),
                    timeout=120.0  # 2 minute timeout for model loading
                )
                
                if self._model is None:
                    logger.error("VoxCPM model loading returned None")
                    self._set_fallback_mode("Model loading failed")
                    return False
                    
            except asyncio.TimeoutError:
                logger.error("VoxCPM model loading timed out after 2 minutes")
                self._set_fallback_mode("Model loading timeout")
                return False
            except Exception as model_error:
                logger.error(f"VoxCPM model loading failed: {model_error}")
                self._set_fallback_mode(f"Model loading error: {str(model_error)}")
                return False
            
            # Test model with a simple generation to ensure it's working
            try:
                test_result = await self._test_model_functionality()
                if not test_result:
                    logger.error("VoxCPM model functionality test failed")
                    self._set_fallback_mode("Model functionality test failed")
                    return False
                    
            except Exception as test_error:
                logger.error(f"VoxCPM model test failed: {test_error}")
                self._set_fallback_mode(f"Model test error: {str(test_error)}")
                return False
            
            self._is_ready = True
            logger.info("VoxCPM engine initialized successfully")
            logger.info(f"Model path: {self.config.model_path}")
            logger.info(f"Reference audio: {self.config.prompt_wav_path}")
            logger.info(f"Reference text length: {len(self._prompt_text)} characters")
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error initializing VoxCPM engine: {e}")
            self._set_fallback_mode(f"Unexpected initialization error: {str(e)}")
            return False
    
    def _set_fallback_mode(self, reason: str):
        """Set the engine to fallback mode with detailed logging.
        
        Args:
            reason: Reason for fallback mode
        """
        self._is_ready = False
        self._model = None
        logger.warning(f"VoxCPM engine entering fallback mode: {reason}")
        logger.warning("Bot will continue operating in text-only mode")
        logger.info("Voice responses will not be available until VoxCPM is properly configured")
    
    async def _test_model_functionality(self) -> bool:
        """Test VoxCPM model with a simple generation to ensure it's working.
        
        Returns:
            bool: True if test successful, False otherwise
        """
        try:
            logger.info("Testing VoxCPM model functionality...")
            
            # Run a simple test generation in executor
            loop = asyncio.get_event_loop()
            test_audio = await asyncio.wait_for(
                loop.run_in_executor(None, self._test_generate_audio),
                timeout=30.0  # 30 second timeout for test
            )
            
            if test_audio is None:
                logger.error("Model test generation returned None")
                return False
                
            if len(test_audio) == 0:
                logger.error("Model test generation returned empty audio")
                return False
                
            logger.info(f"Model test successful - generated {len(test_audio)} audio samples")
            return True
            
        except asyncio.TimeoutError:
            logger.error("Model functionality test timed out")
            return False
        except Exception as e:
            logger.error(f"Model functionality test failed: {e}")
            return False
    
    def _test_generate_audio(self):
        """Generate test audio to verify model functionality (runs in executor thread)."""
        try:
            # Generate a very short test audio
            test_text = "Test"
            audio_array = self._model.generate(
                text=test_text,
                prompt_wav_path=self.config.prompt_wav_path,
                prompt_text=self._prompt_text,
                cfg_value=self.config.cfg_value,
                inference_timesteps=min(5, self.config.inference_timesteps),  # Faster for test
                normalize=self.config.normalize,
                denoise=self.config.denoise,
                max_length=min(100, self.config.max_length)  # Shorter for test
            )
            
            return audio_array
            
        except Exception as e:
            logger.error(f"Test audio generation failed: {e}")
            return None
    
    def _load_model(self):
        """Load VoxCPM model (runs in executor thread).
        
        Implements comprehensive error handling for model loading failures.
        Requirements 4.1: Graceful fallback when VoxCPM is not available.
        """
        try:
            logger.info("Loading VoxCPM model...")
            
            # Import VoxCPM here to avoid import issues if not available
            try:
                from voxcpm import VoxCPM
                logger.debug("VoxCPM module imported successfully")
            except ImportError as import_error:
                logger.error(f"VoxCPM module not available: {import_error}")
                logger.error("Please install VoxCPM: pip install voxcpm")
                return None
            except Exception as import_error:
                logger.error(f"Unexpected error importing VoxCPM: {import_error}")
                return None
            
            # Determine model loading method
            if os.path.isdir(self.config.model_path):
                logger.info(f"Loading local VoxCPM model from: {self.config.model_path}")
                try:
                    # Validate local model directory structure
                    required_files = ["config.json"]  # Basic validation
                    for req_file in required_files:
                        file_path = os.path.join(self.config.model_path, req_file)
                        if not os.path.exists(file_path):
                            logger.warning(f"Local model missing expected file: {req_file}")
                    
                    model = VoxCPM(
                        voxcpm_model_path=self.config.model_path,
                        enable_denoiser=self.config.denoise
                    )
                    logger.info("Local VoxCPM model loaded successfully")
                    
                except FileNotFoundError as e:
                    logger.error(f"Local model files not found: {e}")
                    return None
                except PermissionError as e:
                    logger.error(f"Permission denied accessing local model: {e}")
                    return None
                except Exception as e:
                    logger.error(f"Error loading local VoxCPM model: {e}")
                    return None
                    
            else:
                logger.info(f"Loading VoxCPM model from Hugging Face: {self.config.model_path}")
                try:
                    model = VoxCPM.from_pretrained(
                        hf_model_id=self.config.model_path,
                        load_denoiser=self.config.denoise
                    )
                    logger.info("Hugging Face VoxCPM model loaded successfully")
                    
                except Exception as hf_error:
                    logger.error(f"Error loading model from Hugging Face: {hf_error}")
                    logger.error("This could be due to network issues, invalid model ID, or missing dependencies")
                    
                    # Try to provide helpful error messages
                    error_str = str(hf_error).lower()
                    if "connection" in error_str or "network" in error_str:
                        logger.error("Network connection issue - check internet connectivity")
                    elif "not found" in error_str or "404" in error_str:
                        logger.error(f"Model '{self.config.model_path}' not found on Hugging Face")
                    elif "token" in error_str or "authentication" in error_str:
                        logger.error("Authentication issue - check Hugging Face token if required")
                    elif "memory" in error_str or "out of memory" in error_str:
                        logger.error("Insufficient memory to load model - try a smaller model or increase available RAM")
                    
                    return None
            
            # Validate model was loaded properly
            if model is None:
                logger.error("Model loading returned None")
                return None
                
            # Basic model validation
            try:
                # Check if model has required methods
                if not hasattr(model, 'generate'):
                    logger.error("Loaded model missing 'generate' method")
                    return None
                    
                logger.info("VoxCPM model validation passed")
                
            except Exception as validation_error:
                logger.error(f"Model validation failed: {validation_error}")
                return None
            
            logger.info("VoxCPM model loaded and validated successfully")
            return model
            
        except Exception as e:
            logger.error(f"Unexpected error loading VoxCPM model: {e}")
            logger.error("This is likely due to missing dependencies or system configuration issues")
            return None
    
    async def generate_speech(self, text: str) -> AudioResponse:
        """Generate speech from text using VoxCPM.
        
        Implements comprehensive error handling and graceful degradation.
        Requirements 4.1: Fallback to text-only mode when VoxCPM fails.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            AudioResponse: Response containing audio path and metadata
        """
        start_time = time.time()
        
        # Validate engine state
        if not self._is_ready or self._model is None:
            logger.debug("VoxCPM engine not ready - returning failure response")
            return AudioResponse(
                text=text,
                audio_path=None,
                generation_time=0.0,
                success=False,
                error_message="VoxCPM engine not initialized - operating in text-only mode"
            )
        
        # Validate input text
        if not text or not text.strip():
            logger.warning("Empty text provided for speech generation")
            return AudioResponse(
                text=text,
                audio_path=None,
                generation_time=0.0,
                success=False,
                error_message="Empty text provided"
            )
        
        # Validate text length
        text_clean = text.strip()
        if len(text_clean) > self.config.max_length:
            logger.warning(f"Text too long ({len(text_clean)} chars), truncating to {self.config.max_length}")
            text_clean = text_clean[:self.config.max_length]
        
        try:
            # Generate unique filename with timestamp for better organization
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            audio_filename = f"voxcpm_{timestamp}_{unique_id}.wav"
            audio_path = os.path.join(self.config.save_path, audio_filename)
            
            # Ensure save directory exists
            try:
                os.makedirs(self.config.save_path, exist_ok=True)
            except Exception as dir_error:
                logger.error(f"Failed to create save directory: {dir_error}")
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message=f"Cannot create save directory: {str(dir_error)}"
                )
            
            # Generate audio in executor thread to avoid blocking
            try:
                loop = asyncio.get_event_loop()
                audio_array = await asyncio.wait_for(
                    loop.run_in_executor(None, self._generate_audio, text_clean),
                    timeout=60.0  # 1 minute timeout for generation
                )
                
            except asyncio.TimeoutError:
                logger.error(f"Audio generation timed out for text: '{text_clean[:50]}...'")
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message="Audio generation timed out - text may be too long or complex"
                )
            except Exception as gen_error:
                logger.error(f"Audio generation failed: {gen_error}")
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message=f"Audio generation failed: {str(gen_error)}"
                )
            
            if audio_array is None:
                logger.error("Audio generation returned None")
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message="Audio generation failed - model returned no output"
                )
            
            # Validate generated audio
            if len(audio_array) == 0:
                logger.error("Generated audio array is empty")
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message="Generated audio is empty"
                )
            
            # Save audio file with error handling
            try:
                sf.write(audio_path, audio_array, 16000)
                
                # Verify file was written successfully
                if not os.path.exists(audio_path):
                    logger.error(f"Audio file was not created: {audio_path}")
                    return AudioResponse(
                        text=text,
                        audio_path=None,
                        generation_time=time.time() - start_time,
                        success=False,
                        error_message="Audio file creation failed"
                    )
                
                # Check file size is reasonable
                file_size = os.path.getsize(audio_path)
                if file_size == 0:
                    logger.error(f"Generated audio file is empty: {audio_path}")
                    try:
                        os.remove(audio_path)
                    except:
                        pass
                    return AudioResponse(
                        text=text,
                        audio_path=None,
                        generation_time=time.time() - start_time,
                        success=False,
                        error_message="Generated audio file is empty"
                    )
                
            except Exception as save_error:
                logger.error(f"Failed to save audio file: {save_error}")
                return AudioResponse(
                    text=text,
                    audio_path=None,
                    generation_time=time.time() - start_time,
                    success=False,
                    error_message=f"Failed to save audio file: {str(save_error)}"
                )
            
            generation_time = time.time() - start_time
            logger.info(f"Generated audio for text (length: {len(text_clean)}) in {generation_time:.2f}s")
            logger.debug(f"Audio saved to: {audio_path} ({file_size} bytes)")
            
            return AudioResponse(
                text=text,
                audio_path=audio_path,
                generation_time=generation_time,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Unexpected error generating speech: {e}")
            return AudioResponse(
                text=text,
                audio_path=None,
                generation_time=time.time() - start_time,
                success=False,
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def _generate_audio(self, text: str):
        """Generate audio using VoxCPM (runs in executor thread).
        
        Implements detailed error handling for VoxCPM generation failures.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Audio array or None if generation fails
        """
        try:
            logger.debug(f"Starting VoxCPM generation for text: '{text[:50]}...'")
            
            # Validate model state
            if self._model is None:
                logger.error("Model is None during generation")
                return None
            
            # Validate reference files still exist
            if not os.path.exists(self.config.prompt_wav_path):
                logger.error(f"Reference audio file missing during generation: {self.config.prompt_wav_path}")
                return None
            
            if not self._prompt_text:
                logger.error("Reference text is empty during generation")
                return None
            
            # Generate audio using reference voice with comprehensive error handling
            try:
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
                
                # Validate output
                if audio_array is None:
                    logger.error("VoxCPM generate() returned None")
                    return None
                
                if len(audio_array) == 0:
                    logger.error("VoxCPM generate() returned empty array")
                    return None
                
                logger.debug(f"VoxCPM generation successful: {len(audio_array)} samples")
                return audio_array
                
            except RuntimeError as runtime_error:
                logger.error(f"VoxCPM runtime error: {runtime_error}")
                error_str = str(runtime_error).lower()
                
                if "cuda" in error_str or "gpu" in error_str:
                    logger.error("GPU/CUDA error - model may need CPU fallback")
                elif "memory" in error_str or "out of memory" in error_str:
                    logger.error("Out of memory error - try shorter text or restart bot")
                elif "model" in error_str:
                    logger.error("Model error - model may be corrupted or incompatible")
                
                return None
                
            except ValueError as value_error:
                logger.error(f"VoxCPM value error: {value_error}")
                error_str = str(value_error).lower()
                
                if "text" in error_str:
                    logger.error("Text input error - check text content and encoding")
                elif "parameter" in error_str or "config" in error_str:
                    logger.error("Configuration parameter error - check TTS settings")
                
                return None
                
            except Exception as model_error:
                logger.error(f"VoxCPM model error: {model_error}")
                logger.error("This may indicate model corruption or incompatibility")
                return None
            
        except Exception as e:
            logger.error(f"Unexpected error in VoxCPM generation: {e}")
            logger.error("This indicates a serious issue with the TTS engine")
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