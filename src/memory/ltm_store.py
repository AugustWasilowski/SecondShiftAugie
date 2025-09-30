"""
Long-Term Memory (LTM) store implementation with pgvector integration.

This module implements the LTMStore class that manages persistent memory storage
and retrieval using PostgreSQL with pgvector for vector similarity search.

Requirements addressed:
- 2.1: Extract and store memories in LTM with importance scores
- 2.2: Retrieve relevant memories using hybrid scoring
- 2.4: Return top-k results ranked by combined similarity, recency, and importance
"""

import logging
import time
import uuid
import json
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta

import asyncpg
from asyncpg import Connection

from .models import ThreadCtx, NewMemory, MemoryHit
from .config import MemoryConfig
from .embedding_client import EmbeddingClient, EmbeddingError


logger = logging.getLogger(__name__)


class LTMError(Exception):
    """Exception raised when LTM operations fail."""
    pass


class LTMStore:
    """
    Manages long-term memory storage and retrieval with pgvector integration.
    
    The LTMStore handles persistent memory operations including storage with embeddings,
    vector similarity search, hybrid scoring, and memory management operations.
    """
    
    def __init__(self, db_pool: asyncpg.Pool, config: MemoryConfig, embedding_client: EmbeddingClient):
        """
        Initialize the LTM store.
        
        Args:
            db_pool: AsyncPG connection pool
            config: Memory configuration
            embedding_client: Client for generating embeddings
        """
        self.db_pool = db_pool
        self.config = config
        self.embedding_client = embedding_client
        
        # Retrieval configuration
        self.top_k = config.retrieve_top_k
        self.recency_window_days = config.recency_window_days
        self.similarity_weight = config.boost_similarity
        self.recency_weight = config.boost_recency
        self.importance_weight = config.boost_importance
        self.min_importance = config.memory_min_importance
        
        logger.info(f"Initialized LTMStore with top_k={self.top_k}, "
                   f"weights=({self.similarity_weight:.1f}, {self.recency_weight:.1f}, {self.importance_weight:.1f})")
    
    async def store_memory(self, ctx: ThreadCtx, memory: NewMemory, embedding: Optional[List[float]] = None) -> str:
        """
        Store a memory in LTM with embedding.
        
        Args:
            ctx: Thread context for scoping
            memory: Memory to store
            embedding: Pre-computed embedding (optional, will generate if not provided)
            
        Returns:
            str: UUID of the stored memory
            
        Raises:
            LTMError: If memory storage fails
        """
        if not ctx:
            raise LTMError("Thread context cannot be None")
        if not memory:
            raise LTMError("Memory cannot be None")
        
        # Check importance threshold
        if memory.importance < self.min_importance:
            logger.debug(f"Skipping memory storage: importance {memory.importance} < {self.min_importance}")
            return ""
        
        start_time = time.time()
        memory_id = str(uuid.uuid4())
        
        try:
            # Generate embedding if not provided
            if embedding is None:
                try:
                    embedding = await self.embedding_client.embed_text(memory.text)
                except EmbeddingError as e:
                    logger.error(f"Failed to generate embedding for memory: {e}")
                    raise LTMError(f"Failed to generate embedding: {e}") from e
            
            # Validate embedding
            if not embedding or not isinstance(embedding, list):
                raise LTMError("Invalid embedding: must be a non-empty list")
            
            # Store in database
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO memories (id, guild_id, channel_id, user_id, kind, text, importance, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, memory_id, ctx.guild_id, ctx.channel_id, ctx.user_id, 
                    memory.kind, memory.text, memory.importance, embedding)
            
            elapsed = time.time() - start_time
            logger.debug(f"Stored memory {memory_id} for {ctx} in {elapsed:.3f}s "
                        f"(kind={memory.kind}, importance={memory.importance})")
            
            return memory_id
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to store memory for {ctx} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Failed to store memory: {e}") from e
    
    async def vector_search(self, ctx: ThreadCtx, query_embedding: List[float], k: int) -> List[MemoryHit]:
        """
        Perform vector similarity search using HNSW index.
        
        Args:
            ctx: Thread context for scoping
            query_embedding: Query embedding vector
            k: Number of results to return
            
        Returns:
            List[MemoryHit]: List of memory hits ordered by similarity
            
        Raises:
            LTMError: If vector search fails
        """
        if not ctx:
            raise LTMError("Thread context cannot be None")
        if not query_embedding or not isinstance(query_embedding, list):
            raise LTMError("Query embedding must be a non-empty list")
        if k <= 0:
            raise LTMError("k must be positive")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id,
                        text,
                        kind,
                        importance,
                        created_at,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM memories
                    WHERE guild_id = $2 AND user_id = $3
                    AND importance >= $4
                    ORDER BY embedding <=> $1::vector
                    LIMIT $5
                """, query_embedding, ctx.guild_id, ctx.user_id, self.min_importance, k)
            
            # Convert rows to MemoryHit objects
            hits = []
            for row in rows:
                hit = MemoryHit(
                    id=str(row['id']),
                    text=row['text'],
                    importance=row['importance'],
                    similarity=float(row['similarity']),
                    created_at=row['created_at'].isoformat(),
                    kind=row['kind']
                )
                hits.append(hit)
            
            elapsed = time.time() - start_time
            logger.debug(f"Vector search for {ctx} returned {len(hits)} results in {elapsed:.3f}s")
            
            return hits
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed vector search for {ctx} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Vector search failed: {e}") from e
    
    async def hybrid_search(self, ctx: ThreadCtx, query: str, k: Optional[int] = None) -> List[MemoryHit]:
        """
        Perform hybrid search with similarity + recency + importance scoring.
        
        Args:
            ctx: Thread context for scoping
            query: Query text
            k: Number of results to return (defaults to config value)
            
        Returns:
            List[MemoryHit]: List of memory hits ordered by combined score
            
        Raises:
            LTMError: If hybrid search fails
        """
        if not ctx:
            raise LTMError("Thread context cannot be None")
        if not query or not query.strip():
            raise LTMError("Query cannot be empty")
        
        k = k or self.top_k
        start_time = time.time()
        
        try:
            # Generate query embedding
            try:
                query_embedding = await self.embedding_client.embed_text(query.strip())
            except EmbeddingError as e:
                logger.error(f"Failed to generate query embedding: {e}")
                raise LTMError(f"Failed to generate query embedding: {e}") from e
            
            # Perform hybrid search with combined scoring
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    WITH scored_memories AS (
                        SELECT 
                            id,
                            text,
                            kind,
                            importance,
                            created_at,
                            1 - (embedding <=> $1::vector) AS similarity,
                            EXTRACT(EPOCH FROM (now() - created_at)) / 60.0 AS minutes_ago
                        FROM memories
                        WHERE guild_id = $2 AND user_id = $3
                        AND importance >= $4
                    ),
                    ranked_memories AS (
                        SELECT *,
                            -- Hybrid scoring formula
                            ($5 * similarity + 
                             $6 * GREATEST(0, 1 - (minutes_ago / (60.0 * 24.0 * $7))) + 
                             $8 * (importance / 5.0)) AS combined_score
                        FROM scored_memories
                    )
                    SELECT 
                        id, text, kind, importance, created_at, similarity, combined_score
                    FROM ranked_memories
                    ORDER BY combined_score DESC
                    LIMIT $9
                """, query_embedding, ctx.guild_id, ctx.user_id, self.min_importance,
                    self.similarity_weight, self.recency_weight, self.recency_window_days,
                    self.importance_weight, k)
            
            # Convert rows to MemoryHit objects
            hits = []
            for row in rows:
                hit = MemoryHit(
                    id=str(row['id']),
                    text=row['text'],
                    importance=row['importance'],
                    similarity=float(row['similarity']),
                    created_at=row['created_at'].isoformat(),
                    kind=row['kind']
                )
                hits.append(hit)
            
            elapsed = time.time() - start_time
            logger.debug(f"Hybrid search for {ctx} returned {len(hits)} results in {elapsed:.3f}s")
            
            return hits
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed hybrid search for {ctx} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Hybrid search failed: {e}") from e
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: UUID of the memory to delete
            
        Returns:
            bool: True if memory was deleted, False if not found
            
        Raises:
            LTMError: If memory deletion fails
        """
        if not memory_id or not memory_id.strip():
            raise LTMError("Memory ID cannot be empty")
        
        start_time = time.time()
        
        try:
            # Validate UUID format
            try:
                uuid.UUID(memory_id)
            except ValueError:
                raise LTMError(f"Invalid memory ID format: {memory_id}")
            
            async with self.db_pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM memories WHERE id = $1
                """, memory_id)
                
                # Extract number of deleted rows from result
                deleted_count = int(result.split()[-1]) if result and result.split() else 0
                
                elapsed = time.time() - start_time
                if deleted_count > 0:
                    logger.info(f"Deleted memory {memory_id} in {elapsed:.3f}s")
                    return True
                else:
                    logger.debug(f"Memory {memory_id} not found for deletion in {elapsed:.3f}s")
                    return False
                    
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to delete memory {memory_id} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Failed to delete memory: {e}") from e
    
    async def export_user_memories(self, user_id: str, guild_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Export all memories for a user.
        
        Args:
            user_id: User ID to export memories for
            guild_id: Optional guild ID to scope export (if None, exports from all guilds)
            
        Returns:
            List[Dict]: List of memory dictionaries for export
            
        Raises:
            LTMError: If memory export fails
        """
        if not user_id or not user_id.strip():
            raise LTMError("User ID cannot be empty")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                if guild_id:
                    # Export memories for specific guild
                    rows = await conn.fetch("""
                        SELECT 
                            id, guild_id, channel_id, user_id, kind, text, 
                            importance, created_at
                        FROM memories
                        WHERE user_id = $1 AND guild_id = $2
                        ORDER BY created_at DESC
                    """, user_id, guild_id)
                else:
                    # Export memories from all guilds
                    rows = await conn.fetch("""
                        SELECT 
                            id, guild_id, channel_id, user_id, kind, text, 
                            importance, created_at
                        FROM memories
                        WHERE user_id = $1
                        ORDER BY created_at DESC
                    """, user_id)
            
            # Convert rows to dictionaries
            memories = []
            for row in rows:
                memory_dict = {
                    'id': str(row['id']),
                    'guild_id': row['guild_id'],
                    'channel_id': row['channel_id'],
                    'user_id': row['user_id'],
                    'kind': row['kind'],
                    'text': row['text'],
                    'importance': row['importance'],
                    'created_at': row['created_at'].isoformat()
                }
                memories.append(memory_dict)
            
            elapsed = time.time() - start_time
            logger.info(f"Exported {len(memories)} memories for user {user_id} in {elapsed:.3f}s")
            
            return memories
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to export memories for user {user_id} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Failed to export memories: {e}") from e
    
    async def hard_delete_user_data(self, user_id: str, guild_id: str) -> Dict[str, int]:
        """
        Hard delete all data for a user in a specific guild.
        
        Args:
            user_id: User ID to delete data for
            guild_id: Guild ID to scope deletion
            
        Returns:
            Dict[str, int]: Dictionary with counts of deleted items
            
        Raises:
            LTMError: If hard deletion fails
        """
        if not user_id or not user_id.strip():
            raise LTMError("User ID cannot be empty")
        if not guild_id or not guild_id.strip():
            raise LTMError("Guild ID cannot be empty")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    # Delete memories
                    memories_result = await conn.execute("""
                        DELETE FROM memories 
                        WHERE user_id = $1 AND guild_id = $2
                    """, user_id, guild_id)
                    
                    # Delete thread summaries
                    summaries_result = await conn.execute("""
                        DELETE FROM thread_summaries 
                        WHERE user_id = $1 AND guild_id = $2
                    """, user_id, guild_id)
                    
                    # Delete messages
                    messages_result = await conn.execute("""
                        DELETE FROM messages 
                        WHERE user_id = $1 AND guild_id = $2
                    """, user_id, guild_id)
                    
                    # Extract counts from results
                    memories_deleted = int(memories_result.split()[-1]) if memories_result and memories_result.split() else 0
                    summaries_deleted = int(summaries_result.split()[-1]) if summaries_result and summaries_result.split() else 0
                    messages_deleted = int(messages_result.split()[-1]) if messages_result and messages_result.split() else 0
                    
                    deletion_counts = {
                        'memories': memories_deleted,
                        'summaries': summaries_deleted,
                        'messages': messages_deleted,
                        'total': memories_deleted + summaries_deleted + messages_deleted
                    }
                    
                    elapsed = time.time() - start_time
                    logger.info(f"Hard deleted user data for {user_id} in guild {guild_id} in {elapsed:.3f}s: {deletion_counts}")
                    
                    return deletion_counts
                    
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to hard delete user data for {user_id} in guild {guild_id} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Failed to hard delete user data: {e}") from e
    
    async def get_memory_by_id(self, memory_id: str) -> Optional[MemoryHit]:
        """
        Retrieve a specific memory by ID.
        
        Args:
            memory_id: UUID of the memory to retrieve
            
        Returns:
            Optional[MemoryHit]: Memory hit if found, None otherwise
            
        Raises:
            LTMError: If memory retrieval fails
        """
        if not memory_id or not memory_id.strip():
            raise LTMError("Memory ID cannot be empty")
        
        try:
            # Validate UUID format
            try:
                uuid.UUID(memory_id)
            except ValueError:
                raise LTMError(f"Invalid memory ID format: {memory_id}")
            
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT id, text, kind, importance, created_at
                    FROM memories
                    WHERE id = $1
                """, memory_id)
                
                if not row:
                    return None
                
                hit = MemoryHit(
                    id=str(row['id']),
                    text=row['text'],
                    importance=row['importance'],
                    similarity=1.0,  # Not applicable for direct lookup
                    created_at=row['created_at'].isoformat(),
                    kind=row['kind']
                )
                
                return hit
                
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            raise LTMError(f"Failed to get memory: {e}") from e
    
    async def get_user_memory_stats(self, user_id: str, guild_id: str) -> Dict[str, Any]:
        """
        Get comprehensive memory statistics for a user.
        
        Args:
            user_id: User ID to get stats for
            guild_id: Guild ID to scope stats
            
        Returns:
            Dict[str, Any]: Memory statistics
            
        Raises:
            LTMError: If stats retrieval fails
        """
        if not user_id or not user_id.strip():
            raise LTMError("User ID cannot be empty")
        if not guild_id or not guild_id.strip():
            raise LTMError("Guild ID cannot be empty")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                # Get comprehensive memory stats
                row = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_memories,
                        AVG(importance) as avg_importance,
                        MIN(created_at) as oldest_memory,
                        MAX(created_at) as newest_memory,
                        COUNT(CASE WHEN kind = 'episodic' THEN 1 END) as episodic_count,
                        COUNT(CASE WHEN kind = 'semantic' THEN 1 END) as semantic_count,
                        COUNT(CASE WHEN kind = 'entity' THEN 1 END) as entity_count,
                        COUNT(CASE WHEN kind = 'artifact' THEN 1 END) as artifact_count,
                        COUNT(CASE WHEN importance >= 4 THEN 1 END) as high_importance_count,
                        COUNT(CASE WHEN created_at >= now() - interval '7 days' THEN 1 END) as recent_count
                    FROM memories
                    WHERE user_id = $1 AND guild_id = $2
                """, user_id, guild_id)
                
                stats = {
                    'total_memories': row['total_memories'] if row else 0,
                    'avg_importance': float(row['avg_importance']) if row and row['avg_importance'] else 0.0,
                    'oldest_memory': row['oldest_memory'].isoformat() if row and row['oldest_memory'] else None,
                    'newest_memory': row['newest_memory'].isoformat() if row and row['newest_memory'] else None,
                    'by_kind': {
                        'episodic': row['episodic_count'] if row else 0,
                        'semantic': row['semantic_count'] if row else 0,
                        'entity': row['entity_count'] if row else 0,
                        'artifact': row['artifact_count'] if row else 0
                    },
                    'high_importance_count': row['high_importance_count'] if row else 0,
                    'recent_count': row['recent_count'] if row else 0
                }
                
                elapsed = time.time() - start_time
                logger.debug(f"Retrieved memory stats for user {user_id} in guild {guild_id} in {elapsed:.3f}s")
                
                return stats
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to get memory stats for user {user_id} in guild {guild_id} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Failed to get memory stats: {e}") from e
    
    async def search_memories_by_text(self, ctx: ThreadCtx, text_query: str, k: int = 10) -> List[MemoryHit]:
        """
        Search memories by text content (without embeddings).
        
        Args:
            ctx: Thread context for scoping
            text_query: Text to search for
            k: Number of results to return
            
        Returns:
            List[MemoryHit]: List of matching memories
            
        Raises:
            LTMError: If text search fails
        """
        if not ctx:
            raise LTMError("Thread context cannot be None")
        if not text_query or not text_query.strip():
            raise LTMError("Text query cannot be empty")
        
        start_time = time.time()
        
        try:
            # Use PostgreSQL full-text search
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, text, kind, importance, created_at,
                        ts_rank(to_tsvector('english', text), plainto_tsquery('english', $1)) as text_rank
                    FROM memories
                    WHERE guild_id = $2 AND user_id = $3
                    AND importance >= $4
                    AND to_tsvector('english', text) @@ plainto_tsquery('english', $1)
                    ORDER BY text_rank DESC, created_at DESC
                    LIMIT $5
                """, text_query.strip(), ctx.guild_id, ctx.user_id, self.min_importance, k)
            
            # Convert rows to MemoryHit objects
            hits = []
            for row in rows:
                hit = MemoryHit(
                    id=str(row['id']),
                    text=row['text'],
                    importance=row['importance'],
                    similarity=float(row['text_rank']),  # Use text rank as similarity
                    created_at=row['created_at'].isoformat(),
                    kind=row['kind']
                )
                hits.append(hit)
            
            elapsed = time.time() - start_time
            logger.debug(f"Text search for {ctx} returned {len(hits)} results in {elapsed:.3f}s")
            
            return hits
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed text search for {ctx} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Text search failed: {e}") from e
    
    async def get_recent_memories(self, ctx: ThreadCtx, days: int = 7, k: int = 20) -> List[MemoryHit]:
        """
        Get recent memories for a user within a time window.
        
        Args:
            ctx: Thread context for scoping
            days: Number of days to look back
            k: Maximum number of results to return
            
        Returns:
            List[MemoryHit]: List of recent memories
            
        Raises:
            LTMError: If recent memories retrieval fails
        """
        if not ctx:
            raise LTMError("Thread context cannot be None")
        if days <= 0:
            raise LTMError("Days must be positive")
        if k <= 0:
            raise LTMError("k must be positive")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, text, kind, importance, created_at
                    FROM memories
                    WHERE guild_id = $1 AND user_id = $2
                    AND importance >= $3
                    AND created_at >= now() - interval '%s days'
                    ORDER BY created_at DESC
                    LIMIT $4
                """ % days, ctx.guild_id, ctx.user_id, self.min_importance, k)
            
            # Convert rows to MemoryHit objects
            hits = []
            for row in rows:
                hit = MemoryHit(
                    id=str(row['id']),
                    text=row['text'],
                    importance=row['importance'],
                    similarity=1.0,  # Not applicable for recency search
                    created_at=row['created_at'].isoformat(),
                    kind=row['kind']
                )
                hits.append(hit)
            
            elapsed = time.time() - start_time
            logger.debug(f"Retrieved {len(hits)} recent memories for {ctx} in {elapsed:.3f}s")
            
            return hits
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to get recent memories for {ctx} after {elapsed:.3f}s: {e}")
            raise LTMError(f"Failed to get recent memories: {e}") from e
    
    def __str__(self) -> str:
        """String representation for logging."""
        return (f"LTMStore(top_k={self.top_k}, min_importance={self.min_importance}, "
                f"weights=({self.similarity_weight:.1f}, {self.recency_weight:.1f}, {self.importance_weight:.1f}))")