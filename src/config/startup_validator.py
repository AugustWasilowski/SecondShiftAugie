"""
Startup validation system for SecondShiftAugie bot.

This module implements comprehensive startup validation including reference file checks,
VoxCPM model accessibility validation, and system dependency verification.

Requirements addressed:
- 4.2: Configurable TTS behavior and quality settings validation
- 4.3: Error handling for missing reference files with proper logging
- 5.4: Startup validation for all critical components
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

from src.tts.config import TTSConfig
from src.bot.config import BotConfig
from src.config.ollama_config import OllamaConfig


logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Represents a validation issue found during startup checks."""
    severity: ValidationSeverity
    component: str
    message: str
    suggestion: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of the validation issue."""
        result = f"[{self.severity.value.upper()}] {self.component}: {self.message}"
        if self.suggestion:
            result += f" | Suggestion: {self.suggestion}"
        return result


@dataclass
class ValidationResult:
    """Result of startup validation checks."""
    is_valid: bool
    can_start: bool  # Whether bot can start despite issues
    issues: List[ValidationIssue]
    summary: Dict[str, Any]
    
    def add_issue(self, severity: ValidationSeverity, component: str, message: str, suggestion: str = None):
        """Add a validation issue."""
        issue = ValidationIssue(severity, component, message, suggestion)
        self.issues.append(issue)
        
        # Update validation status based on severity
        if severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL):
            if severity == ValidationSeverity.CRITICAL:
                self.can_start = False
            self.is_valid = False
    
    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Get all issues of a specific severity."""
        return [issue for issue in self.issues if issue.severity == severity]
    
    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues."""
        return any(issue.severity == ValidationSeverity.CRITICAL for issue in self.issues)
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)


class StartupValidator:
    """
    Comprehensive startup validation system.
    
    This class performs all necessary validation checks before the bot starts,
    including file system checks, dependency validation, and configuration verification.
    """
    
    def __init__(self, bot_config: BotConfig, tts_config: TTSConfig, ollama_config: OllamaConfig):
        """
        Initialize the startup validator.
        
        Args:
            bot_config: Bot configuration to validate
            tts_config: TTS configuration to validate
            ollama_config: Ollama AI configuration to validate
        """
        self.bot_config = bot_config
        self.tts_config = tts_config
        self.ollama_config = ollama_config
        self.result = ValidationResult(True, True, [], {})
    
    def validate_reference_files(self) -> None:
        """
        Validate reference audio and text files exist and are accessible.
        
        Requirement 4.3: Error handling for missing reference files with proper logging.
        """
        logger.info("Validating reference files...")
        
        # Validate reference audio file
        audio_path = Path(self.tts_config.prompt_wav_path)
        if not audio_path.exists():
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "reference_audio",
                f"Reference audio file not found: {audio_path}",
                f"Ensure the file exists or update VOXCPM_PROMPT_WAV environment variable"
            )
        else:
            try:
                # Check if file is readable
                if not audio_path.is_file():
                    self.result.add_issue(
                        ValidationSeverity.ERROR,
                        "reference_audio",
                        f"Reference audio path is not a file: {audio_path}"
                    )
                elif audio_path.stat().st_size == 0:
                    self.result.add_issue(
                        ValidationSeverity.ERROR,
                        "reference_audio",
                        f"Reference audio file is empty: {audio_path}"
                    )
                else:
                    # Try to validate audio format using soundfile if available
                    try:
                        import soundfile as sf
                        with sf.SoundFile(str(audio_path)) as f:
                            if f.frames == 0:
                                self.result.add_issue(
                                    ValidationSeverity.ERROR,
                                    "reference_audio",
                                    f"Reference audio file contains no audio data: {audio_path}"
                                )
                            elif f.samplerate < 8000 or f.samplerate > 48000:
                                self.result.add_issue(
                                    ValidationSeverity.WARNING,
                                    "reference_audio",
                                    f"Reference audio sample rate may be suboptimal: {f.samplerate} Hz",
                                    "Consider using 16kHz or 22kHz for better TTS quality"
                                )
                            else:
                                logger.info(f"Reference audio validated: {f.frames} frames, {f.samplerate} Hz, {f.channels} channels")
                                self.result.add_issue(
                                    ValidationSeverity.INFO,
                                    "reference_audio",
                                    f"Reference audio file validated successfully ({f.frames} frames, {f.samplerate} Hz)"
                                )
                                
                    except ImportError:
                        self.result.add_issue(
                            ValidationSeverity.WARNING,
                            "reference_audio",
                            "soundfile library not available - cannot validate audio format",
                            "Install soundfile library for better audio validation"
                        )
                    except Exception as e:
                        self.result.add_issue(
                            ValidationSeverity.ERROR,
                            "reference_audio",
                            f"Reference audio file validation failed: {e}",
                            "Ensure the file is a valid audio format (WAV, MP3, etc.)"
                        )
                        
            except PermissionError:
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "reference_audio",
                    f"Permission denied accessing reference audio file: {audio_path}"
                )
            except Exception as e:
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "reference_audio",
                    f"Error accessing reference audio file: {e}"
                )
        
        # Validate reference text file
        text_path = Path(self.tts_config.prompt_text_path)
        if not text_path.exists():
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "reference_text",
                f"Reference text file not found: {text_path}",
                f"Ensure the file exists or update VOXCPM_PROMPT_TEXT environment variable"
            )
        else:
            try:
                if not text_path.is_file():
                    self.result.add_issue(
                        ValidationSeverity.ERROR,
                        "reference_text",
                        f"Reference text path is not a file: {text_path}"
                    )
                elif text_path.stat().st_size == 0:
                    self.result.add_issue(
                        ValidationSeverity.ERROR,
                        "reference_text",
                        f"Reference text file is empty: {text_path}"
                    )
                else:
                    # Read and validate text content
                    try:
                        with open(text_path, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                            
                        if not content:
                            self.result.add_issue(
                                ValidationSeverity.ERROR,
                                "reference_text",
                                f"Reference text file contains no text: {text_path}"
                            )
                        elif len(content) < 10:
                            self.result.add_issue(
                                ValidationSeverity.WARNING,
                                "reference_text",
                                f"Reference text is very short ({len(content)} chars) - may affect voice quality",
                                "Consider using text with at least 50-100 characters for better voice cloning"
                            )
                        elif len(content) > 1000:
                            self.result.add_issue(
                                ValidationSeverity.WARNING,
                                "reference_text",
                                f"Reference text is very long ({len(content)} chars) - may slow down processing",
                                "Consider using shorter reference text (100-500 chars) for faster processing"
                            )
                        else:
                            logger.info(f"Reference text validated: {len(content)} characters")
                            self.result.add_issue(
                                ValidationSeverity.INFO,
                                "reference_text",
                                f"Reference text file validated successfully ({len(content)} characters)"
                            )
                            
                    except UnicodeDecodeError as e:
                        self.result.add_issue(
                            ValidationSeverity.ERROR,
                            "reference_text",
                            f"Reference text file encoding error: {e}",
                            "Ensure the file is saved in UTF-8 encoding"
                        )
                    except Exception as e:
                        self.result.add_issue(
                            ValidationSeverity.ERROR,
                            "reference_text",
                            f"Error reading reference text file: {e}"
                        )
                        
            except PermissionError:
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "reference_text",
                    f"Permission denied accessing reference text file: {text_path}"
                )
            except Exception as e:
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "reference_text",
                    f"Error accessing reference text file: {e}"
                )
    
    def validate_save_directory(self) -> None:
        """Validate save directory exists and is writable."""
        logger.info("Validating save directory...")
        
        save_path = Path(self.tts_config.save_path)
        
        try:
            # Create directory if it doesn't exist
            save_path.mkdir(parents=True, exist_ok=True)
            
            # Test write permissions
            test_file = save_path / "startup_test.tmp"
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                test_file.unlink()  # Delete test file
                
                logger.info(f"Save directory validated: {save_path}")
                self.result.add_issue(
                    ValidationSeverity.INFO,
                    "save_directory",
                    f"Save directory is accessible and writable: {save_path}"
                )
                
            except PermissionError:
                self.result.add_issue(
                    ValidationSeverity.CRITICAL,
                    "save_directory",
                    f"Save directory is not writable: {save_path}",
                    "Check directory permissions or change SAVE_PATH to a writable location"
                )
            except Exception as e:
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "save_directory",
                    f"Cannot write to save directory: {e}"
                )
                
        except PermissionError:
            self.result.add_issue(
                ValidationSeverity.CRITICAL,
                "save_directory",
                f"Cannot create save directory: {save_path}",
                "Check parent directory permissions or change SAVE_PATH"
            )
        except Exception as e:
            self.result.add_issue(
                ValidationSeverity.CRITICAL,
                "save_directory",
                f"Error creating save directory: {e}"
            )
    
    def validate_voxcpm_accessibility(self) -> None:
        """
        Validate VoxCPM model accessibility during initialization.
        
        Requirement 5.4: Validate VoxCPM model accessibility during initialization.
        """
        logger.info("Validating VoxCPM accessibility...")
        
        # Check if VoxCPM module can be imported with timeout protection
        try:
            # Use a simple import test with timeout protection
            import signal
            import sys
            
            def timeout_handler(signum, frame):
                raise TimeoutError("VoxCPM import timed out")
            
            # Set timeout for import (only on Unix systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(5)  # 5 second timeout
            
            try:
                import voxcpm
                self.result.add_issue(
                    ValidationSeverity.INFO,
                    "voxcpm_import",
                    "VoxCPM module imported successfully"
                )
            finally:
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)  # Cancel timeout
            
        except TimeoutError:
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "voxcpm_import",
                "VoxCPM import timed out - may be slow to load",
                "VoxCPM is available but may take time to initialize"
            )
        except ImportError:
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "voxcpm_import",
                "VoxCPM module not available - voice generation will be disabled",
                "Install VoxCPM: pip install voxcpm"
            )
        except Exception as e:
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "voxcpm_import",
                f"Error importing VoxCPM: {e}"
            )
        
        # Continue with model validation only if import succeeded
        if any(issue.component == "voxcpm_import" and issue.severity == ValidationSeverity.INFO 
               for issue in self.result.issues):
            try:
                # Check if we can access the model path
                model_path = self.tts_config.model_path
                
                # For Hugging Face models, we can't easily validate without downloading
                # But we can check if it looks like a valid model identifier
                if '/' in model_path and not os.path.exists(model_path):
                    # Looks like a Hugging Face model identifier
                    if not model_path.startswith(('openbmb/', 'microsoft/', 'facebook/')):
                        self.result.add_issue(
                            ValidationSeverity.WARNING,
                            "voxcpm_model",
                            f"Model path may not be a valid Hugging Face identifier: {model_path}",
                            "Ensure the model exists on Hugging Face or provide a local path"
                        )
                    else:
                        self.result.add_issue(
                            ValidationSeverity.INFO,
                            "voxcpm_model",
                            f"VoxCPM model identifier appears valid: {model_path}"
                        )
                elif os.path.exists(model_path):
                    # Local model path
                    if os.path.isdir(model_path):
                        self.result.add_issue(
                            ValidationSeverity.INFO,
                            "voxcpm_model",
                            f"Local VoxCPM model directory found: {model_path}"
                        )
                    else:
                        self.result.add_issue(
                            ValidationSeverity.WARNING,
                            "voxcpm_model",
                            f"VoxCPM model path exists but is not a directory: {model_path}"
                        )
                else:
                    self.result.add_issue(
                        ValidationSeverity.WARNING,
                        "voxcpm_model",
                        f"VoxCPM model path not found locally: {model_path}",
                        "Model will be downloaded from Hugging Face on first use"
                    )
                
                # Check for required dependencies
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.result.add_issue(
                            ValidationSeverity.INFO,
                            "voxcpm_dependencies",
                            f"CUDA available for VoxCPM acceleration (devices: {torch.cuda.device_count()})"
                        )
                    else:
                        self.result.add_issue(
                            ValidationSeverity.WARNING,
                            "voxcpm_dependencies",
                            "CUDA not available - VoxCPM will use CPU (slower performance)",
                            "Install CUDA-compatible PyTorch for better performance"
                        )
                except ImportError:
                    self.result.add_issue(
                        ValidationSeverity.ERROR,
                        "voxcpm_dependencies",
                        "PyTorch not available - required for VoxCPM",
                        "Install PyTorch: pip install torch"
                    )
                    
            except Exception as e:
                self.result.add_issue(
                    ValidationSeverity.WARNING,
                    "voxcpm_model",
                    f"Error validating VoxCPM model: {e}"
                )
    
    def validate_system_dependencies(self) -> None:
        """Validate system dependencies like FFmpeg."""
        logger.info("Validating system dependencies...")
        
        # Check for FFmpeg (required for Discord audio)
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                # Extract version info
                output = result.stdout.decode('utf-8', errors='ignore')
                version_line = output.split('\n')[0] if output else "Unknown version"
                self.result.add_issue(
                    ValidationSeverity.INFO,
                    "ffmpeg",
                    f"FFmpeg available: {version_line}"
                )
            else:
                self.result.add_issue(
                    ValidationSeverity.WARNING,
                    "ffmpeg",
                    "FFmpeg command failed - audio playback may not work",
                    "Reinstall FFmpeg or check PATH configuration"
                )
                
        except subprocess.TimeoutExpired:
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "ffmpeg",
                "FFmpeg command timed out - may be installed but not responding"
            )
        except FileNotFoundError:
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "ffmpeg",
                "FFmpeg not found - Discord audio playback will not work",
                "Install FFmpeg and ensure it's in your PATH"
            )
        except Exception as e:
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "ffmpeg",
                f"Error checking FFmpeg: {e}"
            )
        
        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 8):
            self.result.add_issue(
                ValidationSeverity.CRITICAL,
                "python_version",
                f"Python version too old: {python_version.major}.{python_version.minor}",
                "Upgrade to Python 3.8 or newer"
            )
        elif python_version < (3, 9):
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "python_version",
                f"Python version is older: {python_version.major}.{python_version.minor}",
                "Consider upgrading to Python 3.9+ for better performance"
            )
        else:
            self.result.add_issue(
                ValidationSeverity.INFO,
                "python_version",
                f"Python version is compatible: {python_version.major}.{python_version.minor}.{python_version.micro}"
            )
    
    def validate_discord_configuration(self) -> None:
        """Validate Discord-specific configuration."""
        logger.info("Validating Discord configuration...")
        
        # Validate bot token format (basic check)
        token = self.bot_config.token
        if len(token) < 50:
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "discord_token",
                f"Bot token seems too short ({len(token)} chars) - may be invalid"
            )
        elif not any(token.startswith(prefix) for prefix in ['Bot ', 'MTk', 'Nz', 'OD']):
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "discord_token",
                "Bot token format may be invalid - ensure it's a proper Discord bot token"
            )
        else:
            self.result.add_issue(
                ValidationSeverity.INFO,
                "discord_token",
                "Bot token format appears valid"
            )
        
        # Validate channel IDs
        if self.bot_config.channel_id <= 0:
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "discord_channels",
                f"Invalid channel ID: {self.bot_config.channel_id}"
            )
        
        if self.bot_config.voice_channel_id is not None and self.bot_config.voice_channel_id <= 0:
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "discord_channels",
                f"Invalid voice channel ID: {self.bot_config.voice_channel_id}"
            )
        
        # Check if channel IDs are the same (potential issue)
        if (self.bot_config.voice_channel_id is not None and 
            self.bot_config.channel_id == self.bot_config.voice_channel_id):
            self.result.add_issue(
                ValidationSeverity.WARNING,
                "discord_channels",
                "Text and voice channels are the same - this may cause confusion"
            )
    
    def validate_ollama_configuration(self) -> None:
        """
        Validate Ollama AI configuration and connectivity.
        
        Requirement 1.5: Verify Ollama connectivity and model availability during startup.
        """
        logger.info("Validating Ollama configuration...")
        
        # Validate configuration values
        try:
            # Check base URL format
            if not self.ollama_config.base_url.startswith(('http://', 'https://')):
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "ollama_config",
                    f"Invalid Ollama base URL format: {self.ollama_config.base_url}",
                    "URL should start with http:// or https://"
                )
            
            # Check model name
            if not self.ollama_config.model_name.strip():
                self.result.add_issue(
                    ValidationSeverity.ERROR,
                    "ollama_config",
                    "Ollama model name cannot be empty"
                )
            
            # Check system prompt file
            prompt_file_path = Path(self.ollama_config.system_prompt_file)
            if not prompt_file_path.exists():
                self.result.add_issue(
                    ValidationSeverity.WARNING,
                    "ollama_config",
                    f"System prompt file not found: {prompt_file_path}",
                    "File will be created with default prompt if needed"
                )
            else:
                try:
                    import json
                    with open(prompt_file_path, 'r', encoding='utf-8') as f:
                        prompt_data = json.load(f)
                    
                    if 'system_prompt' not in prompt_data:
                        self.result.add_issue(
                            ValidationSeverity.ERROR,
                            "ollama_config",
                            f"System prompt file missing 'system_prompt' field: {prompt_file_path}"
                        )
                    elif not prompt_data['system_prompt'].strip():
                        self.result.add_issue(
                            ValidationSeverity.WARNING,
                            "ollama_config",
                            f"System prompt is empty in file: {prompt_file_path}"
                        )
                    else:
                        self.result.add_issue(
                            ValidationSeverity.INFO,
                            "ollama_config",
                            f"System prompt file validated: {len(prompt_data['system_prompt'])} characters"
                        )
                        
                except json.JSONDecodeError as e:
                    self.result.add_issue(
                        ValidationSeverity.ERROR,
                        "ollama_config",
                        f"Invalid JSON in system prompt file: {e}"
                    )
                except Exception as e:
                    self.result.add_issue(
                        ValidationSeverity.WARNING,
                        "ollama_config",
                        f"Error reading system prompt file: {e}"
                    )
            
            # Basic connectivity check (non-blocking)
            try:
                import asyncio
                import aiohttp
                
                async def check_ollama_connectivity():
                    try:
                        timeout = aiohttp.ClientTimeout(total=5.0)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(f"{self.ollama_config.base_url}/api/tags") as response:
                                if response.status == 200:
                                    return True, "Connected successfully"
                                else:
                                    return False, f"HTTP {response.status}"
                    except aiohttp.ClientConnectorError:
                        return False, "Connection refused - Ollama may not be running"
                    except asyncio.TimeoutError:
                        return False, "Connection timeout"
                    except Exception as e:
                        return False, str(e)
                
                # Run connectivity check with timeout
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're already in an async context, skip the connectivity check
                        self.result.add_issue(
                            ValidationSeverity.INFO,
                            "ollama_connectivity",
                            "Ollama connectivity check skipped (async context)",
                            "Connectivity will be checked during engine initialization"
                        )
                    else:
                        connected, message = loop.run_until_complete(
                            asyncio.wait_for(check_ollama_connectivity(), timeout=10.0)
                        )
                        
                        if connected:
                            self.result.add_issue(
                                ValidationSeverity.INFO,
                                "ollama_connectivity",
                                f"Ollama instance accessible: {message}"
                            )
                        else:
                            self.result.add_issue(
                                ValidationSeverity.WARNING,
                                "ollama_connectivity",
                                f"Ollama instance not accessible: {message}",
                                "Ensure Ollama is running and accessible at the configured URL"
                            )
                            
                except RuntimeError:
                    # Already in async context
                    self.result.add_issue(
                        ValidationSeverity.INFO,
                        "ollama_connectivity",
                        "Ollama connectivity check skipped (async context)",
                        "Connectivity will be checked during engine initialization"
                    )
                except asyncio.TimeoutError:
                    self.result.add_issue(
                        ValidationSeverity.WARNING,
                        "ollama_connectivity",
                        "Ollama connectivity check timed out",
                        "Ollama may be slow to respond or not running"
                    )
                except Exception as e:
                    self.result.add_issue(
                        ValidationSeverity.WARNING,
                        "ollama_connectivity",
                        f"Error checking Ollama connectivity: {e}"
                    )
                    
            except ImportError:
                self.result.add_issue(
                    ValidationSeverity.WARNING,
                    "ollama_connectivity",
                    "aiohttp not available - cannot check Ollama connectivity",
                    "Install aiohttp for connectivity validation"
                )
                
        except Exception as e:
            self.result.add_issue(
                ValidationSeverity.ERROR,
                "ollama_config",
                f"Error validating Ollama configuration: {e}"
            )
    
    def run_all_validations(self) -> ValidationResult:
        """
        Run all startup validations and return comprehensive results.
        
        Returns:
            ValidationResult: Complete validation results
        """
        logger.info("Starting comprehensive startup validation...")
        
        # Run all validation checks
        self.validate_reference_files()
        self.validate_save_directory()
        self.validate_voxcpm_accessibility()
        self.validate_ollama_configuration()
        self.validate_system_dependencies()
        self.validate_discord_configuration()
        
        # Generate summary
        self.result.summary = {
            'total_issues': len(self.result.issues),
            'critical_issues': len(self.result.get_issues_by_severity(ValidationSeverity.CRITICAL)),
            'errors': len(self.result.get_issues_by_severity(ValidationSeverity.ERROR)),
            'warnings': len(self.result.get_issues_by_severity(ValidationSeverity.WARNING)),
            'info': len(self.result.get_issues_by_severity(ValidationSeverity.INFO)),
            'can_start_bot': self.result.can_start,
            'voice_features_available': not any(
                issue.component.startswith(('voxcpm', 'reference_')) and 
                issue.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
                for issue in self.result.issues
            ),
            'ai_features_available': not any(
                issue.component.startswith('ollama_') and 
                issue.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
                for issue in self.result.issues
            )
        }
        
        # Log summary
        logger.info(f"Startup validation complete: {self.result.summary}")
        
        if self.result.has_critical_issues():
            logger.error("Critical issues found - bot cannot start")
        elif self.result.has_errors():
            logger.warning("Errors found - some features may be disabled")
        else:
            logger.info("All validations passed successfully")
        
        return self.result
    
    def log_validation_results(self) -> None:
        """Log all validation results in a structured format."""
        if not self.result.issues:
            logger.info("No validation issues found")
            return
        
        # Group issues by severity
        for severity in ValidationSeverity:
            issues = self.result.get_issues_by_severity(severity)
            if issues:
                logger.log(
                    logging.ERROR if severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
                    else logging.WARNING if severity == ValidationSeverity.WARNING
                    else logging.INFO,
                    f"{severity.value.upper()} issues ({len(issues)}):"
                )
                
                for issue in issues:
                    logger.log(
                        logging.ERROR if severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
                        else logging.WARNING if severity == ValidationSeverity.WARNING
                        else logging.INFO,
                        f"  {issue.component}: {issue.message}"
                    )
                    
                    if issue.suggestion:
                        logger.log(
                            logging.INFO,
                            f"    → {issue.suggestion}"
                        )