"""
Run script for the Trading Bot
Usage:
    python backend/run.py
    
Environment variables:
    DISCORD_BOT_TOKEN     - Your Discord bot token (required for Discord)
    DISCORD_CHANNEL_IDS   - Comma-separated channel IDs to listen on
    MONGO_URL            - MongoDB connection string
    DATABASE_PATH       - SQLite database path (default: tradebot.db)
    IBKR_GATEWAY_URL     - IBKR Gateway URL (default: https://localhost:5000)
    IBKR_ACCOUNT_ID     - IBKR account ID
    API_SECRET_KEY      - Secret key for API authentication
    HOST                - Host to bind to (default: 127.0.0.1)
    PORT                - Port to bind to (default: 8000)
    LOG_LEVEL           - Logging level (default: INFO)
"""
import os
import sys
import logging
from pathlib import Path

# Setup path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('tradebot.log', mode='a')
    ] if os.path.exists(SCRIPT_DIR) else []
)
logger = logging.getLogger(__name__)


def check_environment():
    """Validate required environment variables"""
    issues = []
    warnings = []
    
    # Required for full operation
    if not os.environ.get('DISCORD_BOT_TOKEN'):
        warnings.append("DISCORD_BOT_TOKEN not set - Discord bot will not start")
    if not os.environ.get('DISCORD_CHANNEL_IDS'):
        warnings.append("DISCORD_CHANNEL_IDS not set - Discord channels not configured")
    
    # Database check
    use_sqlite = os.environ.get('USE_SQLITE', 'true').lower() == 'true'
    if use_sqlite:
        db_path = os.environ.get('DATABASE_PATH', 'tradebot.db')
        if not os.path.exists(db_path) and os.path.dirname(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            logger.info(f"Created database directory: {os.path.dirname(db_path)}")
    else:
        if not os.environ.get('MONGO_URL'):
            warnings.append("MONGO_URL not set and SQLite not enabled")
    
    # Log environment status
    logger.info("=" * 50)
    logger.info("ENVIRONMENT CHECK")
    logger.info("=" * 50)
    
    for w in warnings:
        logger.warning(w)
    
    if warnings:
        logger.info("The bot will run in limited mode until environment is configured")
    
    return len(issues) == 0


def main():
    """Main entry point"""
    import uvicorn
    
    logger.info("=" * 60)
    logger.info("TRADING BOT STARTING")
    logger.info("=" * 60)
    
    # Check environment
    check_environment()

    # Configure uvicorn
    config = uvicorn.Config(
        "backend.server:app",
        host=os.environ.get('HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', 8000)),
        reload=os.environ.get('RELOAD', 'false').lower() == 'true',
        log_level=os.environ.get('LOG_LEVEL', 'info').lower(),
        lifespan="on",
    )

    # Run server
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
