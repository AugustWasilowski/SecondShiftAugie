"""
Database initialization module for SecondShiftAugie Memory System.
Handles database setup, migrations, and connection validation.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import asyncpg
from asyncpg import Connection, Pool

logger = logging.getLogger(__name__)


class DatabaseInitError(Exception):
    """Raised when database initialization fails."""
    pass


class DatabaseManager:
    """Manages database connections and initialization for the memory system."""
    
    def __init__(self, dsn: str, pool_min: int = 2, pool_max: int = 10):
        self.dsn = dsn
        self.pool_min = pool_min
        self.pool_max = pool_max
        self.pool: Optional[Pool] = None
        
    async def initialize(self) -> None:
        """
        Initialize the database with schema and connection pool.
        
        Raises:
            DatabaseInitError: If initialization fails
        """
        try:
            logger.info("Starting database initialization...")
            
            # First, test basic connectivity
            await self._test_connection()
            
            # Run migrations
            await self._run_migrations()
            
            # Create connection pool
            await self._create_pool()
            
            # Validate schema
            await self._validate_schema()
            
            logger.info("Database initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseInitError(f"Failed to initialize database: {e}") from e
    
    async def _test_connection(self) -> None:
        """Test basic database connectivity."""
        try:
            conn = await asyncpg.connect(self.dsn)
            await conn.execute("SELECT 1")
            await conn.close()
            logger.info("Database connectivity test passed")
        except Exception as e:
            raise DatabaseInitError(f"Cannot connect to database: {e}") from e 
   
    async def _run_migrations(self) -> None:
        """Run database migrations from the migrations directory."""
        migrations_dir = Path(__file__).parent / "migrations"
        
        if not migrations_dir.exists():
            raise DatabaseInitError(f"Migrations directory not found: {migrations_dir}")
        
        # Get all .sql files sorted by name
        migration_files = sorted(migrations_dir.glob("*.sql"))
        
        if not migration_files:
            logger.warning("No migration files found")
            return
        
        conn = None
        try:
            conn = await asyncpg.connect(self.dsn)
            
            # Create migrations tracking table if it doesn't exist
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now()
                )
            """)
            
            # Get already applied migrations
            applied_migrations = await conn.fetch(
                "SELECT filename FROM schema_migrations"
            )
            applied_set = {row['filename'] for row in applied_migrations}
            
            # Apply new migrations
            for migration_file in migration_files:
                filename = migration_file.name
                
                if filename in applied_set:
                    logger.debug(f"Migration {filename} already applied, skipping")
                    continue
                
                logger.info(f"Applying migration: {filename}")
                
                try:
                    # Read and execute migration
                    migration_sql = migration_file.read_text(encoding='utf-8')
                    await conn.execute(migration_sql)
                    
                    # Record successful migration
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename) VALUES ($1)",
                        filename
                    )
                    
                    logger.info(f"Successfully applied migration: {filename}")
                    
                except Exception as e:
                    logger.error(f"Failed to apply migration {filename}: {e}")
                    raise DatabaseInitError(f"Migration {filename} failed: {e}") from e
            
        finally:
            if conn:
                await conn.close()
    
    async def _create_pool(self) -> None:
        """Create the connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=self.pool_min,
                max_size=self.pool_max,
                command_timeout=30,
                server_settings={
                    'application_name': 'SecondShiftAugie_Memory'
                }
            )
            logger.info(f"Created connection pool (min={self.pool_min}, max={self.pool_max})")
        except Exception as e:
            raise DatabaseInitError(f"Failed to create connection pool: {e}") from e 
   
    async def _validate_schema(self) -> None:
        """Validate that all required tables and extensions exist."""
        required_tables = [
            'messages',
            'thread_summaries', 
            'memories',
            'guild_settings',
            'schema_migrations'
        ]
        
        required_extensions = ['vector']
        
        if not self.pool:
            raise DatabaseInitError("Connection pool not initialized")
        
        async with self.pool.acquire() as conn:
            # Check extensions
            for ext in required_extensions:
                result = await conn.fetchval(
                    "SELECT 1 FROM pg_extension WHERE extname = $1", ext
                )
                if not result:
                    raise DatabaseInitError(f"Required extension '{ext}' not installed")
            
            # Check tables
            for table in required_tables:
                result = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = $1", 
                    table
                )
                if not result:
                    raise DatabaseInitError(f"Required table '{table}' not found")
            
            # Check HNSW index on memories table
            index_result = await conn.fetchval("""
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'memories' 
                AND indexname = 'idx_memories_embedding'
            """)
            if not index_result:
                raise DatabaseInitError("HNSW index on memories.embedding not found")
        
        logger.info("Schema validation passed")
    
    async def get_connection(self) -> Connection:
        """Get a connection from the pool."""
        if not self.pool:
            raise DatabaseInitError("Database not initialized")
        return await self.pool.acquire()
    
    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed")
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the database.
        
        Returns:
            bool: True if database is healthy, False otherwise
        """
        try:
            if not self.pool:
                return False
            
            async with self.pool.acquire() as conn:
                # Test basic query
                await conn.execute("SELECT 1")
                
                # Test vector extension
                await conn.execute("SELECT vector_dims(ARRAY[1,2,3]::vector)")
                
                # Test each required table
                await conn.execute("SELECT COUNT(*) FROM messages LIMIT 1")
                await conn.execute("SELECT COUNT(*) FROM thread_summaries LIMIT 1") 
                await conn.execute("SELECT COUNT(*) FROM memories LIMIT 1")
                await conn.execute("SELECT COUNT(*) FROM guild_settings LIMIT 1")
                
            return True
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


async def initialize_database(dsn: str, pool_min: int = 2, pool_max: int = 10) -> DatabaseManager:
    """
    Initialize database and return configured DatabaseManager.
    
    Args:
        dsn: PostgreSQL connection string
        pool_min: Minimum pool size
        pool_max: Maximum pool size
        
    Returns:
        DatabaseManager: Initialized database manager
        
    Raises:
        DatabaseInitError: If initialization fails
    """
    db_manager = DatabaseManager(dsn, pool_min, pool_max)
    await db_manager.initialize()
    return db_manager


# Convenience function for getting DSN from environment
def get_database_dsn() -> str:
    """Get database DSN from environment variables."""
    dsn = os.getenv('PG_DSN')
    if not dsn:
        # Fallback to individual components
        host = os.getenv('PG_HOST', 'localhost')
        port = os.getenv('PG_PORT', '5432')
        database = os.getenv('PG_DATABASE', 'ssa')
        user = os.getenv('PG_USER', 'ssa')
        password = os.getenv('PG_PASSWORD', 'ssa')
        
        dsn = f"postgres://{user}:{password}@{host}:{port}/{database}"
    
    return dsn


if __name__ == "__main__":
    # Simple test script
    async def main():
        logging.basicConfig(level=logging.INFO)
        
        try:
            dsn = get_database_dsn()
            db_manager = await initialize_database(dsn)
            
            # Test health check
            is_healthy = await db_manager.health_check()
            print(f"Database health check: {'PASSED' if is_healthy else 'FAILED'}")
            
            await db_manager.close()
            
        except DatabaseInitError as e:
            print(f"Database initialization failed: {e}")
            return 1
        
        return 0
    
    exit(asyncio.run(main()))