# Database Setup Guide

This guide covers setting up PostgreSQL with pgvector for the SecondShiftAugie memory system.

## Prerequisites

1. **PostgreSQL 12+** with superuser access
2. **pgvector extension** installed
3. **Python 3.8+** with asyncpg library

## Quick Setup

### 1. Install PostgreSQL and pgvector

#### Ubuntu/Debian
```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Install pgvector
sudo apt install postgresql-14-pgvector
# or compile from source: https://github.com/pgvector/pgvector
```

#### macOS (Homebrew)
```bash
# Install PostgreSQL
brew install postgresql

# Install pgvector
brew install pgvector
```

#### Docker (Recommended for Development)
```bash
# Run PostgreSQL with pgvector
docker run -d \
  --name ssa-postgres \
  -e POSTGRES_DB=ssa \
  -e POSTGRES_USER=ssa \
  -e POSTGRES_PASSWORD=ssa \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 2. Create Database and User

```sql
-- Connect as superuser (postgres)
sudo -u postgres psql

-- Create database
CREATE DATABASE ssa;

-- Create user
CREATE USER ssa WITH PASSWORD 'ssa';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ssa TO ssa;
GRANT CREATE ON DATABASE ssa TO ssa;

-- Connect to the ssa database
\c ssa

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO ssa;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ssa;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ssa;

-- Exit
\q
```

### 3. Run Database Setup Script

#### Option A: Automated Setup (Recommended)
```bash
# Install Python dependencies
pip install asyncpg

# Set environment variable
export PG_DSN="postgres://ssa:ssa@localhost:5432/ssa"

# Run setup script
python scripts/setup_database.py

# Or with custom DSN
python scripts/setup_database.py --dsn "postgres://ssa:ssa@localhost:5432/ssa"
```

#### Option B: Manual Setup
```bash
# Connect to database
psql -U ssa -d ssa -h localhost

# Run SQL script
\i scripts/setup_database.sql

# Verify setup
\dt  -- List tables
\di  -- List indexes
```

### 4. Verify Installation

```bash
# Test database connection and setup
python scripts/setup_database.py --verify-only

# Should show:
# ✓ messages
# ✓ thread_summaries  
# ✓ memories
# ✓ guild_settings
# ✓ pgvector (0.5.1)
# ✓ Vector operations
```

## Database Schema

### Tables Overview

| Table | Purpose | Key Features |
|-------|---------|--------------|
| `messages` | Short-term message storage | Thread-scoped, token estimates |
| `thread_summaries` | Rolling conversation summaries | Per-thread, updated automatically |
| `memories` | Long-term memory storage | Vector embeddings, importance scoring |
| `guild_settings` | Per-guild configuration | Memory policies, retention settings |

### Schema Details

#### messages (STM)
```sql
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT CHECK (role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    token_estimate INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### memories (LTM)
```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    kind TEXT CHECK (kind IN ('episodic','semantic','entity','artifact')),
    text TEXT NOT NULL,
    importance SMALLINT DEFAULT 1 CHECK (importance >= 1 AND importance <= 5),
    created_at TIMESTAMPTZ DEFAULT now(),
    embedding VECTOR(1536)  -- Adjust based on embedding model
);
```

### Indexes for Performance

The setup creates optimized indexes for memory operations:

- **HNSW Index**: `idx_memories_embedding` for fast vector similarity search
- **Thread Indexes**: Efficient message retrieval by thread context
- **Composite Indexes**: Support hybrid search scoring algorithm

## Configuration

### Connection String Format

```bash
# Basic format
PG_DSN=postgres://username:password@host:port/database

# With SSL (production)
PG_DSN=postgres://user:pass@host:5432/db?sslmode=require

# With connection parameters
PG_DSN=postgres://user:pass@host:5432/db?application_name=ssa&connect_timeout=10
```

### Connection Pool Settings

```bash
# Development
PG_POOL_MIN=1
PG_POOL_MAX=5

# Production
PG_POOL_MIN=5
PG_POOL_MAX=20
```

## Maintenance

### Regular Maintenance Tasks

#### 1. Vacuum and Analyze
```sql
-- Run weekly
VACUUM ANALYZE messages;
VACUUM ANALYZE memories;
VACUUM ANALYZE thread_summaries;
```

#### 2. Reindex HNSW (if needed)
```sql
-- Only if search performance degrades
REINDEX INDEX idx_memories_embedding;
```

#### 3. Cleanup Old Messages
```sql
-- Remove messages older than 30 days (adjust as needed)
DELETE FROM messages 
WHERE created_at < now() - INTERVAL '30 days';
```

### Monitoring Queries

#### Check Database Size
```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

#### Check Memory Usage
```sql
SELECT 
    COUNT(*) as total_memories,
    AVG(importance) as avg_importance,
    COUNT(DISTINCT user_id) as unique_users
FROM memories;
```

#### Check Index Usage
```sql
SELECT 
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

## Troubleshooting

### Common Issues

#### 1. pgvector Extension Not Found
```
ERROR: extension "vector" is not available
```

**Solution:**
- Install pgvector extension for your PostgreSQL version
- Ensure user has CREATE EXTENSION privileges
- Check `SELECT * FROM pg_available_extensions WHERE name = 'vector';`

#### 2. Permission Denied
```
ERROR: permission denied to create extension "vector"
```

**Solution:**
```sql
-- Run as superuser
GRANT CREATE ON DATABASE ssa TO ssa;
-- Or install extension as superuser:
CREATE EXTENSION vector;
```

#### 3. Connection Refused
```
ERROR: could not connect to server: Connection refused
```

**Solution:**
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify connection parameters in PG_DSN
- Check firewall settings

#### 4. Vector Dimension Mismatch
```
ERROR: vector dimension mismatch
```

**Solution:**
- Ensure embedding model dimensions match table schema
- Default is 1536 for `nomic-embed-text`
- Update table if using different model:
```sql
ALTER TABLE memories ALTER COLUMN embedding TYPE VECTOR(768);  -- for different dimension
```

### Performance Issues

#### Slow Vector Search
1. **Check HNSW parameters:**
```sql
-- View current index parameters
SELECT * FROM pg_indexes WHERE indexname = 'idx_memories_embedding';
```

2. **Tune HNSW parameters:**
```sql
-- Drop and recreate with different parameters
DROP INDEX idx_memories_embedding;
CREATE INDEX idx_memories_embedding ON memories 
USING hnsw (embedding vector_l2_ops)
WITH (m=32, ef_construction=128);  -- Higher values = better recall, slower build
```

#### High Memory Usage
1. **Monitor connection pool:**
```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'ssa';
```

2. **Adjust pool settings:**
```bash
PG_POOL_MAX=10  # Reduce if memory constrained
```

### Backup and Recovery

#### Backup Database
```bash
# Full backup
pg_dump -U ssa -h localhost ssa > ssa_backup.sql

# Schema only
pg_dump -U ssa -h localhost --schema-only ssa > ssa_schema.sql

# Data only
pg_dump -U ssa -h localhost --data-only ssa > ssa_data.sql
```

#### Restore Database
```bash
# Restore full backup
psql -U ssa -h localhost ssa < ssa_backup.sql

# Restore to new database
createdb -U ssa ssa_restored
psql -U ssa -h localhost ssa_restored < ssa_backup.sql
```

## Production Considerations

### Security
1. **Use SSL connections** in production
2. **Restrict network access** to database server
3. **Use strong passwords** and consider certificate authentication
4. **Regular security updates** for PostgreSQL and pgvector

### Performance
1. **Monitor query performance** with `pg_stat_statements`
2. **Tune PostgreSQL settings** for your workload
3. **Consider read replicas** for high-traffic deployments
4. **Regular VACUUM and ANALYZE** operations

### High Availability
1. **Set up streaming replication** for failover
2. **Regular backups** with point-in-time recovery
3. **Monitor disk space** and connection limits
4. **Connection pooling** with pgbouncer for high concurrency

## Migration Guide

### Upgrading pgvector
1. **Backup database** before upgrade
2. **Update pgvector** extension
3. **Run** `ALTER EXTENSION vector UPDATE;`
4. **Test vector operations** after upgrade

### Schema Changes
1. **Use migrations** for schema changes
2. **Test on staging** environment first
3. **Plan downtime** for major changes
4. **Keep rollback scripts** ready

### Data Migration
```sql
-- Example: Migrate to new embedding dimension
-- 1. Add new column
ALTER TABLE memories ADD COLUMN embedding_new VECTOR(768);

-- 2. Migrate data (application-level)
-- 3. Drop old column and rename
ALTER TABLE memories DROP COLUMN embedding;
ALTER TABLE memories RENAME COLUMN embedding_new TO embedding;

-- 4. Recreate index
CREATE INDEX idx_memories_embedding ON memories 
USING hnsw (embedding vector_l2_ops)
WITH (m=16, ef_construction=64);
```