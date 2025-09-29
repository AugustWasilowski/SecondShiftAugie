# AI module for Ollama integration

from .ollama_engine import OllamaEngine, AIResponse
from .system_prompt_manager import SystemPromptManager, SystemPromptConfig

__all__ = ['OllamaEngine', 'AIResponse', 'SystemPromptManager', 'SystemPromptConfig']