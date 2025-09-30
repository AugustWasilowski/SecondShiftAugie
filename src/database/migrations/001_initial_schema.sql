-- Initial schema migration for SecondShiftAugie Memory System
-- This script sets up the complete database schema with pgvector extension

-- Enable pgvector extension for vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- Recent raw messages table (STM - Short Term Memory)
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

-- Index for efficient thread-based message retrieval
CREATE INDEX IF NOT EXISTS idx_messages_thread 
ON messages(guild_id, channel_id, user_id, created_at DESC);

-- Index for general message queries
CREATE INDEX IF NOT EXISTS idx_messages_created_at 
ON messages(created_at DESC);

-- Rolling summaries per thread table (STM)
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

-- Long-term memories table (LTM) with vector embeddings
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('episodic', 'semantic', 'entity', 'artifact')),
    text TEXT NOT NULL,
    importance SMALLINT DEFAULT 1 CHECK (importance >= 1 AND importance <= 5),
    created_at TIMESTAMPTZ DEFAULT now(),
    embedding VECTOR(1536)  -- Dimension for nomic-embed-text/mxbai-embed-large
);

-- HNSW index for efficient approximate nearest neighbor search
-- Parameters: m=16 (max connections per node), ef_construction=64 (search width during construction)
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
ON memories USING hnsw (embedding vector_l2_ops)
WITH (m=16, ef_construction=64);

-- Index for scoped memory queries (guild + user filtering)
CREATE INDEX IF NOT EXISTS idx_memories_scope 
ON memories (guild_id, user_id, created_at DESC);

-- Index for importance-based filtering
CREATE INDEX IF NOT EXISTS idx_memories_importance 
ON memories (importance DESC, created_at DESC);

-- Guild settings table for per-guild configuration
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    memory_enabled BOOLEAN DEFAULT true,
    stm_max_tokens INT DEFAULT 2400,
    stm_keep_last INT DEFAULT 2,
    retrieve_top_k INT DEFAULT 6,
    memory_min_importance SMALLINT DEFAULT 2 CHECK (memory_min_importance >= 1 AND memory_min_importance <= 5),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Trigger to update updated_at timestamp on guild_settings
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_guild_settings_updated_at 
    BEFORE UPDATE ON guild_settings 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create a view for memory statistics (useful for monitoring)
CREATE OR REPLACE VIEW memory_stats AS
SELECT 
    guild_id,
    user_id,
    COUNT(*) as total_memories,
    AVG(importance) as avg_importance,
    MIN(created_at) as oldest_memory,
    MAX(created_at) as newest_memory
FROM memories 
GROUP BY guild_id, user_id;

-- Grant necessary permissions (adjust as needed for your setup)
-- These are basic permissions - adjust based on your security requirements
GRANT USAGE ON SCHEMA public TO ssa;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ssa;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ssa;