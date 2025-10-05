# Memory System Configuration Guide

This document provides comprehensive configuration information for the SecondShiftAugie memory system.

## Overview

The memory system uses environment variables for configuration and supports graceful degradation when components are unavailable. The system can operate in three modes:

1. **Full Memory Mode**: Both STM and LTM operational with Ollama embeddings
2. **STM-Only Mode**: Embeddings unavailable, conversation context maintained via summaries
3. **No Memory Mode**: Database unavailable, basic bot functionality without context

## Required Environment Variables

### Database Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PG_DSN` | **Yes** | - | PostgreSQL connection string with pgvector support |
| `PG_POOL_MIN` | No | `2` | Minimum database connection pool size |
| `PG_POOL_MAX` | No | `10` | Maximum database connection pool size |

**Example PG_DSN formats:**
```bash
# Local development
PG_DSN=postgres://ssa:ssa@localhost:5432/ssa

# Production with SSL
PG_DSN=postgres://user:pass@host:5432/dbname?sslmode=require

# With connection parameters
PG_DSN=postgres://user:pass@host:5432/dbname?application_name=ssa&connect_timeout=10
```

### Embedding Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMBED_MODEL` | No | `nomic-embed-text` | Ollama embedding model name |
| `EMBED_OLLAMA_URL` | No | `http://localhost:11434` | Ollama API endpoint URL |

**Supported embedding models:**
- `nomic-embed-text` (recommended, 768 dimensions)
- `mxbai-embed-large` (1024 dimensions)
- `all-minilm` (384 dimensions, faster but less accurate)

## Optional Configuration Variables

### Short-Term Memory (STM) Behavior

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `STM_MAX_TOKENS` | `2400` | 100-10000 | Token budget before summarization triggers |
| `STM_KEEP_LAST` | `2` | 1-10 | Messages to keep after summarization |

### Retrieval Configuration

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `RETRIEVE_TOP_K` | `6` | 1-50 | Number of memories to retrieve for context |
| `RECENCY_WINDOW_DAYS` | `7` | 1-365 | Days for recency scoring window |
| `BOOST_SIMILARITY` | `0.7` | 0.0-1.0 | Weight for semantic similarity in hybrid search |
| `BOOST_RECENCY` | `0.2` | 0.0-1.0 | Weight for recency in hybrid search |
| `BOOST_IMPORTANCE` | `0.1` | 0.0-1.0 | Weight for importance in hybrid search |

**Note:** Boost weights should sum to approximately 1.0 for optimal results.

### Policy Configuration

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `MEMORY_MIN_IMPORTANCE` | `2` | 1-5 | Minimum importance score to store memories |
| `MEMORY_EXPORT_DIR` | `./exports` | - | Directory for memory export files |
| `MEMORY_ENABLED` | `true` | true/false | Master switch for memory features |

## Feature Flags

### Memory System Enable/Disable

The memory system can be completely disabled using:

```bash
MEMORY_ENABLED=false
```

When disabled, the bot operates without any memory functionality.

### Graceful Degradation

The system automatically degrades functionality based on component availability:

1. **Ollama unavailable**: Falls back to STM-only mode
2. **Database unavailable**: Falls back to no-memory mode
3. **pgvector extension missing**: Falls back to STM-only mode

## Configuration Validation

The system performs comprehensive validation on startup:

### Database Validation
- Checks PG_DSN format and connectivity
- Validates pool size parameters
- Verifies pgvector extension availability

### Embedding Validation
- Validates Ollama URL format and connectivity
- Checks embedding model availability
- Tests embedding generation

### Parameter Validation
- Ensures numeric values are within acceptable ranges
- Validates boost weights sum to ~1.0
- Checks directory permissions for export path

## Environment Setup Examples

### Development Environment

```bash
# .env.development
# Database (local PostgreSQL with pgvector)
PG_DSN=postgres://ssa:ssa@localhost:5432/ssa_dev
PG_POOL_MIN=1
PG_POOL_MAX=5

# Embedding (local Ollama)
EMBED_MODEL=nomic-embed-text
EMBED_OLLAMA_URL=http://localhost:11434

# Memory settings (development)
STM_MAX_TOKENS=1200
RETRIEVE_TOP_K=3
MEMORY_MIN_IMPORTANCE=1
MEMORY_EXPORT_DIR=./dev_exports
MEMORY_ENABLED=true
```

### Production Environment

```bash
# .env.production
# Database (production PostgreSQL)
PG_DSN=postgres://ssa_user:secure_password@db.example.com:5432/ssa_prod?sslmode=require
PG_POOL_MIN=5
PG_POOL_MAX=20

# Embedding (production Ollama)
EMBED_MODEL=mxbai-embed-large
EMBED_OLLAMA_URL=https://ollama.internal.example.com

# Memory settings (production)
STM_MAX_TOKENS=2400
RETRIEVE_TOP_K=6
MEMORY_MIN_IMPORTANCE=2
MEMORY_EXPORT_DIR=/var/lib/ssa/exports
MEMORY_ENABLED=true

# Additional production settings
RECENCY_WINDOW_DAYS=14
BOOST_SIMILARITY=0.8
BOOST_RECENCY=0.15
BOOST_IMPORTANCE=0.05
```

### Testing Environment

```bash
# .env.test
# Database (test database)
PG_DSN=postgres://test:test@localhost:5432/ssa_test
PG_POOL_MIN=1
PG_POOL_MAX=3

# Embedding (mock or local)
EMBED_MODEL=nomic-embed-text
EMBED_OLLAMA_URL=http://localhost:11434

# Memory settings (testing)
STM_MAX_TOKENS=500
RETRIEVE_TOP_K=2
MEMORY_MIN_IMPORTANCE=1
MEMORY_EXPORT_DIR=./test_exports
MEMORY_ENABLED=true
```

## Troubleshooting

### Common Configuration Issues

1. **Database Connection Failed**
   ```
   Error: Memory configuration validation failed: pg_dsn must start with 'postgres://' or 'postgresql://'
   ```
   - Check PG_DSN format
   - Verify database is running and accessible
   - Ensure credentials are correct

2. **Ollama Connection Failed**
   ```
   Warning: Ollama unavailable, falling back to STM-only mode
   ```
   - Check EMBED_OLLAMA_URL is correct
   - Verify Ollama is running: `curl http://localhost:11434/api/tags`
   - Ensure embedding model is installed: `ollama pull nomic-embed-text`

3. **pgvector Extension Missing**
   ```
   Error: pgvector extension not available
   ```
   - Install pgvector extension in PostgreSQL
   - Ensure user has CREATE EXTENSION privileges
   - See database setup guide below

4. **Invalid Boost Weights**
   ```
   Error: Boost weights should sum to ~1.0, got 1.200
   ```
   - Adjust BOOST_SIMILARITY, BOOST_RECENCY, BOOST_IMPORTANCE to sum to 1.0

### Performance Tuning

For optimal performance, adjust these settings based on your deployment:

- **High-traffic servers**: Increase `PG_POOL_MAX` to 20-50
- **Memory-constrained environments**: Decrease `STM_MAX_TOKENS` to 1200-1800
- **Accuracy-focused deployments**: Increase `BOOST_SIMILARITY` to 0.8-0.9
- **Recent-conversation focused**: Increase `BOOST_RECENCY` to 0.3-0.4

### Monitoring Configuration

Add these optional variables for enhanced monitoring:

```bash
# Logging configuration
LOG_LEVEL=INFO
MEMORY_LOG_PERFORMANCE=true
MEMORY_LOG_QUERIES=false  # Set to true for debugging

# Health check configuration
HEALTH_CHECK_INTERVAL=300  # seconds
MEMORY_HEALTH_ENDPOINT=/health/memory
```

## Security Considerations

1. **Database Credentials**: Store PG_DSN securely, avoid logging
2. **Export Directory**: Ensure proper file permissions on MEMORY_EXPORT_DIR
3. **Network Access**: Restrict Ollama API access to trusted networks
4. **Data Retention**: Configure appropriate retention policies for your use case

## Migration and Upgrades

When upgrading the memory system:

1. **Backup database** before schema changes
2. **Test configuration** in development environment first
3. **Monitor logs** during initial deployment
4. **Verify graceful degradation** works as expected

For configuration changes in production:
1. Update environment variables
2. Restart the bot service
3. Check logs for validation errors
4. Monitor memory system health endpoints