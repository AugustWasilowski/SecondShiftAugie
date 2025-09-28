"""
Configuration loading system with environment variable validation.

This module implements comprehensive configuration loading with validation
for the SecondShiftAugie Discord bot with VoxCPM TTS integration.

Requirements addressed:
- 4.2: Configurable TTS behavior and quality settings
- 4.3: Error handling for missing reference files
- 5.4: Configuration validation during startup
"""

import os
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from src.tts.config import TTSConfig
from src.bot.config import BotConfig
from src.config.ollama_config import OllamaConfig


logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Exception raised when configuration validation fails."""
    
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def add_error(self, error: str):
        """Add an error to the validation result."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        """Add a warning to the validation result."""
        self.warnings.append(warning)


class ConfigLoader:
    """
    Comprehensive configuration loader with environment variable validation.
    
    This class handles loading and validating all configuration for the bot,
    including Discord settings, VoxCPM TTS settings, and audio configuration.
    """
    
    # Required environment variables that must be present
    REQUIRED_VARS = [
        'BOT_TOKEN',
        'CHANNEL_ID'
    ]
    
    # Optional environment variables with their default values and types
    OPTIONAL_VARS = {
        'VOICE_CHANNEL_ID': (None, int),
        'COMMAND_PREFIX': ('!', str),
        'SAVE_PATH': ('./temp_audio', str),
        'VOXCPM_MODEL_PATH': ('openbmb/VoxCPM-0.5B', str),
        'VOXCPM_PROMPT_WAV': ('assets/model.wav', str),
        'VOXCPM_PROMPT_TEXT': ('assets/transcript.txt', str),
        'VOXCPM_CFG_VALUE': (2.0, float),
        'VOXCPM_INFERENCE_STEPS': (10, int),
        'VOXCPM_NORMALIZE': (True, bool),
        'VOXCPM_DENOISE': (True, bool),
        'VOXCPM_MAX_LENGTH': (4096, int),
        'AUDIO_CLEANUP_HOURS': (24, int),
        'OLLAMA_BASE_URL': ('http://localhost:11434', str),
        'OLLAMA_MODEL': ('qwen2.5:1.7b', str),
        'OLLAMA_TIMEOUT': (30.0, float),
        'OLLAMA_MAX_RETRIES': (3, int),
        'OLLAMA_RETRY_DELAY': (1.0, float),
        'OLLAMA_MAX_RESPONSE_LENGTH': (500, int),
        'OLLAMA_TEMPERATURE': (0.7, float),
        'SYSTEM_PROMPT_FILE': ('ollama_system_prompt.json', str),
    }
    
    def __init__(self, env_file: str = '.env'):
        """
        Initialize the configuration loader.
        
        Args:
            env_file: Path to the environment file to load
        """
        self.env_file = env_file
        self.validation_result = ConfigValidationResult(True, [], [])
        
    def load_environment(self) -> bool:
        """
        Load environment variables from .env file.
        
        Returns:
            bool: True if environment loaded successfully, False otherwise
        """
        try:
            # Load environment variables from .env file if it exists
            if os.path.exists(self.env_file):
                load_dotenv(self.env_file)
                logger.info(f"Loaded environment variables from {self.env_file}")
            else:
                logger.info(f"No {self.env_file} file found, using system environment variables")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading environment file {self.env_file}: {e}")
            return False
    
    def validate_environment_variables(self) -> ConfigValidationResult:
        """
        Validate all required and optional environment variables.
        
        Returns:
            ConfigValidationResult: Validation result with errors and warnings
        """
        result = ConfigValidationResult(True, [], [])
        
        # Check required variables
        missing_required = []
        for var in self.REQUIRED_VARS:
            value = os.getenv(var)
            if not value:
                missing_required.append(var)
            elif var == 'BOT_TOKEN' and (len(value) < 50 or not value.startswith(('Bot ', 'MTk', 'Nz', 'OD'))):
                result.add_warning(f"BOT_TOKEN format may be invalid (length: {len(value)})")
        
        if missing_required:
            result.add_error(f"Missing required environment variables: {', '.join(missing_required)}")
        
        # Validate optional variables and their types
        for var, (default_value, expected_type) in self.OPTIONAL_VARS.items():
            value = os.getenv(var)
            if value is not None:
                try:
                    # Type validation
                    if expected_type == bool:
                        # Special handling for boolean values
                        if value.lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
                            result.add_error(f"{var} must be a boolean value (true/false), got: {value}")
                    elif expected_type == int:
                        parsed_value = int(value)
                        # Additional validation for specific variables
                        if var in ('CHANNEL_ID', 'VOICE_CHANNEL_ID') and parsed_value <= 0:
                            result.add_error(f"{var} must be a positive integer, got: {parsed_value}")
                        elif var == 'VOXCPM_INFERENCE_STEPS' and (parsed_value < 1 or parsed_value > 100):
                            result.add_warning(f"{var} should be between 1-100 for optimal performance, got: {parsed_value}")
                        elif var == 'VOXCPM_MAX_LENGTH' and (parsed_value < 100 or parsed_value > 10000):
                            result.add_warning(f"{var} should be between 100-10000 for optimal performance, got: {parsed_value}")
                        elif var == 'AUDIO_CLEANUP_HOURS' and parsed_value < 1:
                            result.add_error(f"{var} must be at least 1 hour, got: {parsed_value}")
                        elif var == 'OLLAMA_MAX_RETRIES' and (parsed_value < 0 or parsed_value > 10):
                            result.add_warning(f"{var} should be between 0-10 for optimal performance, got: {parsed_value}")
                        elif var == 'OLLAMA_MAX_RESPONSE_LENGTH' and (parsed_value < 50 or parsed_value > 2000):
                            result.add_warning(f"{var} should be between 50-2000 characters for optimal performance, got: {parsed_value}")
                    elif expected_type == float:
                        parsed_value = float(value)
                        if var == 'VOXCPM_CFG_VALUE' and (parsed_value < 0.1 or parsed_value > 10.0):
                            result.add_warning(f"{var} should be between 0.1-10.0 for optimal performance, got: {parsed_value}")
                        elif var == 'OLLAMA_TIMEOUT' and (parsed_value < 1.0 or parsed_value > 300.0):
                            result.add_warning(f"{var} should be between 1.0-300.0 seconds for optimal performance, got: {parsed_value}")
                        elif var == 'OLLAMA_RETRY_DELAY' and (parsed_value < 0.1 or parsed_value > 60.0):
                            result.add_warning(f"{var} should be between 0.1-60.0 seconds for optimal performance, got: {parsed_value}")
                        elif var == 'OLLAMA_TEMPERATURE' and (parsed_value < 0.0 or parsed_value > 2.0):
                            result.add_error(f"{var} must be between 0.0-2.0, got: {parsed_value}")
                    elif expected_type == str:
                        if not value.strip():
                            result.add_error(f"{var} cannot be empty")
                        elif var == 'COMMAND_PREFIX' and len(value) > 3:
                            result.add_warning(f"{var} is unusually long ({len(value)} chars): {value}")
                        elif var in ('VOXCPM_PROMPT_WAV', 'VOXCPM_PROMPT_TEXT') and not value.strip():
                            result.add_error(f"{var} path cannot be empty")
                        elif var == 'OLLAMA_BASE_URL' and not value.startswith(('http://', 'https://')):
                            result.add_warning(f"{var} should start with http:// or https://, got: {value}")
                        elif var == 'OLLAMA_MODEL' and not value.strip():
                            result.add_error(f"{var} cannot be empty")
                        elif var == 'SYSTEM_PROMPT_FILE' and not value.strip():
                            result.add_error(f"{var} cannot be empty")
                            
                except ValueError as e:
                    result.add_error(f"{var} type validation failed: expected {expected_type.__name__}, got '{value}' - {e}")
                except Exception as e:
                    result.add_error(f"Unexpected error validating {var}: {e}")
        
        # Additional cross-variable validation
        channel_id = os.getenv('CHANNEL_ID')
        voice_channel_id = os.getenv('VOICE_CHANNEL_ID')
        
        if channel_id and voice_channel_id:
            try:
                if int(channel_id) == int(voice_channel_id):
                    result.add_warning("CHANNEL_ID and VOICE_CHANNEL_ID are the same - this may cause issues")
            except ValueError:
                pass  # Already handled in individual validation
        
        return result
    
    def _convert_env_value(self, value: str, expected_type: type) -> Any:
        """
        Convert environment variable string to expected type.
        
        Args:
            value: String value from environment
            expected_type: Expected Python type
            
        Returns:
            Converted value
            
        Raises:
            ValueError: If conversion fails
        """
        if expected_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif expected_type == int:
            return int(value)
        elif expected_type == float:
            return float(value)
        else:
            return value
    
    def load_bot_config(self) -> BotConfig:
        """
        Load and create BotConfig from environment variables.
        
        Returns:
            BotConfig: Configured bot settings
            
        Raises:
            ConfigValidationError: If required configuration is missing or invalid
        """
        try:
            # Get required values
            token = os.getenv('BOT_TOKEN')
            if not token:
                raise ConfigValidationError("BOT_TOKEN is required")
            
            channel_id_str = os.getenv('CHANNEL_ID')
            if not channel_id_str:
                raise ConfigValidationError("CHANNEL_ID is required")
            
            try:
                channel_id = int(channel_id_str)
            except ValueError:
                raise ConfigValidationError(f"CHANNEL_ID must be an integer, got: {channel_id_str}")
            
            # Get optional values with defaults
            voice_channel_id = None
            voice_channel_id_str = os.getenv('VOICE_CHANNEL_ID')
            if voice_channel_id_str:
                try:
                    voice_channel_id = int(voice_channel_id_str)
                except ValueError:
                    raise ConfigValidationError(f"VOICE_CHANNEL_ID must be an integer, got: {voice_channel_id_str}")
            
            save_path = os.getenv('SAVE_PATH', './temp_audio')
            command_prefix = os.getenv('COMMAND_PREFIX', '!')
            
            # Create and validate config
            config = BotConfig(
                token=token,
                channel_id=channel_id,
                voice_channel_id=voice_channel_id,
                save_path=save_path,
                command_prefix=command_prefix
            )
            
            logger.info("Bot configuration loaded successfully")
            return config
            
        except ValueError as e:
            raise ConfigValidationError(f"Invalid bot configuration: {e}")
        except Exception as e:
            raise ConfigValidationError(f"Error loading bot configuration: {e}")
    
    def load_tts_config(self, save_path: str) -> TTSConfig:
        """
        Load and create TTSConfig from environment variables.
        
        Args:
            save_path: Audio save path from bot config
            
        Returns:
            TTSConfig: Configured TTS settings
            
        Raises:
            ConfigValidationError: If TTS configuration is invalid
        """
        try:
            # Load TTS configuration with defaults
            model_path = os.getenv('VOXCPM_MODEL_PATH', 'openbmb/VoxCPM-0.5B')
            prompt_wav_path = os.getenv('VOXCPM_PROMPT_WAV', 'assets/model.wav')
            prompt_text_path = os.getenv('VOXCPM_PROMPT_TEXT', 'assets/transcript.txt')
            
            # Parse numeric values with validation
            try:
                cfg_value = float(os.getenv('VOXCPM_CFG_VALUE', '2.0'))
            except ValueError:
                raise ConfigValidationError(f"VOXCPM_CFG_VALUE must be a number, got: {os.getenv('VOXCPM_CFG_VALUE')}")
            
            try:
                inference_timesteps = int(os.getenv('VOXCPM_INFERENCE_STEPS', '10'))
            except ValueError:
                raise ConfigValidationError(f"VOXCPM_INFERENCE_STEPS must be an integer, got: {os.getenv('VOXCPM_INFERENCE_STEPS')}")
            
            try:
                max_length = int(os.getenv('VOXCPM_MAX_LENGTH', '4096'))
            except ValueError:
                raise ConfigValidationError(f"VOXCPM_MAX_LENGTH must be an integer, got: {os.getenv('VOXCPM_MAX_LENGTH')}")
            
            # Parse boolean values
            normalize = os.getenv('VOXCPM_NORMALIZE', 'true').lower() in ('true', '1', 'yes', 'on')
            denoise = os.getenv('VOXCPM_DENOISE', 'true').lower() in ('true', '1', 'yes', 'on')
            
            config = TTSConfig(
                model_path=model_path,
                prompt_wav_path=prompt_wav_path,
                prompt_text_path=prompt_text_path,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                normalize=normalize,
                denoise=denoise,
                max_length=max_length,
                save_path=save_path
            )
            
            logger.info("TTS configuration loaded successfully")
            return config
            
        except Exception as e:
            if isinstance(e, ConfigValidationError):
                raise
            raise ConfigValidationError(f"Error loading TTS configuration: {e}")
    
    def load_ollama_config(self) -> OllamaConfig:
        """
        Load and create OllamaConfig from environment variables.
        
        Returns:
            OllamaConfig: Configured Ollama settings
            
        Raises:
            ConfigValidationError: If Ollama configuration is invalid
        """
        try:
            # Load Ollama configuration with defaults
            base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
            model_name = os.getenv('OLLAMA_MODEL', 'qwen2.5:1.7b')
            system_prompt_file = os.getenv('SYSTEM_PROMPT_FILE', 'ollama_system_prompt.json')
            
            # Parse numeric values with validation
            try:
                timeout = float(os.getenv('OLLAMA_TIMEOUT', '30.0'))
            except ValueError:
                raise ConfigValidationError(f"OLLAMA_TIMEOUT must be a number, got: {os.getenv('OLLAMA_TIMEOUT')}")
            
            try:
                max_retries = int(os.getenv('OLLAMA_MAX_RETRIES', '3'))
            except ValueError:
                raise ConfigValidationError(f"OLLAMA_MAX_RETRIES must be an integer, got: {os.getenv('OLLAMA_MAX_RETRIES')}")
            
            try:
                retry_delay = float(os.getenv('OLLAMA_RETRY_DELAY', '1.0'))
            except ValueError:
                raise ConfigValidationError(f"OLLAMA_RETRY_DELAY must be a number, got: {os.getenv('OLLAMA_RETRY_DELAY')}")
            
            try:
                max_response_length = int(os.getenv('OLLAMA_MAX_RESPONSE_LENGTH', '500'))
            except ValueError:
                raise ConfigValidationError(f"OLLAMA_MAX_RESPONSE_LENGTH must be an integer, got: {os.getenv('OLLAMA_MAX_RESPONSE_LENGTH')}")
            
            try:
                temperature = float(os.getenv('OLLAMA_TEMPERATURE', '0.7'))
            except ValueError:
                raise ConfigValidationError(f"OLLAMA_TEMPERATURE must be a number, got: {os.getenv('OLLAMA_TEMPERATURE')}")
            
            config = OllamaConfig(
                base_url=base_url,
                model_name=model_name,
                timeout=timeout,
                max_retries=max_retries,
                retry_delay=retry_delay,
                max_response_length=max_response_length,
                temperature=temperature,
                system_prompt_file=system_prompt_file
            )
            
            logger.info("Ollama configuration loaded successfully")
            return config
            
        except Exception as e:
            if isinstance(e, ConfigValidationError):
                raise
            raise ConfigValidationError(f"Error loading Ollama configuration: {e}")
    
    def load_all_configs(self) -> tuple[BotConfig, TTSConfig, OllamaConfig]:
        """
        Load all configurations with comprehensive validation.
        
        Returns:
            tuple: (BotConfig, TTSConfig, OllamaConfig)
            
        Raises:
            ConfigValidationError: If any configuration is invalid
        """
        # Load environment
        if not self.load_environment():
            raise ConfigValidationError("Failed to load environment variables")
        
        # Validate environment variables
        validation_result = self.validate_environment_variables()
        
        # Log warnings
        for warning in validation_result.warnings:
            logger.warning(f"Configuration warning: {warning}")
        
        # Raise error if validation failed
        if not validation_result.is_valid:
            error_msg = "Configuration validation failed"
            logger.error(error_msg)
            for error in validation_result.errors:
                logger.error(f"  - {error}")
            raise ConfigValidationError(error_msg, validation_result.errors)
        
        # Load individual configs
        bot_config = self.load_bot_config()
        tts_config = self.load_tts_config(bot_config.save_path)
        ollama_config = self.load_ollama_config()
        
        logger.info("All configurations loaded and validated successfully")
        return bot_config, tts_config, ollama_config
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the configuration validation.
        
        Returns:
            dict: Summary of validation results
        """
        env_vars_present = {}
        
        # Check which variables are present
        for var in self.REQUIRED_VARS:
            env_vars_present[var] = os.getenv(var) is not None
        
        for var in self.OPTIONAL_VARS:
            env_vars_present[var] = os.getenv(var) is not None
        
        return {
            'environment_file_exists': os.path.exists(self.env_file),
            'required_vars_present': all(env_vars_present[var] for var in self.REQUIRED_VARS),
            'environment_variables': env_vars_present,
            'validation_errors': len(self.validation_result.errors),
            'validation_warnings': len(self.validation_result.warnings)
        }