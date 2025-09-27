#!/usr/bin/env python3
"""
Entry point for the VoxCPM-integrated SecondShiftAugie bot.

This script runs the new VoxCPM TTS-enabled version of the bot.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('voxcpm_bot.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the VoxCPM bot."""
    try:
        logger.info("Starting VoxCPM SecondShiftAugie bot...")
        
        # Import the main bot class
        from main import SecondShiftAugieBot
        
        # Create and run the bot
        bot_app = SecondShiftAugieBot()
        await bot_app.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    # Handle Windows event loop policy
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run the application
    asyncio.run(main())