#!/usr/bin/env python3
"""
Launcher script for SecondShiftAugie bot with VoxCPM integration.

This script provides a simple way to start the bot from the project root directory.
It handles Python path setup and provides command-line options for configuration.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from main import main


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="SecondShiftAugie Discord Bot with VoxCPM TTS Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_bot.py                    # Start bot with default settings
  python run_bot.py --verbose          # Start with verbose logging
  python run_bot.py --check-config     # Validate configuration without starting

Environment Variables:
  BOT_TOKEN              Discord bot token (required)
  CHANNEL_ID             Discord channel ID for bot messages (required)
  VOICE_CHANNEL_ID       Default voice channel ID (optional)
  SAVE_PATH              Directory for temporary audio files (default: ./temp_audio)
  VOXCPM_MODEL_PATH      VoxCPM model path (default: openbmb/VoxCPM-0.5B)
  VOXCPM_PROMPT_WAV      Reference audio file path (default: assets/model.wav)
  VOXCPM_PROMPT_TEXT     Reference text file path (default: assets/transcript.txt)
        """
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--check-config', '-c',
        action='store_true',
        help='Validate configuration and exit'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='SecondShiftAugie Bot v1.0.0'
    )
    
    return parser.parse_args()


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    import logging
    
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # Reduce noise from some libraries
    logging.getLogger('nextcord').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def check_configuration():
    """Check configuration without starting the bot."""
    import os
    from dotenv import load_dotenv
    
    print("🔍 Checking configuration...")
    
    # Load environment variables
    load_dotenv()
    
    # Check required variables
    required_vars = {
        'BOT_TOKEN': 'Discord bot token',
        'CHANNEL_ID': 'Discord channel ID'
    }
    
    optional_vars = {
        'VOICE_CHANNEL_ID': 'Default voice channel ID',
        'SAVE_PATH': 'Audio save directory',
        'VOXCPM_MODEL_PATH': 'VoxCPM model path',
        'VOXCPM_PROMPT_WAV': 'Reference audio file',
        'VOXCPM_PROMPT_TEXT': 'Reference text file'
    }
    
    # Check required variables
    missing_required = []
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {description} - Set")
        else:
            print(f"❌ {var}: {description} - Missing")
            missing_required.append(var)
    
    # Check optional variables
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {description} - {value}")
        else:
            print(f"⚠️  {var}: {description} - Using default")
    
    # Check reference files
    prompt_wav = os.getenv('VOXCPM_PROMPT_WAV', 'assets/model.wav')
    prompt_text = os.getenv('VOXCPM_PROMPT_TEXT', 'assets/transcript.txt')
    
    if os.path.exists(prompt_wav):
        print(f"✅ Reference audio file found: {prompt_wav}")
    else:
        print(f"❌ Reference audio file missing: {prompt_wav}")
    
    if os.path.exists(prompt_text):
        print(f"✅ Reference text file found: {prompt_text}")
    else:
        print(f"❌ Reference text file missing: {prompt_text}")
    
    # Summary
    if missing_required:
        print(f"\n❌ Configuration check failed. Missing required variables: {missing_required}")
        print("Please set these in your .env file or environment variables.")
        return False
    else:
        print("\n✅ Configuration check passed!")
        return True


async def run_bot():
    """Run the bot application."""
    try:
        await main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    args = parse_arguments()
    
    # Set up logging
    setup_logging(args.verbose)
    
    # Check configuration if requested
    if args.check_config:
        success = check_configuration()
        sys.exit(0 if success else 1)
    
    # Print startup banner
    print("🤖 SecondShiftAugie Discord Bot")
    print("🎤 VoxCPM TTS Integration")
    print("=" * 40)
    
    # Handle Windows event loop policy
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run the bot
    asyncio.run(run_bot())