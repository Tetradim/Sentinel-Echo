"""Production app wrapper that adds durable live-order and position recovery."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

try:
    from . import server as _server
    from .database import get_db
    from .fill_monitor import resume_pending_fill_monitors, stop_fill_monitors
    from . import live_broker_clients_patch as _live_broker_clients_patch  # noqa: F401
    from .live_order_execution_runtime import recover_journalled_orders
    from . import live_order_execution_runtime as _live_order_execution_runtime  # noqa: F401
    from . import option_execution_quote_patch as _option_execution_quote_patch  # noqa: F401
    from . import option_broker_inventory_patch as _option_broker_inventory_patch  # noqa: F401
    from . import option_order_expiry_patch as _option_order_expiry_patch  # noqa: F401
    from .broker_inventory_reconciliation import reconcile_broker_inventory
    from . import journal_fill_lifecycle_patch as _journal_fill_lifecycle_patch  # noqa: F401
    from . import pre_task_order_persistence as _pre_task_order_persistence  # noqa: F401
    from . import live_trade_state_patch as _live_trade_state_patch  # noqa: F401
    from .option_position_supervisor import (
        start_position_supervisor,
        stop_position_supervisor,
    )
    from . import explicit_exit_continuation_patch as _explicit_exit_continuation_patch  # noqa: F401
except ImportError:  # direct backend path execution
    import server as _server
    from database import get_db
    from fill_monitor import resume_pending_fill_monitors, stop_fill_monitors
    import live_broker_clients_patch as _live_broker_clients_patch  # noqa: F401
    from live_order_execution_runtime import recover_journalled_orders
    import live_order_execution_runtime as _live_order_execution_runtime  # noqa: F401
    import option_execution_quote_patch as _option_execution_quote_patch  # noqa: F401
    import option_broker_inventory_patch as _option_broker_inventory_patch  # noqa: F401
    import option_order_expiry_patch as _option_order_expiry_patch  # noqa: F401
    from broker_inventory_reconciliation import reconcile_broker_inventory
    import journal_fill_lifecycle_patch as _journal_fill_lifecycle_patch  # noqa: F401
    import pre_task_order_persistence as _pre_task_order_persistence  # noqa: F401
    import live_trade_state_patch as _live_trade_state_patch  # noqa: F401
    from option_position_supervisor import (
        start_position_supervisor,
        stop_position_supervisor,
    )
    import explicit_exit_continuation_patch as _explicit_exit_continuation_patch  # noqa: F401


app = _server.app
logger = logging.getLogger(__name__)
_original_lifespan = app.router.lifespan_context
_original_init_discord_bot = _server.init_discord_bot


@asynccontextmanager
async def _live_recovery_lifespan(application):
    deferred_discord: dict = {}

    async def _defer_discord_start(token, channel_ids):
        deferred_discord["token"] = token
        deferred_discord["channel_ids"] = channel_ids
        logger.warning(
            "Discord ingestion deferred until live broker orders and positions are recovered"
        )
        return None

    # The legacy lifespan initializes the DB and routes, then immediately starts
    # Discord before yielding. Temporarily replace that startup hook so recovery
    # and autonomous position supervision are active before any new alert can
    # submit another live order.
    _server.init_discord_bot = _defer_discord_start
    try:
        async with _original_lifespan(application):
            db = get_db()
            settings = await db.get_settings()

            inventory = await reconcile_broker_inventory(db, settings)
            if inventory.get("positions_imported") or inventory.get("positions_updated") or inventory.get("positions_closed") or inventory.get("orders_recovered"):
                logger.critical("Broker inventory reconciliation applied: %s", inventory)
            if inventory.get("errors"):
                logger.error("Broker inventory reconciliation incidents: %s", inventory["errors"])

            recovered = await recover_journalled_orders(db, settings)
            if recovered:
                logger.critical(
                    "Reconstructed %s live broker order(s) that were missing from the primary trade ledger",
                    recovered,
                )
            resumed = await resume_pending_fill_monitors(db, settings)
            if resumed:
                logger.warning("Resumed %s non-terminal broker order monitor(s)", resumed)
            start_position_supervisor(db)

            _server.init_discord_bot = _original_init_discord_bot
            if deferred_discord:
                await _original_init_discord_bot(
                    deferred_discord["token"],
                    deferred_discord["channel_ids"],
                )
            try:
                yield
            finally:
                await stop_position_supervisor()
                await stop_fill_monitors()
    finally:
        _server.init_discord_bot = _original_init_discord_bot


app.router.lifespan_context = _live_recovery_lifespan
