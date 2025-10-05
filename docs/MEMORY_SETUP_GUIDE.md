# Memory System Setup Guide

This guide provides step-by-step instructions for setting up the SecondShiftAugie memory system.

## Quick Start

### 1. Prerequisites

- **Python 3.8+** with pip
- **PostgreSQL 12+** with pgvector extension
- **Ollama** for embeddings (optional, enables LTM)

### 2. Install Dependencies

```bash
# Install Python dependencies
pip install asyncpg aiohttp

# Install PostgreSQL and pgvector (Ubuntu/Debian)
sudo apt install postgresql postgresql-contrib postgresql-14-pgvector

# Or use Docker (recommended for development)
docker run -d --name ssa-postgres \
  -e POSTGRES_DB=ssa \
  -e POSTGRES_USER=ssa \
  -e POSTGRES_PASSWORD=ssa \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 3. Install Ollama (Optional, for LTM features)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve

# Pull embedding model
ollama pull nomic-embed-text
```

### 4. Run Setup Script

```bash
# Automated setup (recommended)
python scripts/setup_memory_system.py

# Or with custom database
python scripts/setup_memory_system.py --dsn postgres://user:pass@host:5432/db
```

### 5. Configure Environment

Copy the appropriate configuration template:

```bash
# Development
cp config/development.env .env

# Production  
cp config/production.env .env

# Edit .env with your actual values
nano .env
```

### 6. Verify Setup

```bash
# Validate configuration
python scripts/memory_config.py validate

# Check feature availability
python scripts/memory_config.py features
```

## Detailed Setup

### Database Setup

#### Option 1: Automated Setup
```bash
# Full database setup with validation
python scripts/setup_database.py

# Force recreation of existing tables
python scripts/setup_database.py --force

# Verify existing setup
python scripts/setup_database.py --verify-only
```

#### Option 2: Manual Setup
```bash
# Create database and user
sudo -u postgres createdb ssa
sudo -u postgres createuser ssa -P  # Enter password when prompted

# Run SQL setup script
psql -U ssa -d ssa -h localhost -f scripts/setup_database.sql
```

### Configuration Management

#### View Current Configuration
```bash
# Show all configuration
python scripts/memory_config.py info

# Show feature flags only
python scripts/memory_config.py features

# Check specific feature
python scripts/memory_config.py check-feature ltm
```

#### Validate Configuration
```bash
# Full validation (connectivity + permissions)
python scripts/memory_config.py validate

# Skip connectivity tests
python scripts/memory_config.py validate --no-connectivity

# JSON output for automation
python scripts/memory_config.py validate --json
```

#### Generate Configuration Templates
```bash
# Print template to stdout
python scripts/memory_config.py template

# Save to file
python scripts/memory_config.py template --output my_config.env
```

## Configuration Options

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `MEMORY_ENABLED` | Master switch for memory features | `true` |
| `PG_DSN` | PostgreSQL connection string | `postgres://ssa:ssa@localhost:5432/ssa` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_POOL_MIN` | `2` | Minimum database connections |
| `PG_POOL_MAX` | `10` | Maximum database connections |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `EMBED_OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `STM_MAX_TOKENS` | `2400` | Token budget for STM |
| `RETRIEVE_TOP_K` | `6` | Number of memories to retrieve |
| `MEMORY_MIN_IMPORTANCE` | `2` | Minimum importance to store |
| `MEMORY_EXPORT_DIR` | `./exports` | Directory for memory exports |

See [MEMORY_CONFIGURATION.md](MEMORY_CONFIGURATION.md) for complete reference.

## Operation Modes

The memory system operates in three modes based on component availability:

### Full Memory Mode
- **Requirements**: Database + Ollama + pgvector
- **Features**: STM + LTM + Vector search + Embeddings
- **Best for**: Production deployments with full functionality

### STM-Only Mode  
- **Requirements**: Database + pgvector
- **Features**: STM + Summarization (no LTM/embeddings)
- **Best for**: Limited resource environments

### No Memory Mode
- **Requirements**: None
- **Features**: Basic bot functionality only
- **Best for**: Fallback when database unavailable

## Troubleshooting

### Common Issues

#### 1. Database Connection Failed
```
Error: could not connect to server: Connection refused
```

**Solutions:**
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify connection string in `PG_DSN`
- Check firewall settings

#### 2. pgvector Extension Missing
```
Error: pgvector extension not available
```

**Solutions:**
```bash
# Install pgvector
sudo apt install postgresql-14-pgvector

# Or compile from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make && sudo make install

# Enable in database
psql -U ssa -d ssa -c "CREATE EXTENSION vector;"
```

#### 3. Ollama Connection Failed
```
Warning: Ollama unavailable, falling back to STM-only mode
```

**Solutions:**
```bash
# Start Ollama
ollama serve

# Check status
curl http://localhost:11434/api/tags

# Pull embedding model
ollama pull nomic-embed-text
```

#### 4. Permission Denied
```
Error: Export directory not writable
```

**Solutions:**
```bash
# Create directory with proper permissions
mkdir -p ./exports
chmod 755 ./exports

# Or use different directory
export MEMORY_EXPORT_DIR=/tmp/ssa_exports
```

### Diagnostic Commands

```bash
# Check system status
python scripts/memory_config.py validate

# Test database connectivity
python scripts/setup_database.py --verify-only

# Check Ollama models
ollama list

# View PostgreSQL logs
sudo journalctl -u postgresql -f
```

## Performance Tuning

### Database Optimization

```sql
-- Tune PostgreSQL for memory workload
-- Add to postgresql.conf

shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
```

### Memory System Tuning

```bash
# High-traffic servers
PG_POOL_MAX=20
RETRIEVE_TOP_K=8

# Memory-constrained environments  
STM_MAX_TOKENS=1200
PG_POOL_MAX=5

# Accuracy-focused deployments
BOOST_SIMILARITY=0.8
MEMORY_MIN_IMPORTANCE=3
```

## Security Considerations

### Database Security
- Use SSL connections in production: `?sslmode=require`
- Create dedicated database user with minimal privileges
- Regular security updates for PostgreSQL

### Network Security
- Restrict Ollama API access to trusted networks
- Use firewall rules to limit database access
- Consider VPN for remote database connections

### Data Privacy
- Configure appropriate retention policies
- Implement data deletion procedures
- Monitor export directory permissions

## Monitoring and Maintenance

### Health Checks

```bash
# Automated health check
python scripts/memory_config.py validate --json | jq '.valid'

# Database health
psql -U ssa -d ssa -c "SELECT COUNT(*) FROM memories;"

# Ollama health
curl -s http://localhost:11434/api/tags | jq '.models | length'
```

### Regular Maintenance

```bash
# Weekly database maintenance
psql -U ssa -d ssa -c "VACUUM ANALYZE;"

# Monthly cleanup (adjust retention as needed)
psql -U ssa -d ssa -c "DELETE FROM messages WHERE created_at < now() - INTERVAL '30 days';"

# Monitor disk usage
du -sh /var/lib/postgresql/
```

### Backup Strategy

```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
pg_dump -U ssa ssa | gzip > /backups/ssa_${DATE}.sql.gz

# Keep last 7 days
find /backups -name "ssa_*.sql.gz" -mtime +7 -delete
```

## Migration and Upgrades

### Upgrading Memory System

1. **Backup database** before any changes
2. **Test in development** environment first
3. **Update configuration** as needed
4. **Run validation** after upgrade

```bash
# Backup before upgrade
pg_dump -U ssa ssa > backup_before_upgrade.sql

# Update configuration
python scripts/memory_config.py validate

# Test new features
python scripts/memory_config.py features
```

### Schema Migrations

For future schema changes, use the migration pattern:

```sql
-- Example migration script
BEGIN;

-- Add new column
ALTER TABLE memories ADD COLUMN new_field TEXT;

-- Update existing data if needed
UPDATE memories SET new_field = 'default_value';

-- Create new indexes
CREATE INDEX idx_memories_new_field ON memories(new_field);

COMMIT;
```

## Getting Help

### Documentation
- [Memory Configuration Reference](MEMORY_CONFIGURATION.md)
- [Database Setup Guide](DATABASE_SETUP.md)
- [API Documentation](../src/memory/README.md)

### Diagnostic Information

When reporting issues, include:

```bash
# System information
python scripts/memory_config.py info

# Validation results
python scripts/memory_config.py validate --json

# Database status
python scripts/setup_database.py --verify-only

# Ollama status
ollama list
```

### Common Support Scenarios

1. **Setup Issues**: Use automated setup script first
2. **Performance Problems**: Check database indexes and connection pool
3. **Feature Not Working**: Validate configuration and check logs
4. **Data Loss**: Restore from backup and check retention policies