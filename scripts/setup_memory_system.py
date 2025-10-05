#!/usr/bin/env python3
"""
Complete setup script for SecondShiftAugie Memory System.

This script handles the complete setup process including:
- Environment validation
- Database setup and verification
- Configuration validation
- Feature availability checks

Usage:
    python scripts/setup_memory_system.py [options]
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from memory.config import MemoryConfig, MemoryConfigError
    from memory.config_validator import validate_memory_config, print_validation_results
except ImportError as e:
    print(f"Error importing memory modules: {e}")
    print("Ensure src/memory/ directory exists with required modules")
    sys.exit(1)

# Import database setup
try:
    from setup_database import setup_database, DatabaseSetupError
except ImportError:
    print("Error: setup_database.py not found in scripts directory")
    sys.exit(1)


logger = logging.getLogger(__name__)


class MemorySystemSetupError(Exception):
    """Exception raised during memory system setup."""
    pass


async def setup_memory_system(
    dsn: Optional[str] = None,
    force_db_setup: bool = False,
    skip_db_setup: bool = False,
    skip_validation: bool = False
) -> bool:
    """
    Set up the complete memory system.
    
    Args:
        dsn: Database connection string (optional)
        force_db_setup: Force database setup even if tables exist
        skip_db_setup: Skip database setup entirely
        skip_validation: Skip configuration validation
        
    Returns:
        bool: True if setup successful
        
    Raises:
        MemorySystemSetupError: If setup fails
    """
    try:
        print("="*60)
        print("SECONDSHIFTAUGIE MEMORY SYSTEM SETUP")
        print("="*60)
        
        # Step 1: Load and validate configuration
        print("\n1. Loading configuration...")
        try:
            if dsn:
                # Create temporary config with provided DSN
                import os
                original_dsn = os.environ.get('PG_DSN')
                os.environ['PG_DSN'] = dsn
                config = MemoryConfig.from_environment()
                if original_dsn:
                    os.environ['PG_DSN'] = original_dsn
                else:
                    os.environ.pop('PG_DSN', None)
            else:
                config = MemoryConfig.from_environment()
            
            print(f"✓ Configuration loaded: {config}")
            
        except MemoryConfigError as e:
            raise MemorySystemSetupError(f"Configuration error: {e}")
        
        # Step 2: Database setup
        if not skip_db_setup:
            print("\n2. Setting up database...")
            try:
                db_dsn = dsn or config.pg_dsn
                db_results = await setup_database(db_dsn, force=force_db_setup)
                
                # Check if setup was successful
                required_tables = ['table_messages', 'table_memories', 'table_thread_summaries']
                missing_tables = [t for t in required_tables if not db_results.get(t, False)]
                
                if missing_tables:
                    raise MemorySystemSetupError(f"Database setup incomplete: missing {missing_tables}")
                
                if not db_results.get('pgvector_installed', False):
                    raise MemorySystemSetupError("pgvector extension not available")
                
                print("✓ Database setup completed successfully")
                
            except DatabaseSetupError as e:
                raise MemorySystemSetupError(f"Database setup failed: {e}")
        else:
            print("\n2. Skipping database setup (--skip-db-setup)")
        
        # Step 3: Configuration validation
        if not skip_validation:
            print("\n3. Validating configuration...")
            
            validation_result = await validate_memory_config(
                config=config,
                check_connectivity=True,
                check_permissions=True
            )
            
            if not validation_result.is_valid():
                print("\n⚠ Configuration validation found issues:")
                print_validation_results(validation_result)
                
                # Check if errors are critical
                critical_errors = [
                    error for error in validation_result.errors
                    if any(keyword in error.lower() for keyword in [
                        'database', 'connection', 'pgvector', 'extension'
                    ])
                ]
                
                if critical_errors:
                    raise MemorySystemSetupError("Critical configuration errors found")
                else:
                    print("\n⚠ Non-critical issues found, continuing...")
            else:
                print("✓ Configuration validation passed")
        else:
            print("\n3. Skipping configuration validation (--skip-validation)")
        
        # Step 4: Feature availability summary
        print("\n4. Feature availability summary...")
        
        features = ['stm', 'ltm', 'embeddings', 'export', 'vector_search']
        available_features = []
        unavailable_features = []
        
        for feature in features:
            if config.is_feature_enabled(feature):
                available_features.append(feature)
                print(f"✓ {feature.upper()}")
            else:
                unavailable_features.append(feature)
                print(f"✗ {feature.upper()}")
        
        # Step 5: Setup completion
        print("\n" + "="*60)
        print("SETUP COMPLETED")
        print("="*60)
        
        print(f"\nFeatures available: {len(available_features)}/{len(features)}")
        print(f"Available: {', '.join(available_features) if available_features else 'None'}")
        if unavailable_features:
            print(f"Unavailable: {', '.join(unavailable_features)}")
        
        # Determine operation mode
        if config.is_feature_enabled('ltm') and config.is_feature_enabled('embeddings'):
            mode = "Full Memory Mode (STM + LTM + Embeddings)"
        elif config.is_feature_enabled('stm'):
            mode = "STM-Only Mode (No embeddings/LTM)"
        else:
            mode = "No Memory Mode (Basic bot only)"
        
        print(f"\nOperation Mode: {mode}")
        
        # Next steps
        print(f"\nNext steps:")
        print(f"1. Update your .env file with the configuration")
        print(f"2. Ensure Ollama is running with the embedding model: {config.embed_model}")
        print(f"3. Start the bot with: python run_voxcpm_bot.py")
        
        if unavailable_features:
            print(f"\nTo enable missing features:")
            if 'ltm' in unavailable_features or 'embeddings' in unavailable_features:
                print(f"- Install and start Ollama: https://ollama.ai/")
                print(f"- Pull embedding model: ollama pull {config.embed_model}")
            if 'export' in unavailable_features:
                print(f"- Ensure export directory is writable: {config.memory_export_dir}")
        
        return True
        
    except Exception as e:
        logger.error(f"Memory system setup failed: {e}")
        raise MemorySystemSetupError(f"Setup failed: {e}")


async def main():
    """Main entry point for the setup script."""
    parser = argparse.ArgumentParser(
        description="Set up SecondShiftAugie Memory System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full setup with default configuration
  python scripts/setup_memory_system.py
  
  # Setup with custom database
  python scripts/setup_memory_system.py --dsn postgres://user:pass@host:5432/db
  
  # Force database recreation
  python scripts/setup_memory_system.py --force-db-setup
  
  # Skip database setup (already done)
  python scripts/setup_memory_system.py --skip-db-setup
  
  # Quick validation only
  python scripts/setup_memory_system.py --skip-db-setup --validation-only
        """
    )
    
    parser.add_argument(
        "--dsn",
        help="PostgreSQL connection string (overrides PG_DSN env var)"
    )
    parser.add_argument(
        "--force-db-setup",
        action="store_true",
        help="Force database setup even if tables exist"
    )
    parser.add_argument(
        "--skip-db-setup",
        action="store_true",
        help="Skip database setup entirely"
    )
    parser.add_argument(
        "--validation-only",
        action="store_true",
        help="Only run configuration validation"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip configuration validation"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error output"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.quiet:
        log_level = logging.ERROR
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    try:
        # Handle validation-only mode
        if args.validation_only:
            print("Running configuration validation only...")
            
            try:
                config = MemoryConfig.from_environment()
            except MemoryConfigError as e:
                print(f"Configuration error: {e}")
                return 1
            
            result = await validate_memory_config(config)
            print_validation_results(result)
            return 0 if result.is_valid() else 1
        
        # Run full setup
        success = await setup_memory_system(
            dsn=args.dsn,
            force_db_setup=args.force_db_setup,
            skip_db_setup=args.skip_db_setup,
            skip_validation=args.skip_validation
        )
        
        return 0 if success else 1
        
    except MemorySystemSetupError as e:
        if not args.quiet:
            print(f"\n✗ Setup failed: {e}")
        logger.error(f"Setup failed: {e}")
        return 1
    except KeyboardInterrupt:
        if not args.quiet:
            print("\n✗ Setup cancelled by user")
        return 1
    except Exception as e:
        if not args.quiet:
            print(f"\n✗ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))