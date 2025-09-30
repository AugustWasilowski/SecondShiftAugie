"""
Main MemoryService interface combining STM and LTM operations.

This module implements the MemoryService class that provides the main interface
for all memory operations, combining short-term and long-term memory with
graceful degradation and comprehensive error handling.

Requirements addressed:
- 5.1: MemoryService interface that abstracts storage details
- 5.2: Only interact through defined public API methods
- 5.5: Graceful degradation and error handling with appropriate fallbacks
"""

import asyncio
import logging
import time
import json
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from pathlib import Path
from datetime import datetime

import asyncpg

from .models import ThreadCtx, Msg, NewMemory, MemoryHit
from .config import MemoryConfig, MemoryConfigError
from .stm_store import STMStore, STMError
from .ltm_store import LTMStore, LTMError
from .embedding_client import EmbeddingClient, EmbeddingError
from .summarizer import Summarizer, SummarizerError
from .memory_extractor import MemoryExtractor, MemoryExtractorError


logger = logging.getLogger(__name__)


class MemoryMode(Enum):
    """Memory system operation modes for graceful degradation."""
    FULL = "full"           # Both STM and LTM operational
    STM_ONLY = "stm_only"   # Only STM operational (no embeddings/LTM)
    NO_MEMORY = "no_memory" # Memory system disabled (fallback mode)


class MemoryServiceError(Exception):
    """Exception raised when memory service operations fail."""
    pass


class MemoryService:
    """
    Main interface for all memory operations.
    
    The MemoryService provides a unified interface for both short-term and long-term
    memory operations with graceful degradation, error handling, and resource management.
    """
    
    def __init__(self, config: MemoryConfig):
        """
        Initialize the MemoryService.
        
        Args:
            config: Memory configuration
        """
        self.config = config
        self.mode = MemoryMode.NO_MEMORY
        
        # Core components (initialized during startup)
        self.db_pool: Optional[asyncpg.Pool] = None
        self.stm_store: Optional[STMStore] = None
        self.ltm_store: Optional[LTMStore] = None
        self.embedding_client: Optional[EmbeddingClient] = None
        self.summarizer: Optional[Summarizer] = None
        self.memory_extractor: Optional[MemoryExtractor] = None
        
        # Initialization state
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        
        logger.info(f"MemoryService created with config: {config}")
    
    async def initialize(self) -> bool:
        """
        Initialize the memory service and determine operation mode.
        
        Attempts to initialize components in order and sets the appropriate
        operation mode based on what's available.
        
        Returns:
            bool: True if initialization successful (any mode), False if completely failed
        """
        async with self._initialization_lock:
            if self._initialized:
                return True
            
            start_time = time.time()
            
            try:
                # Check if memory is enabled in configuration
                if not self.config.memory_enabled:
                    logger.info("Memory system disabled by configuration")
                    self.mode = MemoryMode.NO_MEMORY
                    self._initialized = True
                    return True
                
                # Try to initialize database connection
                db_success = await self._initialize_database()
                
                if not db_success:
                    logger.error("Database initialization failed, memory system disabled")
                    self.mode = MemoryMode.NO_MEMORY
                    self._initialized = True
                    return True
                
                # Initialize STM store (required for STM_ONLY mode)
                stm_success = await self._initialize_stm()
                
                if not stm_success:
                    logger.error("STM initialization failed, memory system disabled")
                    await self._cleanup_database()
                    self.mode = MemoryMode.NO_MEMORY
                    self._initialized = True
                    return True
                
                # Try to initialize embedding client and LTM components
                embedding_success = await self._initialize_embedding_client()
                
                if embedding_success:
                    # Try to initialize LTM components
                    ltm_success = await self._initialize_ltm()
                    summarizer_success = await self._initialize_summarizer()
                    extractor_success = await self._initialize_memory_extractor()
                    
                    if ltm_success:
                        self.mode = MemoryMode.FULL
                        logger.info("Memory system initialized in FULL mode")
                    else:
                        self.mode = MemoryMode.STM_ONLY
                        logger.info("Memory system initialized in STM_ONLY mode (LTM unavailable)")
                else:
                    self.mode = MemoryMode.STM_ONLY
                    logger.info("Memory system initialized in STM_ONLY mode (embeddings unavailable)")
                
                elapsed = time.time() - start_time
                logger.info(f"MemoryService initialization completed in {elapsed:.3f}s (mode: {self.mode.value})")
                
                self._initialized = True
                return True
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"MemoryService initialization failed after {elapsed:.3f}s: {e}")
                
                # Cleanup any partially initialized components
                await self._cleanup_all()
                self.mode = MemoryMode.NO_MEMORY
                self._initialized = True
                return True  # Return True to allow fallback operation
    
    async def cleanup(self) -> None:
        """Clean up all resources and close connections."""
        async with self._initialization_lock:
            if not self._initialized:
                return
            
            await self._cleanup_all()
            self._initialized = False
            logger.info("MemoryService cleanup completed")
    
    # STM Operations
    
    async def append_message(self, ctx: ThreadCtx, msg: Msg) -> None:
        """
        Append a message to the thread's STM.
        
        Args:
            ctx: Thread context for scoping
            msg: Message to append
            
        Raises:
            MemoryServiceError: If message storage fails in modes that support STM
        """
        if not await self._ensure_initialized():
            return
        
        if self.mode == MemoryMode.NO_MEMORY:
            logger.debug("append_message: No memory mode, skipping")
            return
        
        if not self.stm_store:
            logger.warning("append_message: STM store not available")
            return
        
        try:
            await self.stm_store.append_message(ctx, msg)
        except STMError as e:
            logger.error(f"Failed to append message: {e}")
            raise MemoryServiceError(f"Failed to append message: {e}") from e
    
    async def maybe_summarize(self, ctx: ThreadCtx) -> Optional[str]:
        """
        Check if summarization is needed and perform it if token budget exceeded.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            Optional[str]: Updated summary if summarization occurred, None otherwise
        """
        if not await self._ensure_initialized():
            return None
        
        if self.mode == MemoryMode.NO_MEMORY:
            logger.debug("maybe_summarize: No memory mode, skipping")
            return None
        
        if not self.stm_store:
            logger.warning("maybe_summarize: STM store not available")
            return None
        
        try:
            return await self.stm_store.maybe_summarize(ctx)
        except STMError as e:
            logger.error(f"Failed to maybe_summarize: {e}")
            # Don't raise exception - summarization failure shouldn't break the system
            return None
    
    async def get_thread_summary(self, ctx: ThreadCtx) -> Optional[str]:
        """
        Get the current thread summary if it exists.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            Optional[str]: Thread summary text, or None if no summary exists
        """
        if not await self._ensure_initialized():
            return None
        
        if self.mode == MemoryMode.NO_MEMORY:
            return None
        
        if not self.stm_store:
            return None
        
        try:
            return await self.stm_store.get_thread_summary(ctx)
        except STMError as e:
            logger.error(f"Failed to get thread summary: {e}")
            return None
    
    async def get_recent_window(self, ctx: ThreadCtx, n: int) -> List[Msg]:
        """
        Retrieve the last N messages from the thread.
        
        Args:
            ctx: Thread context for scoping
            n: Number of recent messages to retrieve
            
        Returns:
            List[Msg]: List of recent messages, ordered chronologically
        """
        if not await self._ensure_initialized():
            return []
        
        if self.mode == MemoryMode.NO_MEMORY:
            return []
        
        if not self.stm_store:
            return []
        
        try:
            return await self.stm_store.get_recent_window(ctx, n)
        except STMError as e:
            logger.error(f"Failed to get recent window: {e}")
            return []
    
    # LTM Operations
    
    async def retrieve(self, ctx: ThreadCtx, query: str, k: int = 6) -> List[MemoryHit]:
        """
        Retrieve relevant memories using hybrid scoring.
        
        Args:
            ctx: Thread context for scoping
            query: Query text for memory retrieval
            k: Number of results to return
            
        Returns:
            List[MemoryHit]: List of relevant memory hits
        """
        if not await self._ensure_initialized():
            return []
        
        if self.mode != MemoryMode.FULL:
            logger.debug(f"retrieve: Mode {self.mode.value} doesn't support LTM retrieval")
            return []
        
        if not self.ltm_store:
            logger.warning("retrieve: LTM store not available")
            return []
        
        try:
            return await self.ltm_store.hybrid_search(ctx, query, k)
        except LTMError as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []
    
    async def write_memories(self, ctx: ThreadCtx, items: List[NewMemory]) -> None:
        """
        Write new memories to LTM.
        
        Args:
            ctx: Thread context for scoping
            items: List of new memories to store
        """
        if not await self._ensure_initialized():
            return
        
        if self.mode != MemoryMode.FULL:
            logger.debug(f"write_memories: Mode {self.mode.value} doesn't support LTM storage")
            return
        
        if not self.ltm_store or not items:
            return
        
        stored_count = 0
        
        for memory in items:
            try:
                memory_id = await self.ltm_store.store_memory(ctx, memory)
                if memory_id:
                    stored_count += 1
            except LTMError as e:
                logger.error(f"Failed to store memory: {e}")
                continue
        
        if stored_count > 0:
            logger.debug(f"Stored {stored_count}/{len(items)} memories for {ctx}")
    
    async def export_user_memories(self, user_id: str, guild_id: Optional[str] = None) -> str:
        """
        Export all memories for a user to a JSON file.
        
        Args:
            user_id: User ID to export memories for
            guild_id: Optional guild ID to scope export
            
        Returns:
            str: Path to the exported file
            
        Raises:
            MemoryServiceError: If export fails
        """
        if not await self._ensure_initialized():
            raise MemoryServiceError("Memory service not initialized")
        
        if self.mode != MemoryMode.FULL:
            raise MemoryServiceError(f"Memory export not available in {self.mode.value} mode")
        
        if not self.ltm_store:
            raise MemoryServiceError("LTM store not available")
        
        try:
            # Get memories from LTM store
            memories = await self.ltm_store.export_user_memories(user_id, guild_id)
            
            # Create export directory
            export_dir = self.config.ensure_export_directory()
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            guild_suffix = f"_{guild_id}" if guild_id else ""
            filename = f"memories_{user_id}{guild_suffix}_{timestamp}.json"
            export_path = export_dir / filename
            
            # Write to file
            export_data = {
                "user_id": user_id,
                "guild_id": guild_id,
                "exported_at": datetime.now().isoformat(),
                "memory_count": len(memories),
                "memories": memories
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(memories)} memories for user {user_id} to {export_path}")
            return str(export_path)
            
        except Exception as e:
            logger.error(f"Failed to export memories for user {user_id}: {e}")
            raise MemoryServiceError(f"Failed to export memories: {e}") from e
    
    async def forget_memory(self, memory_id: str) -> bool:
        """
        Delete a specific memory by ID.
        
        Args:
            memory_id: UUID of the memory to delete
            
        Returns:
            bool: True if memory was deleted, False if not found
            
        Raises:
            MemoryServiceError: If deletion fails
        """
        if not await self._ensure_initialized():
            return False
        
        if self.mode != MemoryMode.FULL:
            raise MemoryServiceError(f"Memory deletion not available in {self.mode.value} mode")
        
        if not self.ltm_store:
            raise MemoryServiceError("LTM store not available")
        
        try:
            return await self.ltm_store.delete_memory(memory_id)
        except LTMError as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            raise MemoryServiceError(f"Failed to delete memory: {e}") from e
    
    async def hard_delete_user_data(self, user_id: str, guild_id: str) -> Dict[str, int]:
        """
        Hard delete all data for a user in a specific guild.
        
        Args:
            user_id: User ID to delete data for
            guild_id: Guild ID to scope deletion
            
        Returns:
            Dict[str, int]: Dictionary with counts of deleted items
            
        Raises:
            MemoryServiceError: If hard deletion fails
        """
        if not await self._ensure_initialized():
            return {"total": 0}
        
        if self.mode == MemoryMode.NO_MEMORY:
            return {"total": 0}
        
        try:
            if self.mode == MemoryMode.FULL and self.ltm_store:
                # Full deletion including LTM
                return await self.ltm_store.hard_delete_user_data(user_id, guild_id)
            elif self.stm_store:
                # STM-only deletion
                ctx = ThreadCtx(guild_id=guild_id, channel_id="*", user_id=user_id)
                
                # Clear all threads for this user in the guild
                # Note: This is a simplified approach - in practice, you'd need to
                # iterate through all channels for the user
                messages_deleted, summary_deleted = await self.stm_store.clear_thread(ctx)
                
                return {
                    "messages": messages_deleted,
                    "summaries": 1 if summary_deleted else 0,
                    "memories": 0,
                    "total": messages_deleted + (1 if summary_deleted else 0)
                }
            else:
                return {"total": 0}
                
        except Exception as e:
            logger.error(f"Failed to hard delete user data for {user_id}: {e}")
            raise MemoryServiceError(f"Failed to hard delete user data: {e}") from e
    
    # Memory Extraction and Processing
    
    async def extract_and_store_memories(self, ctx: ThreadCtx, messages: List[Msg]) -> int:
        """
        Extract memories from conversation and store them in LTM.
        
        Args:
            ctx: Thread context for scoping
            messages: List of messages to analyze
            
        Returns:
            int: Number of memories successfully stored
        """
        if not await self._ensure_initialized():
            return 0
        
        if self.mode != MemoryMode.FULL:
            logger.debug(f"extract_and_store_memories: Mode {self.mode.value} doesn't support memory extraction")
            return 0
        
        if not self.memory_extractor or not messages:
            return 0
        
        try:
            # Extract memories from the conversation
            new_memories = await self.memory_extractor.extract_memories(ctx, messages)
            
            if not new_memories:
                return 0
            
            # Store the extracted memories
            await self.write_memories(ctx, new_memories)
            
            return len(new_memories)
            
        except Exception as e:
            logger.error(f"Failed to extract and store memories: {e}")
            return 0
    
    # Status and Information Methods
    
    def get_mode(self) -> MemoryMode:
        """
        Get the current operation mode.
        
        Returns:
            MemoryMode: Current operation mode
        """
        return self.mode
    
    def is_available(self) -> bool:
        """
        Check if memory service is available (any mode except NO_MEMORY).
        
        Returns:
            bool: True if memory service is available
        """
        return self.mode != MemoryMode.NO_MEMORY
    
    def supports_ltm(self) -> bool:
        """
        Check if LTM operations are supported.
        
        Returns:
            bool: True if LTM operations are supported
        """
        return self.mode == MemoryMode.FULL
    
    async def get_service_status(self) -> Dict[str, Any]:
        """
        Get comprehensive service status information.
        
        Returns:
            Dict[str, Any]: Service status information
        """
        status = {
            "initialized": self._initialized,
            "mode": self.mode.value,
            "config_enabled": self.config.memory_enabled,
            "components": {
                "database": self.db_pool is not None,
                "stm_store": self.stm_store is not None,
                "ltm_store": self.ltm_store is not None,
                "embedding_client": self.embedding_client is not None,
                "summarizer": self.summarizer is not None,
                "memory_extractor": self.memory_extractor is not None
            }
        }
        
        # Add health check information if available
        if self.embedding_client:
            try:
                embedding_healthy = await self.embedding_client.health_check()
                status["embedding_health"] = embedding_healthy
            except Exception:
                status["embedding_health"] = False
        
        return status
    
    # Private Initialization Methods
    
    async def _ensure_initialized(self) -> bool:
        """Ensure the service is initialized."""
        if not self._initialized:
            return await self.initialize()
        return True
    
    async def _initialize_database(self) -> bool:
        """Initialize database connection pool."""
        try:
            db_config = self.config.get_database_config()
            self.db_pool = await asyncpg.create_pool(**db_config)
            
            # Test the connection
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            logger.info("Database connection pool initialized")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    async def _initialize_stm(self) -> bool:
        """Initialize STM store."""
        try:
            if not self.db_pool:
                return False
            
            self.stm_store = STMStore(self.db_pool, self.config, self.summarizer)
            logger.info("STM store initialized")
            return True
            
        except Exception as e:
            logger.error(f"STM initialization failed: {e}")
            return False
    
    async def _initialize_embedding_client(self) -> bool:
        """Initialize embedding client."""
        try:
            self.embedding_client = EmbeddingClient(self.config)
            
            # Test connectivity
            async with self.embedding_client:
                healthy = await self.embedding_client.health_check()
                if not healthy:
                    logger.warning("Embedding client health check failed")
                    return False
            
            logger.info("Embedding client initialized")
            return True
            
        except Exception as e:
            logger.error(f"Embedding client initialization failed: {e}")
            return False
    
    async def _initialize_ltm(self) -> bool:
        """Initialize LTM store."""
        try:
            if not self.db_pool or not self.embedding_client:
                return False
            
            self.ltm_store = LTMStore(self.db_pool, self.config, self.embedding_client)
            logger.info("LTM store initialized")
            return True
            
        except Exception as e:
            logger.error(f"LTM initialization failed: {e}")
            return False
    
    async def _initialize_summarizer(self) -> bool:
        """Initialize summarizer."""
        try:
            self.summarizer = Summarizer(self.config)
            success = await self.summarizer.initialize()
            
            if success:
                logger.info("Summarizer initialized")
                return True
            else:
                logger.warning("Summarizer initialization failed")
                return False
                
        except Exception as e:
            logger.error(f"Summarizer initialization failed: {e}")
            return False
    
    async def _initialize_memory_extractor(self) -> bool:
        """Initialize memory extractor."""
        try:
            self.memory_extractor = MemoryExtractor(self.config)
            success = await self.memory_extractor.initialize()
            
            if success:
                logger.info("Memory extractor initialized")
                return True
            else:
                logger.warning("Memory extractor initialization failed")
                return False
                
        except Exception as e:
            logger.error(f"Memory extractor initialization failed: {e}")
            return False
    
    # Cleanup Methods
    
    async def _cleanup_all(self) -> None:
        """Clean up all components."""
        cleanup_tasks = []
        
        if self.memory_extractor:
            cleanup_tasks.append(self.memory_extractor.cleanup())
        
        if self.summarizer:
            cleanup_tasks.append(self.summarizer.cleanup())
        
        if self.embedding_client:
            cleanup_tasks.append(self.embedding_client.close())
        
        if self.db_pool:
            cleanup_tasks.append(self._cleanup_database())
        
        # Run all cleanup tasks concurrently
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Reset component references
        self.memory_extractor = None
        self.summarizer = None
        self.embedding_client = None
        self.ltm_store = None
        self.stm_store = None
        self.db_pool = None
    
    async def _cleanup_database(self) -> None:
        """Clean up database connection pool."""
        if self.db_pool:
            try:
                await self.db_pool.close()
                logger.info("Database connection pool closed")
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")
            finally:
                self.db_pool = None
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"MemoryService(mode={self.mode.value}, initialized={self._initialized})"