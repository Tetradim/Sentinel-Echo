"""Production app wrapper that adds durable live-order submission recovery."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

try:
    from .server import app
    from .database import get_db
    from .fill_monitor import resume_pending_fill_monitors, stop_fill_monitors
    from . import live_broker_clients_patch as _live_broker_clients_patch  # noqa: F401
    from .live_order_execution_runtime import recover_journalled_orders
    from . import live_order_execution_runtime as _live_order_execution_runtime  # noqa: F401
    from . import pre_task_order_persistence as _pre_task_order_persistence  # noqa: F401
    from . import live_trade_state_patch as _live_trade_state_patch  # noqa: F401
except ImportError:  # direct backend path execution
    from server import app
    from database import get_db
    from fill_monitor import resume_pending_fill_monitors, stop_fill_monitors
    import live_broker_clients_patch as _live_broker_clients_patch  # noqa: F401
    from live_order_execution_runtime import recover_journalled_orders
    import live_order_execution_runtime as _live_order_execution_runtime  # noqa: F401
    import pre_task_order_persistence as _pre_task_order_persistence  # noqa: F401
    import live_trade_state_patch as _live_trade_state_patch  # noqa: F401


logger = logging.getLogger(__name__)
_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _live_recovery_lifespan(application):
    async with _original_lifespan(application):
        db = get_db()
        settings = await db.get_settings()
        recovered = await recover_journalled_orders(db, settings)
        if recovered:
            logger.critical(
                "Reconstructed %s live broker order(s) that were missing from the primary trade ledger",
                recovered,
            )
        resumed = await resume_pending_fill_monitors(db, settings)
        if resumed:
            logger.warning("Resumed %s non-terminal broker order monitor(s)", resumed)
        try:
            yield
        finally:
            await stop_fill_monitors()


app.router.lifespan_context = _live_recovery_lifespan
