"""
Configuration validation utilities for the memory system.

This module provides comprehensive validation and diagnostic tools for memory
system configuration, including connectivity tests and feature availability checks.

Requirements addressed:
- 4.1: Configuration validation with helpful error messages
- 4.2: Feature flag handling for memory system enable/disable
- 4.3: Environment setup validation
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import json

try:
    import asyncpg
except ImportError:
    asyncpg = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .config import MemoryConfig, MemoryConfigError


logger = logging.getLogger(__name__)


class ConfigValidationResult:
    """Results of configuration validation."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.features: Dict[str, bool] = {}
        self.connectivity: Dict[str, bool] = {}
        
    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        logger.error(message)
    
    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)
        logger.warning(message)
    
    def add_info(self, message: str) -> None:
        """Add an info message."""
        self.info.append(message)
        logger.info(message)
    
    def is_valid(self) -> bool:
        """Check if configuration is valid (no errors)."""
        return len(self.errors) == 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get validation summary."""
        return {
            "valid": self.is_valid(),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "features_available": sum(self.features.values()),
            "features_total": len(self.features),
            "connectivity_ok": sum(self.connectivity.values()),
            "connectivity_total": len(self.connectivity)
        }


class MemoryConfigValidator:
    """Comprehensive configuration validator for the memory system."""
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        
    async def validate_full(self, 
                          check_connectivity: bool = True,
                          check_permissions: bool = True) -> ConfigValidationResult:
        """
        Perform comprehensive configuration validation.
        
        Args:
            check_connectivity: Whether to test network connectivity
            check_permissions: Whether to check file/directory permissions
            
        Returns:
            ConfigValidationResult: Validation results
        """
        result = ConfigValidationResult()
        
        # Basic configuration validation (already done in config.__post_init__)
        try:
            self.config._validate_config()
            result.add_info("Basic configuration validation passed")
        except MemoryConfigError as e:
            result.add_error(f"Configuration validation failed: {e}")
            return result  # Don't continue if basic validation fails
        
        # Feature availability checks
        await self._check_feature_availability(result)
        
        # Connectivity checks
        if check_connectivity:
            await self._check_connectivity(result)
        
        # Permission checks
        if check_permissions:
            await self._check_permissions(result)
        
        # Environment checks
        await self._check_environment(result)
        
        return result
    
    async def _check_feature_availability(self, result: ConfigValidationResult) -> None:
        """Check which memory features are available."""
        features = [
            'stm', 'ltm', 'embeddings', 'export', 
            'summarization', 'vector_search'
        ]
        
        for feature in features:
            available = self.config.is_feature_enabled(feature)
            result.features[feature] = available
            
            if available:
                result.add_info(f"Feature '{feature}' is available")
            else:
                result.add_warning(f"Feature '{feature}' is not available")
        
        # Check for critical feature combinations
        if not result.features.get('stm', False):
            result.add_error("Short-term memory (STM) is not available")
        
        if result.features.get('ltm', False) and not result.features.get('embeddings', False):
            result.add_warning("LTM enabled but embeddings not available - will degrade to STM-only")
    
    async def _check_connectivity(self, result: ConfigValidationResult) -> None:
        """Check connectivity to external services."""
        
        # Check database connectivity
        if self.config.pg_dsn:
            db_ok = await self._test_database_connection(result)
            result.connectivity['database'] = db_ok
        else:
            result.connectivity['database'] = False
            result.add_warning("Database DSN not configured")
        
        # Check Ollama connectivity
        if self.config.embed_ollama_url:
            ollama_ok = await self._test_ollama_connection(result)
            result.connectivity['ollama'] = ollama_ok
        else:
            result.connectivity['ollama'] = False
            result.add_warning("Ollama URL not configured")
    
    async def _test_database_connection(self, result: ConfigValidationResult) -> bool:
        """Test database connectivity and pgvector availability."""
        if not asyncpg:
            result.add_error("asyncpg library not available for database testing")
            return False
        
        try:
            conn = await asyncpg.connect(self.config.pg_dsn)
            try:
                # Test basic connection
                await conn.fetchval("SELECT 1")
                result.add_info("Database connection successful")
                
                # Test pgvector extension
                pgvector_version = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
                
                if pgvector_version:
                    result.add_info(f"pgvector extension available (version: {pgvector_version})")
                    
                    # Test vector operations
                    try:
                        await conn.execute("SELECT '[1,2,3]'::vector")
                        result.add_info("Vector operations working")
                        return True
                    except Exception as e:
                        result.add_error(f"Vector operations failed: {e}")
                        return False
                else:
                    result.add_error("pgvector extension not installed")
                    return False
                    
            finally:
                await conn.close()
                
        except asyncpg.exceptions.InvalidCatalogNameError:
            result.add_error("Database does not exist")
            return False
        except asyncpg.exceptions.InvalidPasswordError:
            result.add_error("Database authentication failed")
            return False
        except asyncpg.exceptions.CannotConnectNowError:
            result.add_error("Cannot connect to database - server may be down")
            return False
        except Exception as e:
            result.add_error(f"Database connection failed: {e}")
            return False
    
    async def _test_ollama_connection(self, result: ConfigValidationResult) -> bool:
        """Test Ollama connectivity and model availability."""
        if not aiohttp:
            result.add_error("aiohttp library not available for Ollama testing")
            return False
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Test basic connectivity
                async with session.get(f"{self.config.embed_ollama_url}/api/tags") as response:
                    if response.status == 200:
                        result.add_info("Ollama API connection successful")
                        
                        # Check if embedding model is available
                        data = await response.json()
                        models = [model['name'] for model in data.get('models', [])]
                        
                        if self.config.embed_model in models:
                            result.add_info(f"Embedding model '{self.config.embed_model}' is available")
                            return True
                        else:
                            result.add_warning(
                                f"Embedding model '{self.config.embed_model}' not found. "
                                f"Available models: {', '.join(models)}"
                            )
                            return False
                    else:
                        result.add_error(f"Ollama API returned status {response.status}")
                        return False
                        
        except aiohttp.ClientConnectorError:
            result.add_error("Cannot connect to Ollama - server may be down")
            return False
        except asyncio.TimeoutError:
            result.add_error("Ollama connection timeout")
            return False
        except Exception as e:
            result.add_error(f"Ollama connection failed: {e}")
            return False
    
    async def _check_permissions(self, result: ConfigValidationResult) -> None:
        """Check file and directory permissions."""
        
        # Check export directory
        try:
            export_path = self.config.ensure_export_directory()
            if export_path.exists() and export_path.is_dir():
                # Test write permissions
                test_file = export_path / ".test_write"
                try:
                    test_file.write_text("test")
                    test_file.unlink()
                    result.add_info(f"Export directory writable: {export_path}")
                except Exception as e:
                    result.add_error(f"Export directory not writable: {e}")
            else:
                result.add_error(f"Export directory not accessible: {export_path}")
        except Exception as e:
            result.add_error(f"Cannot access export directory: {e}")
    
    async def _check_environment(self, result: ConfigValidationResult) -> None:
        """Check environment-specific configuration."""
        
        # Check for development vs production settings
        if "localhost" in self.config.pg_dsn or "127.0.0.1" in self.config.pg_dsn:
            result.add_info("Using local database (development mode)")
        else:
            result.add_info("Using remote database (production mode)")
            
            # Production-specific checks
            if "sslmode=require" not in self.config.pg_dsn:
                result.add_warning("SSL not required for database connection in production")
        
        # Check pool sizes
        if self.config.pg_pool_max > 20:
            result.add_warning(f"Large connection pool size ({self.config.pg_pool_max}) - monitor resource usage")
        
        # Check token budget
        if self.config.stm_max_tokens > 4000:
            result.add_warning(f"Large STM token budget ({self.config.stm_max_tokens}) - may impact performance")
        
        # Check boost weights
        total_boost = self.config.boost_similarity + self.config.boost_recency + self.config.boost_importance
        if abs(total_boost - 1.0) > 0.05:
            result.add_warning(f"Boost weights sum to {total_boost:.3f}, should be close to 1.0")


async def validate_memory_config(config: Optional[MemoryConfig] = None,
                               check_connectivity: bool = True,
                               check_permissions: bool = True) -> ConfigValidationResult:
    """
    Validate memory system configuration.
    
    Args:
        config: Configuration to validate (loads from env if None)
        check_connectivity: Whether to test network connectivity
        check_permissions: Whether to check file permissions
        
    Returns:
        ConfigValidationResult: Validation results
    """
    if config is None:
        try:
            config = MemoryConfig.from_environment()
        except MemoryConfigError as e:
            result = ConfigValidationResult()
            result.add_error(f"Failed to load configuration: {e}")
            return result
    
    validator = MemoryConfigValidator(config)
    return await validator.validate_full(check_connectivity, check_permissions)


def print_validation_results(result: ConfigValidationResult) -> None:
    """Print validation results in a readable format."""
    print("\n" + "="*60)
    print("MEMORY SYSTEM CONFIGURATION VALIDATION")
    print("="*60)
    
    # Summary
    summary = result.get_summary()
    status = "✓ VALID" if result.is_valid() else "✗ INVALID"
    print(f"\nOverall Status: {status}")
    print(f"Errors: {summary['error_count']}, Warnings: {summary['warning_count']}")
    
    # Features
    if result.features:
        print(f"\nFeature Availability ({summary['features_available']}/{summary['features_total']}):")
        for feature, available in result.features.items():
            status = "✓" if available else "✗"
            print(f"  {status} {feature}")
    
    # Connectivity
    if result.connectivity:
        print(f"\nConnectivity ({summary['connectivity_ok']}/{summary['connectivity_total']}):")
        for service, ok in result.connectivity.items():
            status = "✓" if ok else "✗"
            print(f"  {status} {service}")
    
    # Messages
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  ✗ {error}")
    
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  ⚠ {warning}")
    
    if result.info:
        print(f"\nInfo ({len(result.info)}):")
        for info in result.info:
            print(f"  ℹ {info}")
    
    print("="*60)


async def main():
    """CLI entry point for configuration validation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate memory system configuration")
    parser.add_argument("--no-connectivity", action="store_true", help="Skip connectivity tests")
    parser.add_argument("--no-permissions", action="store_true", help="Skip permission tests")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise for CLI
    
    # Run validation
    result = await validate_memory_config(
        check_connectivity=not args.no_connectivity,
        check_permissions=not args.no_permissions
    )
    
    # Output results
    if args.json:
        output = {
            "valid": result.is_valid(),
            "summary": result.get_summary(),
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
            "features": result.features,
            "connectivity": result.connectivity
        }
        print(json.dumps(output, indent=2))
    else:
        print_validation_results(result)
    
    # Exit with appropriate code
    return 0 if result.is_valid() else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))