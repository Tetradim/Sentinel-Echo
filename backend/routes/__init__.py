"""
Routes package - Modular API endpoints
"""
from .health import router as health_router, bot_status, update_bot_status, get_bot_status, set_db as set_health_db
from .brokers import router as brokers_router, set_db as set_brokers_db
from .settings import router as settings_router, set_db as set_settings_db, check_and_trigger_shutdown
from .discord import router as discord_router, set_db as set_discord_db, set_discord_bot, get_discord_bot
from .profiles import router as profiles_router, set_db as set_profiles_db
from .trading import router as trading_router, set_db as set_trading_db
from .operator import router as operator_router, set_db as set_operator_db
from .sentinel_archive import router as sentinel_archive_router, set_db as set_sentinel_archive_db
from .bot_bus import router as bot_bus_router
from .pairing import router as pairing_router
# Advanced analytics routes
from .analytics import router as analytics_router


def init_routes(database):
    """Initialize all routes with database abstraction layer"""
    set_health_db(database)
    set_brokers_db(database)
    set_settings_db(database)
    set_discord_db(database)
    set_profiles_db(database)
    set_trading_db(database)
    set_operator_db(database)
    set_sentinel_archive_db(database)


__all__ = [
    'health_router',
    'brokers_router', 
    'settings_router',
    'discord_router',
    'profiles_router',
    'trading_router',
    'operator_router',
    'sentinel_archive_router',
    'bot_bus_router',
    'pairing_router',
    'analytics_router',
    'init_routes',
    'bot_status',
    'update_bot_status',
    'get_bot_status',
    'set_health_db',
    'set_discord_bot',
    'get_discord_bot',
    'check_and_trigger_shutdown'
]
