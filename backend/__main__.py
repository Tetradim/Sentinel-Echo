"""
Trading Bot Main Entry Point
Run with: python -m backend
Or: python backend/run.py
"""
import os
import sys
import logging
import asyncio
import signal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from server import app, init_discord_bot, shutdown_bot
from database import init_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_environment():
    """Load required environment variables"""
    required = []
    optional = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'tradebot',
        'DATABASE_PATH': 'tradebot.db',
        'DISCORD_BOT_TOKEN': '',
        'DISCORD_CHANNEL_IDS': '',
        'IBKR_GATEWAY_URL': 'https://localhost:5000',
        'IBKR_ACCOUNT_ID': '',
    }
    
    # Check required
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        logger.warning(f"Missing environment variables: {missing}")
    
    return optional


async def startup():
    """Initialize all services"""
    logger.info("Starting Trading Bot...")
    
    # Initialize database
    init_database()
    logger.info("Database initialized")
    
    # Initialize Discord bot if token is set
    token = os.environ.get('DISCORD_BOT_TOKEN', '')
    channel_ids = os.environ.get('DISCORD_CHANNEL_IDS', '').split(',')
    channel_ids = [c.strip() for c in channel_ids if c.strip()]
    
    if token and channel_ids:
        logger.info(f"Initializing Discord bot for channels: {channel_ids}")
        await init_discord_bot(token, channel_ids)
    else:
        logger.warning("Discord bot not configured - set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_IDS")
    
    logger.info("Trading Bot started successfully")
    return app


async def shutdown():
    """Cleanup on shutdown"""
    logger.info("Shutting down Trading Bot...")
    await shutdown_bot()
    logger.info("Trading Bot stopped")


def main():
    """Main entry point"""
    import uvicorn
    
    load_environment()
    
    # Run the FastAPI server
    uvicorn.run(
        "backend.server:app",
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 8000)),
        reload=os.environ.get('RELOAD', 'false').lower() == 'true',
        log_level="info"
    )


if __name__ == "__main__":
    main()
