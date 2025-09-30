# Database Module

This module handles database initialization and schema management for the SecondShiftAugie Memory System.

## Files

- `db_init.py` - Main database initialization and management module
- `migrations/001_initial_schema.sql` - Initial database schema with pgvector extension
- `requirements.txt` - Python dependencies for database operations

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure PostgreSQL is running with pgvector extension available

3. Set environment variables:
   ```bash
   export PG_DSN="postgres://user:password@localhost:5432/database"
   # OR individual components:
   export PG_HOST="localhost"
   export PG_PORT="5432"
   export PG_DATABASE="ssa"
   export PG_USER="ssa"
   export PG_PASSWORD="ssa"
   ```

4. Run initialization:
   ```python
   from src.database.db_init import initialize_database, get_database_dsn
   
   db_manager = await initialize_database(get_database_dsn())
   ```

## Schema

The database includes:

- **messages** - Recent raw messages (STM)
- **thread_summaries** - Rolling summaries per thread (STM)  
- **memories** - Long-term memories with vector embeddings (LTM)
- **guild_settings** - Per-guild configuration

All tables include proper indexes for efficient querying, including an HNSW index on the memories table for vector similarity search.