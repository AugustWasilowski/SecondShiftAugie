"""
Memory extraction and importance scoring functionality.

This module implements the MemoryExtractor class that analyzes conversations
to extract important facts, preferences, and knowledge worth storing in LTM
with importance scoring and deduplication logic.

Requirements addressed:
- 2.1: Extract and store facts worth remembering with importance scores (1-5)
- 2.3: Only persist items with importance >= configured minimum threshold
"""

import logging
import time
import json
from typing import List, Optional, Set, Tuple
from difflib import SequenceMatcher
import re

import aiohttp

from .models import ThreadCtx, Msg, NewMemory
from .config import MemoryConfig


logger = logging.getLogger(__name__)


class MemoryExtractorError(Exception):
    """Exception raised when memory extraction operations fail."""
    pass


class MemoryExtractor:
    """
    Handles memory extraction and importance scoring using LLM integration.
    
    The MemoryExtractor analyzes conversation exchanges to identify facts,
    preferences, and knowledge worth storing in long-term memory with
    appropriate importance scoring and deduplication.
    """
    
    def __init__(self, config: MemoryConfig):
        """
        Initialize the MemoryExtractor.
        
        Args:
            config: Memory configuration containing LLM settings and thresholds
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Memory extraction prompt template
        self.extraction_prompt = (
            "From the conversation, extract enduring facts/preferences worth remembering (if any). "
            "Return JSON list of objects {\"text\": \"...\", \"importance\": 1-5, \"kind\": \"...\"} "
            "with importance 1–5. Keep only reusable, cross-session info.\n\n"
            "Memory kinds:\n"
            "- episodic: Events, experiences, things that happened\n"
            "- semantic: Facts, knowledge, general information\n"
            "- entity: Information about people, places, things\n"
            "- artifact: References to files, links, code, created content\n\n"
            "Importance scale:\n"
            "1: Minor preference or temporary info\n"
            "2: Useful preference or context\n"
            "3: Important fact or strong preference\n"
            "4: Critical information or key relationship\n"
            "5: Essential identity or core characteristic\n\n"
            "Only extract memories that would be useful in future conversations. "
            "Skip temporary chat, greetings, or one-time requests."
        )
        
        # Similarity threshold for deduplication (0.0-1.0)
        self.similarity_threshold = 0.85
        
        logger.info("MemoryExtractor initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize the HTTP session for LLM requests.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            timeout = aiohttp.ClientTimeout(total=45.0)  # 45 second timeout for extraction
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Test connectivity to Ollama
            if not await self._check_ollama_connectivity():
                logger.error("Failed to connect to Ollama for memory extraction")
                return False
            
            logger.info("MemoryExtractor initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during MemoryExtractor initialization: {e}")
            return False
    
    async def extract_memories(self, ctx: ThreadCtx, messages: List[Msg], 
                             existing_memories: Optional[List[str]] = None) -> List[NewMemory]:
        """
        Extract memories from a conversation exchange.
        
        Args:
            ctx: Thread context for scoping
            messages: List of messages to analyze for memory extraction
            existing_memories: Optional list of existing memory texts for deduplication
            
        Returns:
            List[NewMemory]: List of extracted memories that meet importance threshold
            
        Raises:
            MemoryExtractorError: If memory extraction fails
        """
        if not ctx:
            raise MemoryExtractorError("Thread context cannot be None")
        if not messages:
            logger.debug(f"No messages to extract memories from for {ctx}")
            return []
        
        start_time = time.time()
        
        try:
            # Build the prompt for memory extraction
            prompt = self._build_extraction_prompt(messages)
            
            # Extract memories using LLM
            raw_memories = await self._extract_memories_with_llm(prompt)
            
            if not raw_memories:
                logger.debug(f"No memories extracted for {ctx}")
                return []
            
            # Parse and validate extracted memories
            parsed_memories = self._parse_extracted_memories(raw_memories)
            
            # Filter by importance threshold
            filtered_memories = self._filter_by_importance(parsed_memories)
            
            # Deduplicate against existing memories
            if existing_memories:
                deduplicated_memories = self._deduplicate_memories(filtered_memories, existing_memories)
            else:
                deduplicated_memories = filtered_memories
            
            elapsed = time.time() - start_time
            logger.info(f"Extracted {len(deduplicated_memories)} memories for {ctx} in {elapsed:.3f}s "
                       f"(filtered from {len(parsed_memories)} raw, threshold={self.config.memory_min_importance})")
            
            return deduplicated_memories
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to extract memories for {ctx} after {elapsed:.3f}s: {e}")
            
            # Return empty list on failure rather than raising
            # This allows the system to continue functioning
            return []
    
    async def cleanup(self):
        """Clean up resources and close connections."""
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info("MemoryExtractor cleanup completed")
    
    async def _check_ollama_connectivity(self) -> bool:
        """
        Check if Ollama instance is accessible.
        
        Returns:
            bool: True if accessible, False otherwise
        """
        try:
            if not self._session:
                return False
            
            async with self._session.get(f"{self.config.embed_ollama_url}/api/tags") as response:
                return response.status == 200
                
        except Exception as e:
            logger.debug(f"Ollama connectivity check failed: {e}")
            return False
    
    def _build_extraction_prompt(self, messages: List[Msg]) -> str:
        """
        Build the prompt for memory extraction.
        
        Args:
            messages: List of messages to analyze
            
        Returns:
            str: Complete prompt for LLM
        """
        prompt_parts = [self.extraction_prompt]
        prompt_parts.append("\nConversation to analyze:")
        
        # Add the conversation messages
        for msg in messages:
            role_label = msg.role.capitalize()
            prompt_parts.append(f"{role_label}: {msg.content}")
        
        prompt_parts.append("\nExtracted memories (JSON):")
        
        return "\n".join(prompt_parts)
    
    async def _extract_memories_with_llm(self, prompt: str) -> Optional[str]:
        """
        Extract memories using the LLM.
        
        Args:
            prompt: Complete prompt for memory extraction
            
        Returns:
            Optional[str]: Raw LLM response or None if failed
            
        Raises:
            MemoryExtractorError: If LLM request fails
        """
        if not self._session:
            raise MemoryExtractorError("HTTP session not initialized")
        
        request_data = {
            "model": self.config.embed_model,  # Use the same model as embeddings for consistency
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,  # Lower temperature for more consistent extraction
                "max_tokens": 1000   # Allow room for multiple memories
            }
        }
        
        try:
            async with self._session.post(
                f"{self.config.embed_ollama_url}/api/generate",
                json=request_data
            ) as response:
                
                if response.status == 200:
                    response_data = await response.json()
                    raw_response = response_data.get('response', '').strip()
                    
                    if not raw_response:
                        logger.debug("Empty response from LLM for memory extraction")
                        return None
                    
                    return raw_response
                else:
                    response_text = await response.text()
                    raise MemoryExtractorError(f"LLM request failed: HTTP {response.status} - {response_text}")
                    
        except aiohttp.ClientError as e:
            raise MemoryExtractorError(f"HTTP client error: {e}")
        except Exception as e:
            raise MemoryExtractorError(f"Unexpected error in LLM request: {e}")
    
    def _parse_extracted_memories(self, raw_response: str) -> List[NewMemory]:
        """
        Parse the raw LLM response into NewMemory objects.
        
        Args:
            raw_response: Raw response from LLM
            
        Returns:
            List[NewMemory]: Parsed and validated memory objects
        """
        memories = []
        
        try:
            # Try to extract JSON from the response
            json_text = self._extract_json_from_response(raw_response)
            
            if not json_text:
                logger.debug("No JSON found in LLM response")
                return memories
            
            # Parse JSON
            memory_data = json.loads(json_text)
            
            # Handle both single object and array responses
            if isinstance(memory_data, dict):
                memory_data = [memory_data]
            elif not isinstance(memory_data, list):
                logger.warning(f"Unexpected JSON structure: {type(memory_data)}")
                return memories
            
            # Convert to NewMemory objects
            for item in memory_data:
                try:
                    memory = self._create_memory_from_dict(item)
                    if memory:
                        memories.append(memory)
                except Exception as e:
                    logger.warning(f"Failed to parse memory item {item}: {e}")
                    continue
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"Raw response: {raw_response}")
        except Exception as e:
            logger.error(f"Unexpected error parsing memories: {e}")
        
        return memories
    
    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """
        Extract JSON content from LLM response.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Optional[str]: Extracted JSON string or None
        """
        # Look for JSON array or object patterns
        json_patterns = [
            r'\[.*\]',  # Array
            r'\{.*\}',  # Object
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                return match.group(0)
        
        # If no JSON patterns found, try the whole response
        response = response.strip()
        if response.startswith(('[', '{')):
            return response
        
        return None
    
    def _create_memory_from_dict(self, data: dict) -> Optional[NewMemory]:
        """
        Create a NewMemory object from dictionary data.
        
        Args:
            data: Dictionary containing memory data
            
        Returns:
            Optional[NewMemory]: Created memory object or None if invalid
        """
        try:
            # Extract required fields
            text = data.get('text', '').strip()
            importance = data.get('importance')
            kind = data.get('kind', 'semantic').lower()
            
            # Validate required fields
            if not text:
                logger.debug("Skipping memory with empty text")
                return None
            
            # Validate and convert importance
            if isinstance(importance, str):
                try:
                    importance = int(importance)
                except ValueError:
                    logger.debug(f"Invalid importance value: {importance}")
                    return None
            
            if not isinstance(importance, int) or importance < 1 or importance > 5:
                logger.debug(f"Invalid importance score: {importance}")
                return None
            
            # Validate kind
            valid_kinds = {'episodic', 'semantic', 'entity', 'artifact'}
            if kind not in valid_kinds:
                logger.debug(f"Invalid memory kind '{kind}', defaulting to 'semantic'")
                kind = 'semantic'
            
            # Create the memory object
            return NewMemory(
                kind=kind,
                text=text,
                importance=importance
            )
            
        except Exception as e:
            logger.warning(f"Error creating memory from data {data}: {e}")
            return None
    
    def _filter_by_importance(self, memories: List[NewMemory]) -> List[NewMemory]:
        """
        Filter memories by minimum importance threshold.
        
        Args:
            memories: List of memories to filter
            
        Returns:
            List[NewMemory]: Filtered memories meeting importance threshold
        """
        filtered = [
            memory for memory in memories 
            if memory.importance >= self.config.memory_min_importance
        ]
        
        if len(filtered) < len(memories):
            logger.debug(f"Filtered {len(memories) - len(filtered)} memories below importance threshold {self.config.memory_min_importance}")
        
        return filtered
    
    def _deduplicate_memories(self, new_memories: List[NewMemory], 
                            existing_memories: List[str]) -> List[NewMemory]:
        """
        Remove near-duplicate memories based on text similarity.
        
        Args:
            new_memories: List of new memories to check
            existing_memories: List of existing memory texts
            
        Returns:
            List[NewMemory]: Deduplicated memories
        """
        if not existing_memories:
            return new_memories
        
        deduplicated = []
        
        for memory in new_memories:
            is_duplicate = False
            
            # Check similarity against existing memories
            for existing_text in existing_memories:
                similarity = self._calculate_text_similarity(memory.text, existing_text)
                
                if similarity >= self.similarity_threshold:
                    logger.debug(f"Skipping duplicate memory (similarity={similarity:.3f}): {memory.text[:50]}...")
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                # Also check against other new memories to avoid duplicates within the batch
                for other_memory in deduplicated:
                    similarity = self._calculate_text_similarity(memory.text, other_memory.text)
                    
                    if similarity >= self.similarity_threshold:
                        logger.debug(f"Skipping duplicate within batch (similarity={similarity:.3f}): {memory.text[:50]}...")
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                deduplicated.append(memory)
        
        if len(deduplicated) < len(new_memories):
            logger.debug(f"Deduplicated {len(new_memories) - len(deduplicated)} similar memories")
        
        return deduplicated
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text strings.
        
        Args:
            text1: First text string
            text2: Second text string
            
        Returns:
            float: Similarity score between 0.0 and 1.0
        """
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts for comparison
        norm_text1 = self._normalize_text_for_comparison(text1)
        norm_text2 = self._normalize_text_for_comparison(text2)
        
        # Use SequenceMatcher for similarity calculation
        return SequenceMatcher(None, norm_text1, norm_text2).ratio()
    
    def _normalize_text_for_comparison(self, text: str) -> str:
        """
        Normalize text for similarity comparison.
        
        Args:
            text: Text to normalize
            
        Returns:
            str: Normalized text
        """
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove common punctuation
        normalized = re.sub(r'[.,!?;:]', '', normalized)
        
        return normalized.strip()
    
    def get_extraction_stats(self) -> dict:
        """
        Get statistics about memory extraction performance.
        
        Returns:
            dict: Statistics dictionary
        """
        return {
            "similarity_threshold": self.similarity_threshold,
            "min_importance": self.config.memory_min_importance,
            "model": self.config.embed_model,
            "ollama_url": self.config.embed_ollama_url
        }
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"MemoryExtractor(model={self.config.embed_model}, min_importance={self.config.memory_min_importance})"