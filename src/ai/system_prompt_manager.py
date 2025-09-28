"""
System Prompt Manager for dynamic prompt configuration and reloading.
Handles loading, validation, and file watching for system prompt configuration.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import jsonschema
from jsonschema import validate, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class SystemPromptConfig:
    """Configuration structure for system prompts."""
    system_prompt: str
    version: str
    last_updated: str
    max_length: int
    fallback_prompt: str


class SystemPromptFileHandler(FileSystemEventHandler):
    """File system event handler for watching system prompt file changes."""
    
    def __init__(self, manager: 'SystemPromptManager'):
        self.manager = manager
        
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and Path(event.src_path) == self.manager.config_path:
            logger.info(f"System prompt file modified: {event.src_path}")
            self.manager.reload_prompt()
    
    def on_moved(self, event):
        """Handle file move events (some editors use move for save)."""
        if not event.is_directory and Path(event.dest_path) == self.manager.config_path:
            logger.info(f"System prompt file moved/saved: {event.dest_path}")
            self.manager.reload_prompt()
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and Path(event.src_path) == self.manager.config_path:
            logger.info(f"System prompt file created: {event.src_path}")
            self.manager.reload_prompt()


class SystemPromptManager:
    """
    Manages system prompt configuration with dynamic reloading capabilities.
    
    Handles loading system prompts from JSON configuration files, validates
    the structure, and provides file watching for automatic reloading.
    """
    
    # JSON schema for validating system prompt configuration
    PROMPT_SCHEMA = {
        "type": "object",
        "properties": {
            "system_prompt": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2000
            },
            "version": {
                "type": "string",
                "pattern": r"^\d+\.\d+$"
            },
            "last_updated": {
                "type": "string",
                "format": "date-time"
            },
            "max_length": {
                "type": "integer",
                "minimum": 50,
                "maximum": 2000
            },
            "fallback_prompt": {
                "type": "string",
                "minLength": 1,
                "maxLength": 500
            }
        },
        "required": ["system_prompt", "version", "last_updated", "max_length", "fallback_prompt"],
        "additionalProperties": False
    }
    
    DEFAULT_PROMPT = "You are a helpful assistant. Keep responses brief and friendly."
    
    def __init__(self, config_path: str):
        """
        Initialize the SystemPromptManager.
        
        Args:
            config_path: Path to the system prompt JSON configuration file
        """
        self.config_path = Path(config_path)
        self.current_config: Optional[SystemPromptConfig] = None
        self.observer: Optional[Observer] = None
        self.file_handler: Optional[SystemPromptFileHandler] = None
        
        # Load initial configuration
        self.load_system_prompt()
        
        # Start file watching
        self._start_file_watching()
    
    def load_system_prompt(self) -> bool:
        """
        Load system prompt from the configuration file.
        
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"System prompt file not found: {self.config_path}")
                self._use_fallback_config()
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Validate the configuration
            if not self.validate_prompt_config(config_data):
                logger.error("System prompt configuration validation failed")
                self._use_fallback_config()
                return False
            
            # Create configuration object
            self.current_config = SystemPromptConfig(
                system_prompt=config_data['system_prompt'],
                version=config_data['version'],
                last_updated=config_data['last_updated'],
                max_length=config_data['max_length'],
                fallback_prompt=config_data['fallback_prompt']
            )
            
            logger.info(f"System prompt loaded successfully (version: {self.current_config.version})")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in system prompt file: {e}")
            self._use_fallback_config()
            return False
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            self._use_fallback_config()
            return False
    
    def reload_prompt(self) -> bool:
        """
        Reload the system prompt from the configuration file.
        
        Returns:
            bool: True if reloaded successfully, False otherwise
        """
        logger.info("Reloading system prompt configuration")
        old_prompt = self.get_current_prompt() if self.current_config else None
        success = self.load_system_prompt()
        new_prompt = self.get_current_prompt()
        
        if old_prompt != new_prompt:
            logger.info(f"System prompt updated from '{old_prompt[:50]}...' to '{new_prompt[:50]}...'")
        
        return success
    
    def get_current_prompt(self) -> str:
        """
        Get the current system prompt.
        
        Returns:
            str: The current system prompt text
        """
        if self.current_config:
            return self.current_config.system_prompt
        return self.DEFAULT_PROMPT
    
    def get_fallback_prompt(self) -> str:
        """
        Get the fallback prompt.
        
        Returns:
            str: The fallback prompt text
        """
        if self.current_config:
            return self.current_config.fallback_prompt
        return self.DEFAULT_PROMPT
    
    def get_max_length(self) -> int:
        """
        Get the maximum allowed prompt length.
        
        Returns:
            int: Maximum prompt length
        """
        if self.current_config:
            return self.current_config.max_length
        return 500
    
    def validate_prompt_config(self, config_data: Dict[str, Any]) -> bool:
        """
        Validate system prompt configuration against JSON schema.
        
        Args:
            config_data: Configuration data to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            validate(instance=config_data, schema=self.PROMPT_SCHEMA)
            
            # Additional validation for prompt length
            prompt_length = len(config_data['system_prompt'])
            max_length = config_data['max_length']
            
            if prompt_length > max_length:
                logger.error(f"System prompt length ({prompt_length}) exceeds max_length ({max_length})")
                return False
            
            return True
            
        except ValidationError as e:
            logger.error(f"Schema validation failed: {e.message}")
            return False
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def validate_prompt(self, prompt: str) -> bool:
        """
        Validate a prompt string meets basic requirements.
        
        Args:
            prompt: Prompt string to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not prompt or not isinstance(prompt, str):
            return False
        
        if len(prompt.strip()) == 0:
            return False
        
        max_length = self.get_max_length()
        if len(prompt) > max_length:
            return False
        
        return True
    
    def _use_fallback_config(self):
        """Use a hardcoded fallback configuration."""
        self.current_config = SystemPromptConfig(
            system_prompt=self.DEFAULT_PROMPT,
            version="1.0",
            last_updated=datetime.now().isoformat(),
            max_length=500,
            fallback_prompt=self.DEFAULT_PROMPT
        )
        logger.info("Using fallback system prompt configuration")
    
    def _start_file_watching(self):
        """Start watching the configuration file for changes."""
        try:
            if self.config_path.exists():
                self.observer = Observer()
                self.file_handler = SystemPromptFileHandler(self)
                
                # Watch the directory containing the config file
                watch_dir = self.config_path.parent
                self.observer.schedule(self.file_handler, str(watch_dir), recursive=False)
                self.observer.start()
                
                logger.info(f"Started watching system prompt file: {self.config_path}")
            else:
                logger.warning(f"Cannot watch non-existent file: {self.config_path}")
                
        except Exception as e:
            logger.error(f"Failed to start file watching: {e}")
    
    def cleanup(self):
        """Clean up resources and stop file watching."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped system prompt file watching")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()