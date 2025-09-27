"""Configuration classes for VoxCPM TTS engine."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TTSConfig:
    """Configuration for VoxCPM TTS engine."""
    model_path: str = "openbmb/VoxCPM-0.5B"
    prompt_wav_path: str = "assets/model.wav"
    prompt_text_path: str = "assets/transcript.txt"
    cfg_value: float = 2.0
    inference_timesteps: int = 10
    normalize: bool = True
    denoise: bool = True
    max_length: int = 4096
    save_path: str = "./temp_audio"


@dataclass
class AudioResponse:
    """Response from audio generation."""
    text: str
    audio_path: Optional[str]
    generation_time: float
    success: bool
    error_message: Optional[str] = None