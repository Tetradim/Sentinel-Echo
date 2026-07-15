"""Trading Bot Main Entry Point.

Run with ``python -m backend`` or ``python backend/run.py``.
"""
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_environment():
    optional = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'tradebot',
        'DATABASE_PATH': 'tradebot.db',
        'DISCORD_BOT_TOKEN': '',
        'DISCORD_CHANNEL_IDS': '',
        'IBKR_GATEWAY_URL': 'https://localhost:5000',
        'IBKR_ACCOUNT_ID': '',
    }
    return optional


def main():
    import uvicorn

    load_environment()
    uvicorn.run(
        "backend.runtime_app:app",
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 8000)),
        reload=os.environ.get('RELOAD', 'false').lower() == 'true',
        log_level="info",
        lifespan="on",
    )


if __name__ == "__main__":
    main()
