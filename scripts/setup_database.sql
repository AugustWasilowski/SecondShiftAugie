-- SecondShiftAugie Memory System Database Setup
-- This script creates the necessary database schema for the memory system
-- Requires PostgreSQL with pgvector extension

-- Enable pgvector extension for vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- Create database user (run as superuser)
-- Note: Adjust password and privileges as needed for your environment
-- CREATE USER ssa WITH PASSWORD 'ssa';
-- GRANT CREATE ON DATABASE ssa TO ssa;

-- Recent raw messages (STM)
-- Stores conversation messages with thread context and token estimates
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_estimate INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for efficient thread-based queries (most recent first)
CREATE INDEX IF NOT EXISTS idx_messages_thread 
ON messages(guild_id, channel_id, user_id, created_at DESC);

-- Index for cleanup operations (oldest first)
CREATE INDEX IF NOT EXISTS idx_messages_cleanup 
ON messages(created_at);

-- Rolling summaries per thread (STM)
-- Stores conversation summaries to maintain context within token budget
CREATE TABLE IF NOT EXISTS thread_summaries (
    id BIGSERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (guild_id, channel_id, user_id)
);

-- Index for efficient summary lookups
CREATE INDEX IF NOT EXISTS idx_thread_summaries_lookup 
ON thread_summaries(guild_id, channel_id, user_id);

-- Long-term memories (LTM)
-- Stores persistent facts, preferences, and knowledge with vector embeddings
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('episodic', 'semantic', 'entity', 'artifact')),
    text TEXT NOT NULL,
    importance SMALLINT DEFAULT 1 CHECK (importance >= 1 AND importance <= 5),
    created_at TIMESTAMPTZ DEFAULT now(),
    embedding VECTOR(1536)  -- Adjust dimension based on embedding model
);

-- HNSW index for efficient approximate nearest neighbor search
-- Parameters optimized for typical memory datasets
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
ON memories USING hnsw (embedding vector_l2_ops)
WITH (m=16, ef_construction=64);

-- Index for scoped queries (user-specific memory access)
CREATE INDEX IF NOT EXISTS idx_memories_scope 
ON memories (guild_id, user_id, created_at DESC);

-- Index for importance-based filtering
CREATE INDEX IF NOT EXISTS idx_memories_importance 
ON memories (importance, created_at DESC);

-- Guild settings (optional, for multi-guild deployments)
-- Stores per-guild memory system configuration
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    memory_enabled BOOLEAN DEFAULT true,
    memory_retention_days INT DEFAULT 365,
    min_importance_threshold SMALLINT DEFAULT 2,
    max_memories_per_user INT DEFAULT 10000,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at for thread_summaries
CREATE TRIGGER update_thread_summaries_updated_at 
    BEFORE UPDATE ON thread_summaries 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger to automatically update updated_at for guild_settings
CREATE TRIGGER update_guild_settings_updated_at 
    BEFORE UPDATE ON guild_settings 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create indexes for performance optimization
-- These indexes support the hybrid search scoring algorithm

-- Composite index for memory retrieval with filtering
CREATE INDEX IF NOT EXISTS idx_memories_retrieval 
ON memories (guild_id, user_id, importance, created_at DESC);

-- Index for memory cleanup operations
CREATE INDEX IF NOT EXISTS idx_memories_cleanup 
ON memories (created_at, guild_id);

-- Partial index for high-importance memories
CREATE INDEX IF NOT EXISTS idx_memories_high_importance 
ON memories (guild_id, user_id, created_at DESC) 
WHERE importance >= 4;

-- Grant permissions to ssa user (adjust as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ssa;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ssa;

-- Insert default guild settings (optional)
-- INSERT INTO guild_settings (guild_id, memory_enabled) 
-- VALUES ('your_guild_id_here', true) 
-- ON CONFLICT (guild_id) DO NOTHING;

-- Verify pgvector installation
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'vector'
    ) THEN
        RAISE EXCEPTION 'pgvector extension is not installed. Please install it first.';
    END IF;
    
    RAISE NOTICE 'Database setup completed successfully!';
    RAISE NOTICE 'pgvector extension: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
    RAISE NOTICE 'Tables created: messages, thread_summaries, memories, guild_settings';
    RAISE NOTICE 'Indexes created for optimal performance';
END $$;