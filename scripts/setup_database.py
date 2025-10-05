#!/usr/bin/env python3
"""
Database setup script for SecondShiftAugie Memory System.

This script creates the necessary database schema and verifies the setup.
It can be run standalone or imported as a module.

Usage:
    python scripts/setup_database.py [--dsn postgres://...] [--force]
    
Requirements:
    - PostgreSQL with pgvector extension
    - asyncpg library
    - Appropriate database permissions
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

try:
    import asyncpg
except ImportError:
    print("Error: asyncpg library not found. Install with: pip install asyncpg")
    sys.exit(1)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from memory.config import MemoryConfig, MemoryConfigError
except ImportError:
    print("Error: Could not import memory configuration. Ensure src/memory/config.py exists.")
    sys.exit(1)


logger = logging.getLogger(__name__)


class DatabaseSetupError(Exception):
    """Exception raised during database setup."""
    pass


async def check_pgvector_extension(conn: asyncpg.Connection) -> bool:
    """
    Check if pgvector extension is available and installed.
    
    Args:
        conn: Database connection
        
    Returns:
        bool: True if pgvector is available
        
    Raises:
        DatabaseSetupError: If pgvector is not available
    """
    try:
        # Check if extension is available
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_available_extensions WHERE name = 'vector'"
        )
        
        if result == 0:
            raise DatabaseSetupError(
                "pgvector extension is not available. "
                "Please install pgvector: https://github.com/pgvector/pgvector"
            )
        
        # Check if extension is installed
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'"
        )
        
        if result == 0:
            logger.info("Installing pgvector extension...")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            logger.info("pgvector extension installed successfully")
        else:
            version = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            logger.info(f"pgvector extension already installed (version: {version})")
        
        return True
        
    except asyncpg.exceptions.InsufficientPrivilegeError:
        raise DatabaseSetupError(
            "Insufficient privileges to install pgvector extension. "
            "Please run as superuser or ask your DBA to install it."
        )
    except Exception as e:
        raise DatabaseSetupError(f"Error checking pgvector extension: {e}")


async def create_tables(conn: asyncpg.Connection) -> None:
    """
    Create all necessary tables for the memory system.
    
    Args:
        conn: Database connection
        
    Raises:
        DatabaseSetupError: If table creation fails
    """
    try:
        # Read SQL setup script
        sql_file = Path(__file__).parent / "setup_database.sql"
        if not sql_file.exists():
            raise DatabaseSetupError(f"SQL setup script not found: {sql_file}")
        
        sql_content = sql_file.read_text()
        
        # Execute the setup script
        logger.info("Creating database schema...")
        await conn.execute(sql_content)
        logger.info("Database schema created successfully")
        
    except Exception as e:
        raise DatabaseSetupError(f"Error creating tables: {e}")


async def verify_setup(conn: asyncpg.Connection) -> dict:
    """
    Verify the database setup is correct.
    
    Args:
        conn: Database connection
        
    Returns:
        dict: Verification results
        
    Raises:
        DatabaseSetupError: If verification fails
    """
    try:
        results = {}
        
        # Check tables exist
        tables = ['messages', 'thread_summaries', 'memories', 'guild_settings']
        for table in tables:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = 'public'",
                table
            )
            results[f"table_{table}"] = count > 0
        
        # Check pgvector extension
        vector_version = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        results["pgvector_installed"] = vector_version is not None
        results["pgvector_version"] = vector_version
        
        # Check indexes exist
        indexes = [
            'idx_messages_thread',
            'idx_memories_embedding',
            'idx_memories_scope'
        ]
        for index in indexes:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE indexname = $1 AND schemaname = 'public'",
                index
            )
            results[f"index_{index}"] = count > 0
        
        # Test vector operations
        try:
            await conn.execute("SELECT '[1,2,3]'::vector")
            results["vector_operations"] = True
        except Exception:
            results["vector_operations"] = False
        
        return results
        
    except Exception as e:
        raise DatabaseSetupError(f"Error verifying setup: {e}")


async def setup_database(dsn: str, force: bool = False) -> dict:
    """
    Set up the database for the memory system.
    
    Args:
        dsn: PostgreSQL connection string
        force: Whether to force setup even if tables exist
        
    Returns:
        dict: Setup results
        
    Raises:
        DatabaseSetupError: If setup fails
    """
    try:
        logger.info(f"Connecting to database...")
        conn = await asyncpg.connect(dsn)
        
        try:
            # Check if tables already exist
            if not force:
                existing_tables = await conn.fetchval(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name IN ('messages', 'memories') AND table_schema = 'public'"
                )
                
                if existing_tables > 0:
                    logger.warning("Memory system tables already exist. Use --force to recreate.")
                    return await verify_setup(conn)
            
            # Check and install pgvector
            await check_pgvector_extension(conn)
            
            # Create tables and indexes
            await create_tables(conn)
            
            # Verify setup
            results = await verify_setup(conn)
            
            logger.info("Database setup completed successfully!")
            return results
            
        finally:
            await conn.close()
            
    except asyncpg.exceptions.InvalidCatalogNameError:
        raise DatabaseSetupError(
            "Database does not exist. Please create it first:\n"
            "CREATE DATABASE ssa;"
        )
    except asyncpg.exceptions.InvalidPasswordError:
        raise DatabaseSetupError("Invalid database credentials")
    except asyncpg.exceptions.CannotConnectNowError:
        raise DatabaseSetupError("Cannot connect to database. Is PostgreSQL running?")
    except Exception as e:
        raise DatabaseSetupError(f"Database setup failed: {e}")


def print_verification_results(results: dict) -> None:
    """Print verification results in a readable format."""
    print("\n" + "="*50)
    print("DATABASE SETUP VERIFICATION")
    print("="*50)
    
    # Tables
    print("\nTables:")
    for key, value in results.items():
        if key.startswith("table_"):
            table_name = key.replace("table_", "")
            status = "✓" if value else "✗"
            print(f"  {status} {table_name}")
    
    # Indexes
    print("\nIndexes:")
    for key, value in results.items():
        if key.startswith("index_"):
            index_name = key.replace("index_", "")
            status = "✓" if value else "✗"
            print(f"  {status} {index_name}")
    
    # Extensions
    print("\nExtensions:")
    pgvector_installed = results.get("pgvector_installed", False)
    pgvector_version = results.get("pgvector_version", "unknown")
    status = "✓" if pgvector_installed else "✗"
    print(f"  {status} pgvector ({pgvector_version})")
    
    # Operations
    print("\nOperations:")
    vector_ops = results.get("vector_operations", False)
    status = "✓" if vector_ops else "✗"
    print(f"  {status} Vector operations")
    
    # Overall status
    all_good = all([
        results.get("table_messages", False),
        results.get("table_memories", False),
        results.get("pgvector_installed", False),
        results.get("vector_operations", False)
    ])
    
    print(f"\nOverall Status: {'✓ READY' if all_good else '✗ ISSUES FOUND'}")
    print("="*50)


async def main():
    """Main entry point for the setup script."""
    parser = argparse.ArgumentParser(
        description="Set up database for SecondShiftAugie Memory System"
    )
    parser.add_argument(
        "--dsn",
        help="PostgreSQL connection string (default: from PG_DSN env var)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force setup even if tables exist"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing setup, don't create anything"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    try:
        # Get database DSN
        if args.dsn:
            dsn = args.dsn
        else:
            try:
                config = MemoryConfig.from_environment()
                dsn = config.pg_dsn
            except MemoryConfigError as e:
                print(f"Error loading configuration: {e}")
                print("Please provide --dsn or set PG_DSN environment variable")
                sys.exit(1)
        
        # Run setup or verification
        if args.verify_only:
            logger.info("Verifying existing database setup...")
            conn = await asyncpg.connect(dsn)
            try:
                results = await verify_setup(conn)
            finally:
                await conn.close()
        else:
            results = await setup_database(dsn, force=args.force)
        
        # Print results
        print_verification_results(results)
        
        # Exit with appropriate code
        all_good = all([
            results.get("table_messages", False),
            results.get("table_memories", False),
            results.get("pgvector_installed", False),
            results.get("vector_operations", False)
        ])
        
        sys.exit(0 if all_good else 1)
        
    except DatabaseSetupError as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())