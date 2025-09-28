"""
Configuration classes for Ollama AI integration.

This module provides configuration management for the Ollama AI engine
integration with the SecondShiftAugie Discord bot.

Requirements addressed:
- 6.1: Ollama configuration from environment variables
- 5.4: Configuration validation during startup
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class OllamaConfig:
    """Configuration for Ollama AI engine integration."""
    
    base_url: str = "http://localhost:11434"
    model_name: str = "qwen2.5:1.7b"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_response_length: int = 500
    temperature: float = 0.7
    system_prompt_file: str = "ollama_system_prompt.json"
    
    def __post_init__(self):
        """Validate configuration values."""
        if not self.base_url:
            raise ValueError("Ollama base URL cannot be empty")
        if not self.model_name:
            raise ValueError("Ollama model name cannot be empty")
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay cannot be negative")
        if self.max_response_length <= 0:
            raise ValueError("Max response length must be positive")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("Temperature must be between 0.0 and 2.0")
        if not self.system_prompt_file:
            raise ValueError("System prompt file path cannot be empty")