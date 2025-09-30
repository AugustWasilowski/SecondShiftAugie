"""
Short-Term Memory (STM) store implementation.

This module implements the STMStore class that manages thread-scoped conversation
context with token budget management and automatic summarization triggers.

Requirements addressed:
- 1.1: Store messages in STM with thread context
- 1.2: Create rolling summaries when token budget exceeded
- 1.3: Include thread summary and recent messages in prompt context
"""

import logging
import time
from typing import List, Optional, Tuple
from datetime import datetime, timezone

import asyncpg
from asyncpg import Connection

from .models import ThreadCtx, Msg
from .config import MemoryConfig


logger = logging.getLogger(__name__)


class STMError(Exception):
    """Exception raised when STM operations fail."""
    pass


class STMStore:
    """
    Manages thread-scoped conversation context with token budget management.
    
    The STMStore handles short-term memory operations including message storage,
    retrieval, token budget tracking, and automatic trimming when limits are exceeded.
    """
    
    def __init__(self, db_pool: asyncpg.Pool, config: MemoryConfig, summarizer=None):
        """
        Initialize the STM store.
        
        Args:
            db_pool: AsyncPG connection pool
            config: Memory configuration
            summarizer: Optional Summarizer instance for generating summaries
        """
        self.db_pool = db_pool
        self.config = config
        self.summarizer = summarizer
        
        # Token budget configuration
        self.max_tokens = config.stm_max_tokens
        self.keep_last = config.stm_keep_last
        
        logger.info(f"Initialized STMStore with max_tokens={self.max_tokens}, keep_last={self.keep_last}")
    
    async def append_message(self, ctx: ThreadCtx, msg: Msg) -> None:
        """
        Append a message to the thread's STM.
        
        Stores the message in the database with token estimation and thread context.
        
        Args:
            ctx: Thread context for scoping
            msg: Message to append
            
        Raises:
            STMError: If message storage fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        if not msg:
            raise STMError("Message cannot be None")
        
        start_time = time.time()
        
        try:
            # Ensure token count is estimated
            token_count = msg.estimate_tokens()
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO messages (guild_id, channel_id, user_id, role, content, token_estimate)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, ctx.guild_id, ctx.channel_id, ctx.user_id, msg.role, msg.content, token_count)
            
            elapsed = time.time() - start_time
            logger.debug(f"Appended message ({token_count} tokens) to {ctx} in {elapsed:.3f}s")
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to append message to {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to append message: {e}") from e
    
    async def get_recent_window(self, ctx: ThreadCtx, n: int) -> List[Msg]:
        """
        Retrieve the last N messages from the thread.
        
        Args:
            ctx: Thread context for scoping
            n: Number of recent messages to retrieve
            
        Returns:
            List[Msg]: List of recent messages, ordered chronologically (oldest first)
            
        Raises:
            STMError: If message retrieval fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        if n <= 0:
            raise STMError("Number of messages must be positive")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT role, content, token_estimate
                    FROM messages
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                    ORDER BY created_at DESC
                    LIMIT $4
                """, ctx.guild_id, ctx.channel_id, ctx.user_id, n)
            
            # Convert rows to Msg objects and reverse to get chronological order
            messages = []
            for row in reversed(rows):  # Reverse to get oldest-first order
                msg = Msg(
                    role=row['role'],
                    content=row['content'],
                    tokens=row['token_estimate']
                )
                messages.append(msg)
            
            elapsed = time.time() - start_time
            logger.debug(f"Retrieved {len(messages)} recent messages from {ctx} in {elapsed:.3f}s")
            
            return messages
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to get recent messages from {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to retrieve recent messages: {e}") from e
    
    async def get_thread_summary(self, ctx: ThreadCtx) -> Optional[str]:
        """
        Get the current thread summary if it exists.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            Optional[str]: Thread summary text, or None if no summary exists
            
        Raises:
            STMError: If summary retrieval fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT summary
                    FROM thread_summaries
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                """, ctx.guild_id, ctx.channel_id, ctx.user_id)
            
            summary = row['summary'] if row else None
            
            elapsed = time.time() - start_time
            logger.debug(f"Retrieved thread summary from {ctx} in {elapsed:.3f}s: {'found' if summary else 'not found'}")
            
            return summary
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to get thread summary from {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to retrieve thread summary: {e}") from e
    
    async def update_summary(self, ctx: ThreadCtx, summary: str) -> None:
        """
        Update or create the thread summary.
        
        Args:
            ctx: Thread context for scoping
            summary: New summary text
            
        Raises:
            STMError: If summary update fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        if not summary or not summary.strip():
            raise STMError("Summary cannot be empty")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO thread_summaries (guild_id, channel_id, user_id, summary)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, channel_id, user_id)
                    DO UPDATE SET summary = EXCLUDED.summary, updated_at = now()
                """, ctx.guild_id, ctx.channel_id, ctx.user_id, summary.strip())
            
            elapsed = time.time() - start_time
            logger.debug(f"Updated thread summary for {ctx} in {elapsed:.3f}s")
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to update thread summary for {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to update thread summary: {e}") from e
    
    async def calculate_token_usage(self, ctx: ThreadCtx) -> int:
        """
        Calculate the total token usage for the thread.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            int: Total token count for all messages in the thread
            
        Raises:
            STMError: If token calculation fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT COALESCE(SUM(token_estimate), 0) as total_tokens
                    FROM messages
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                """, ctx.guild_id, ctx.channel_id, ctx.user_id)
            
            total_tokens = row['total_tokens'] if row else 0
            
            elapsed = time.time() - start_time
            logger.debug(f"Calculated token usage for {ctx}: {total_tokens} tokens in {elapsed:.3f}s")
            
            return total_tokens
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to calculate token usage for {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to calculate token usage: {e}") from e
    
    async def trim_messages(self, ctx: ThreadCtx, keep_last: Optional[int] = None) -> int:
        """
        Trim old messages from the thread, keeping only the most recent ones.
        
        Args:
            ctx: Thread context for scoping
            keep_last: Number of recent messages to keep (defaults to config value)
            
        Returns:
            int: Number of messages that were deleted
            
        Raises:
            STMError: If message trimming fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        keep_count = keep_last if keep_last is not None else self.keep_last
        if keep_count < 0:
            raise STMError("keep_last cannot be negative")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                # First, get the total count to see if trimming is needed
                total_count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM messages
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                """, ctx.guild_id, ctx.channel_id, ctx.user_id)
                
                if total_count <= keep_count:
                    logger.debug(f"No trimming needed for {ctx}: {total_count} messages <= {keep_count} keep_last")
                    return 0
                
                # Delete older messages, keeping only the most recent ones
                result = await conn.execute("""
                    DELETE FROM messages
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                    AND id NOT IN (
                        SELECT id
                        FROM messages
                        WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                        ORDER BY created_at DESC
                        LIMIT $4
                    )
                """, ctx.guild_id, ctx.channel_id, ctx.user_id, keep_count)
                
                # Extract number of deleted rows from result
                deleted_count = int(result.split()[-1]) if result and result.split() else 0
                
                elapsed = time.time() - start_time
                logger.info(f"Trimmed {deleted_count} messages from {ctx}, kept last {keep_count} in {elapsed:.3f}s")
                
                return deleted_count
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to trim messages for {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to trim messages: {e}") from e
    
    async def get_message_count(self, ctx: ThreadCtx) -> int:
        """
        Get the total number of messages in the thread.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            int: Total number of messages in the thread
            
        Raises:
            STMError: If count retrieval fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        try:
            async with self.db_pool.acquire() as conn:
                count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM messages
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                """, ctx.guild_id, ctx.channel_id, ctx.user_id)
            
            return count or 0
            
        except Exception as e:
            logger.error(f"Failed to get message count for {ctx}: {e}")
            raise STMError(f"Failed to get message count: {e}") from e
    
    async def get_thread_stats(self, ctx: ThreadCtx) -> dict:
        """
        Get comprehensive statistics for the thread.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            dict: Thread statistics including message count, token usage, etc.
            
        Raises:
            STMError: If stats retrieval fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                # Get comprehensive stats in a single query
                row = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as message_count,
                        COALESCE(SUM(token_estimate), 0) as total_tokens,
                        MIN(created_at) as oldest_message,
                        MAX(created_at) as newest_message,
                        AVG(token_estimate) as avg_tokens_per_message
                    FROM messages
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                """, ctx.guild_id, ctx.channel_id, ctx.user_id)
                
                # Check if summary exists
                summary_exists = await conn.fetchval("""
                    SELECT 1 FROM thread_summaries
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                """, ctx.guild_id, ctx.channel_id, ctx.user_id)
                
                stats = {
                    'message_count': row['message_count'] if row else 0,
                    'total_tokens': row['total_tokens'] if row else 0,
                    'avg_tokens_per_message': float(row['avg_tokens_per_message']) if row and row['avg_tokens_per_message'] else 0.0,
                    'oldest_message': row['oldest_message'].isoformat() if row and row['oldest_message'] else None,
                    'newest_message': row['newest_message'].isoformat() if row and row['newest_message'] else None,
                    'has_summary': bool(summary_exists),
                    'token_budget_used': (row['total_tokens'] / self.max_tokens * 100) if row and row['total_tokens'] else 0.0,
                    'needs_trimming': (row['total_tokens'] > self.max_tokens) if row else False
                }
                
                elapsed = time.time() - start_time
                logger.debug(f"Retrieved thread stats for {ctx} in {elapsed:.3f}s")
                
                return stats
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to get thread stats for {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to get thread stats: {e}") from e
    
    async def maybe_summarize(self, ctx: ThreadCtx) -> Optional[str]:
        """
        Check if summarization is needed and perform it if token budget exceeded.
        
        This method implements the core logic for rolling summaries:
        1. Check if current token usage exceeds the budget
        2. If yes, generate a summary of recent messages
        3. Update the thread summary
        4. Trim old messages, keeping only the last N messages
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            Optional[str]: Updated summary if summarization occurred, None otherwise
            
        Raises:
            STMError: If summarization process fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        start_time = time.time()
        
        try:
            # Check current token usage
            current_tokens = await self.calculate_token_usage(ctx)
            
            if current_tokens <= self.max_tokens:
                logger.debug(f"No summarization needed for {ctx}: {current_tokens} <= {self.max_tokens} tokens")
                return None
            
            logger.info(f"Token budget exceeded for {ctx}: {current_tokens} > {self.max_tokens}, triggering summarization")
            
            # Get all messages for summarization
            all_messages = await self.get_recent_window(ctx, n=1000)  # Get all messages
            
            if not all_messages:
                logger.warning(f"No messages found for summarization in {ctx}")
                return None
            
            # Get existing summary if it exists
            existing_summary = await self.get_thread_summary(ctx)
            
            # Generate new summary
            if self.summarizer:
                try:
                    new_summary = await self.summarizer.generate_summary(
                        ctx, all_messages, existing_summary
                    )
                except Exception as e:
                    logger.error(f"Summarizer failed for {ctx}: {e}")
                    # Create fallback summary
                    new_summary = self._create_emergency_summary(all_messages, existing_summary)
            else:
                logger.warning(f"No summarizer available for {ctx}, creating basic summary")
                new_summary = self._create_emergency_summary(all_messages, existing_summary)
            
            # Update the thread summary
            await self.update_summary(ctx, new_summary)
            
            # Trim messages, keeping only the last N messages
            deleted_count = await self.trim_messages(ctx, self.keep_last)
            
            elapsed = time.time() - start_time
            logger.info(f"Summarization completed for {ctx} in {elapsed:.3f}s: "
                       f"trimmed {deleted_count} messages, kept last {self.keep_last}")
            
            return new_summary
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to maybe_summarize for {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to perform summarization: {e}") from e
    
    def _create_emergency_summary(self, messages: List[Msg], existing_summary: Optional[str] = None) -> str:
        """
        Create an emergency summary when the Summarizer is unavailable.
        
        Args:
            messages: List of messages to summarize
            existing_summary: Optional existing summary to update
            
        Returns:
            str: Emergency summary text
        """
        if not messages:
            return existing_summary or "Empty conversation"
        
        # Count messages by role
        user_count = sum(1 for msg in messages if msg.role == 'user')
        assistant_count = sum(1 for msg in messages if msg.role == 'assistant')
        total_tokens = sum(msg.estimate_tokens() for msg in messages)
        
        # Get recent context
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        
        summary_parts = []
        
        if existing_summary:
            summary_parts.append(f"Previous: {existing_summary}")
            summary_parts.append("")
        
        summary_parts.extend([
            f"• Conversation: {user_count} user, {assistant_count} assistant messages ({total_tokens} tokens)",
            "• Recent exchange:"
        ])
        
        # Add recent message summaries
        for msg in recent_messages[-3:]:  # Last 3 messages
            content_preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
            summary_parts.append(f"  - {msg.role}: {content_preview}")
        
        summary_parts.append("• Summary created in emergency mode")
        
        return "\n".join(summary_parts)

    async def clear_thread(self, ctx: ThreadCtx) -> Tuple[int, bool]:
        """
        Clear all messages and summary for a thread.
        
        Args:
            ctx: Thread context for scoping
            
        Returns:
            Tuple[int, bool]: (number of messages deleted, summary was deleted)
            
        Raises:
            STMError: If thread clearing fails
        """
        if not ctx:
            raise STMError("Thread context cannot be None")
        
        start_time = time.time()
        
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    # Delete messages
                    messages_result = await conn.execute("""
                        DELETE FROM messages
                        WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                    """, ctx.guild_id, ctx.channel_id, ctx.user_id)
                    
                    # Delete summary
                    summary_result = await conn.execute("""
                        DELETE FROM thread_summaries
                        WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                    """, ctx.guild_id, ctx.channel_id, ctx.user_id)
                    
                    messages_deleted = int(messages_result.split()[-1]) if messages_result and messages_result.split() else 0
                    summary_deleted = int(summary_result.split()[-1]) if summary_result and summary_result.split() else 0
                    
                    elapsed = time.time() - start_time
                    logger.info(f"Cleared thread {ctx}: {messages_deleted} messages, {summary_deleted} summary in {elapsed:.3f}s")
                    
                    return messages_deleted, bool(summary_deleted)
                    
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed to clear thread {ctx} after {elapsed:.3f}s: {e}")
            raise STMError(f"Failed to clear thread: {e}") from e
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"STMStore(max_tokens={self.max_tokens}, keep_last={self.keep_last})"