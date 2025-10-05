#!/usr/bin/env python3
"""
Memory system configuration management CLI.

This script provides utilities for managing memory system configuration,
including validation, feature flags, and environment setup.

Usage:
    python scripts/memory_config.py [command] [options]
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from memory.config import MemoryConfig, MemoryConfigError
    from memory.config_validator import validate_memory_config, print_validation_results
except ImportError as e:
    print(f"Error importing memory modules: {e}")
    sys.exit(1)


def print_config_info(config: MemoryConfig) -> None:
    """Print configuration information in a readable format."""
    print("="*50)
    print("MEMORY SYSTEM CONFIGURATION")
    print("="*50)
    
    print(f"\nGeneral:")
    print(f"  Memory Enabled: {config.memory_enabled}")
    print(f"  Export Directory: {config.memory_export_dir}")
    print(f"  Min Importance: {config.memory_min_importance}")
    
    print(f"\nDatabase:")
    print(f"  DSN: {config.pg_dsn[:50]}{'...' if len(config.pg_dsn) > 50 else ''}")
    print(f"  Pool Size: {config.pg_pool_min}-{config.pg_pool_max}")
    
    print(f"\nEmbeddings:")
    print(f"  Model: {config.embed_model}")
    print(f"  Ollama URL: {config.embed_ollama_url}")
    
    print(f"\nSTM Configuration:")
    print(f"  Max Tokens: {config.stm_max_tokens}")
    print(f"  Keep Last: {config.stm_keep_last}")
    
    print(f"\nRetrieval Configuration:")
    print(f"  Top K: {config.retrieve_top_k}")
    print(f"  Recency Window: {config.recency_window_days} days")
    print(f"  Boost Weights: similarity={config.boost_similarity}, recency={config.boost_recency}, importance={config.boost_importance}")
    
    print(f"\nFeature Availability:")
    features = ['stm', 'ltm', 'embeddings', 'export', 'vector_search']
    for feature in features:
        status = "✓" if config.is_feature_enabled(feature) else "✗"
        print(f"  {status} {feature.upper()}")


def print_feature_flags(config: MemoryConfig) -> None:
    """Print feature flag status."""
    print("="*40)
    print("MEMORY SYSTEM FEATURE FLAGS")
    print("="*40)
    
    features = {
        'memory_enabled': config.memory_enabled,
        'stm': config.is_feature_enabled('stm'),
        'ltm': config.is_feature_enabled('ltm'),
        'embeddings': config.is_feature_enabled('embeddings'),
        'export': config.is_feature_enabled('export'),
        'summarization': config.is_feature_enabled('summarization'),
        'vector_search': config.is_feature_enabled('vector_search'),
    }
    
    for feature, enabled in features.items():
        status = "✓ ENABLED " if enabled else "✗ DISABLED"
        print(f"  {status} {feature}")
    
    # Operation mode
    if config.is_feature_enabled('ltm') and config.is_feature_enabled('embeddings'):
        mode = "Full Memory Mode"
    elif config.is_feature_enabled('stm'):
        mode = "STM-Only Mode"
    else:
        mode = "No Memory Mode"
    
    print(f"\nOperation Mode: {mode}")


def generate_env_template(config: MemoryConfig, output_file: str = None) -> None:
    """Generate environment template based on current configuration."""
    template = f"""# SecondShiftAugie Memory System Configuration
# Generated from current configuration

# Master switch for memory features
MEMORY_ENABLED={str(config.memory_enabled).lower()}

# Database Configuration (Required if memory enabled)
PG_DSN={config.pg_dsn}
PG_POOL_MIN={config.pg_pool_min}
PG_POOL_MAX={config.pg_pool_max}

# Embedding Configuration (Required for LTM)
EMBED_MODEL={config.embed_model}
EMBED_OLLAMA_URL={config.embed_ollama_url}

# Short-Term Memory Behavior
STM_MAX_TOKENS={config.stm_max_tokens}
STM_KEEP_LAST={config.stm_keep_last}

# Retrieval Configuration
RETRIEVE_TOP_K={config.retrieve_top_k}
RECENCY_WINDOW_DAYS={config.recency_window_days}
BOOST_SIMILARITY={config.boost_similarity}
BOOST_RECENCY={config.boost_recency}
BOOST_IMPORTANCE={config.boost_importance}

# Policy Configuration
MEMORY_MIN_IMPORTANCE={config.memory_min_importance}
MEMORY_EXPORT_DIR={config.memory_export_dir}
"""
    
    if output_file:
        Path(output_file).write_text(template)
        print(f"Environment template written to: {output_file}")
    else:
        print(template)


async def cmd_info(args) -> int:
    """Show configuration information."""
    try:
        config = MemoryConfig.from_environment()
        print_config_info(config)
        return 0
    except MemoryConfigError as e:
        print(f"Configuration error: {e}")
        return 1


async def cmd_validate(args) -> int:
    """Validate configuration."""
    try:
        config = MemoryConfig.from_environment()
        result = await validate_memory_config(
            config=config,
            check_connectivity=not args.no_connectivity,
            check_permissions=not args.no_permissions
        )
        
        if args.json:
            output = {
                "valid": result.is_valid(),
                "summary": result.get_summary(),
                "errors": result.errors,
                "warnings": result.warnings,
                "features": result.features,
                "connectivity": result.connectivity
            }
            print(json.dumps(output, indent=2))
        else:
            print_validation_results(result)
        
        return 0 if result.is_valid() else 1
        
    except MemoryConfigError as e:
        print(f"Configuration error: {e}")
        return 1


async def cmd_features(args) -> int:
    """Show feature flag status."""
    try:
        config = MemoryConfig.from_environment()
        
        if args.json:
            features = {
                'memory_enabled': config.memory_enabled,
                'stm': config.is_feature_enabled('stm'),
                'ltm': config.is_feature_enabled('ltm'),
                'embeddings': config.is_feature_enabled('embeddings'),
                'export': config.is_feature_enabled('export'),
                'summarization': config.is_feature_enabled('summarization'),
                'vector_search': config.is_feature_enabled('vector_search'),
            }
            print(json.dumps(features, indent=2))
        else:
            print_feature_flags(config)
        
        return 0
        
    except MemoryConfigError as e:
        print(f"Configuration error: {e}")
        return 1


async def cmd_template(args) -> int:
    """Generate environment template."""
    try:
        config = MemoryConfig.from_environment()
        generate_env_template(config, args.output)
        return 0
    except MemoryConfigError as e:
        print(f"Configuration error: {e}")
        return 1


async def cmd_check_feature(args) -> int:
    """Check if a specific feature is enabled."""
    try:
        config = MemoryConfig.from_environment()
        enabled = config.is_feature_enabled(args.feature)
        
        if args.json:
            print(json.dumps({"feature": args.feature, "enabled": enabled}))
        else:
            status = "ENABLED" if enabled else "DISABLED"
            print(f"{args.feature}: {status}")
        
        return 0 if enabled else 1
        
    except MemoryConfigError as e:
        print(f"Configuration error: {e}")
        return 1


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Memory system configuration management",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show configuration information')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    validate_parser.add_argument('--no-connectivity', action='store_true', help='Skip connectivity tests')
    validate_parser.add_argument('--no-permissions', action='store_true', help='Skip permission tests')
    validate_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # Features command
    features_parser = subparsers.add_parser('features', help='Show feature flag status')
    features_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # Template command
    template_parser = subparsers.add_parser('template', help='Generate environment template')
    template_parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    
    # Check-feature command
    check_parser = subparsers.add_parser('check-feature', help='Check if specific feature is enabled')
    check_parser.add_argument('feature', help='Feature name to check')
    check_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Route to command handlers
    commands = {
        'info': cmd_info,
        'validate': cmd_validate,
        'features': cmd_features,
        'template': cmd_template,
        'check-feature': cmd_check_feature,
    }
    
    handler = commands.get(args.command)
    if handler:
        try:
            return await handler(args)
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return 1
        except Exception as e:
            print(f"Error: {e}")
            return 1
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))