"""
Database Abstraction Layer
Provides a unified async interface for both MongoDB (server) and SQLite (desktop).

Fixes applied in this version:
  C3  -- SQLiteDatabase now uses aiosqlite throughout; no blocking sqlite3 calls.
  C16 -- Loss counter increments are atomic DB-level UPDATE statements.
  M1  -- update_settings protected by asyncio.Lock.
  M2  -- get_portfolio_summary uses SQL/aggregation pipeline; no large in-memory lists.
  M6  -- Runtime counters/flags live in a dedicated table/collection, not the config blob.
"""
import os
import json
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

USE_SQLITE = os.environ.get('USE_SQLITE', 'false').lower() == 'true'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_runtime_state() -> Dict[str, Any]:
    return {
        'consecutive_losses': 0,
        'daily_losses': 0,
        'daily_loss_amount': 0.0,
        'last_loss_reset_date': '',
        'shutdown_triggered': False,
        'shutdown_reason': '',
        'auto_trading_enabled': False,
    }


def _default_settings() -> Dict[str, Any]:
    """Pure config -- no runtime counters or transient flags."""
    return {
        'id': 'main_settings',
        'discord_token': '',
        'discord_channel_ids': [],
        'source_overrides': {},
        'active_broker': 'ibkr',
        'broker_configs': {},
        'auto_trading_enabled': False,
        'premium_buffer_enabled': False,
        'premium_buffer_amount': 10.0,
        'default_quantity': 1,
        'simulation_mode': True,
        'max_position_size': 1000.0,
        'risk_per_trade': 1.0,
        'max_drawdown_percent': 20.0,
        'max_positions_per_ticker': 3,
        'max_positions_per_sector': 3,
        'averaging_down_enabled': False,
        'averaging_down_threshold': 10.0,
        'averaging_down_percentage': 25.0,
        'averaging_down_max_buys': 3,
        'take_profit_enabled': False,
        'take_profit_percentage': 50.0,
        'bracket_order_enabled': False,
        'stop_loss_enabled': False,
        'stop_loss_percentage': 25.0,
        'stop_loss_order_type': 'market',
        'trailing_stop_enabled': False,
        'trailing_stop_type': 'percent',
        'trailing_stop_percent': 10.0,
        'trailing_stop_cents': 50.0,
        'trailing_hours': 4.0,
        'auto_shutdown_enabled': False,
        'max_consecutive_losses': 3,
        'max_daily_losses': 5,
        'max_daily_loss_amount': 500.0,
    }


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class DatabaseInterface(ABC):

    @abstractmethod
    async def get_settings(self) -> Dict[str, Any]: pass

    @abstractmethod
    async def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]: pass

    # M6 -- runtime state separate from config
    @abstractmethod
    async def get_runtime_state(self) -> Dict[str, Any]: pass

    @abstractmethod
    async def update_runtime_state(self, updates: Dict[str, Any]) -> Dict[str, Any]: pass

    # C16 -- atomic counter operations
    @abstractmethod
    async def increment_loss_counters(self, loss_amount: float) -> Dict[str, Any]: pass

    @abstractmethod
    async def reset_loss_counters(self) -> Dict[str, Any]: pass

    @abstractmethod
    async def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]: pass

    @abstractmethod
    async def insert_alert(self, alert: Dict[str, Any]) -> str: pass

    @abstractmethod
    async def update_alert(self, alert_id: str, updates: Dict[str, Any]): pass

    @abstractmethod
    async def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]: pass

    @abstractmethod
    async def insert_trade(self, trade: Dict[str, Any]) -> str: pass

    @abstractmethod
    async def update_trade(self, trade_id: str, updates: Dict[str, Any]): pass

    @abstractmethod
    async def get_positions(self, status: Optional[str] = None) -> List[Dict[str, Any]]: pass

    @abstractmethod
    async def get_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]: pass

    @abstractmethod
    async def insert_position(self, position: Dict[str, Any]) -> str: pass

    @abstractmethod
    async def update_position(self, position_id: str, updates: Dict[str, Any]): pass

    @abstractmethod
    async def get_profiles(self) -> List[Dict[str, Any]]: pass

    @abstractmethod
    async def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]: pass

    @abstractmethod
    async def insert_profile(self, profile: Dict[str, Any]) -> str: pass

    @abstractmethod
    async def update_profile(self, profile_id: str, updates: Dict[str, Any]): pass

    @abstractmethod
    async def delete_profile(self, profile_id: str) -> bool: pass

    @abstractmethod
    async def count_profiles(self) -> int: pass

    @abstractmethod
    async def set_all_profiles_inactive(self): pass

    @abstractmethod
    async def get_discord_patterns(self) -> Optional[Dict[str, Any]]: pass

    @abstractmethod
    async def update_discord_patterns(self, patterns: Dict[str, Any]): pass

    @abstractmethod
    async def get_portfolio_summary(self) -> Dict[str, Any]: pass


# ---------------------------------------------------------------------------
# MongoDB implementation
# ---------------------------------------------------------------------------

class MongoDBDatabase(DatabaseInterface):

    def __init__(self, db):
        self.db = db
        self._settings_lock = asyncio.Lock()

    async def get_settings(self) -> Dict[str, Any]:
        doc = await self.db.settings.find_one({'id': 'main_settings'}, {'_id': 0})
        return doc or {}

    async def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        async with self._settings_lock:  # M1
            if updates:
                await self.db.settings.update_one(
                    {'id': 'main_settings'}, {'$set': updates}, upsert=True
                )
            doc = await self.db.settings.find_one({'id': 'main_settings'}, {'_id': 0})
            return doc or {}

    async def get_runtime_state(self) -> Dict[str, Any]:
        doc = await self.db.runtime_state.find_one({'id': 'runtime'}, {'_id': 0})
        return doc or _default_runtime_state()

    async def update_runtime_state(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if updates:
            await self.db.runtime_state.update_one(
                {'id': 'runtime'}, {'$set': updates}, upsert=True
            )
        return await self.get_runtime_state()

    async def increment_loss_counters(self, loss_amount: float) -> Dict[str, Any]:
        # C16: MongoDB $inc is atomic
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        doc = await self.db.runtime_state.find_one_and_update(
            {'id': 'runtime'},
            {
                '$inc': {
                    'consecutive_losses': 1,
                    'daily_losses': 1,
                    'daily_loss_amount': loss_amount,
                },
                '$set': {'last_loss_reset_date': today},
            },
            upsert=True,
            return_document=True,
        )
        return doc or await self.get_runtime_state()

    async def reset_loss_counters(self) -> Dict[str, Any]:
        return await self.update_runtime_state({
            'consecutive_losses': 0,
            'daily_losses': 0,
            'daily_loss_amount': 0.0,
            'shutdown_triggered': False,
            'shutdown_reason': '',
        })

    async def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        alerts = await self.db.alerts.find().sort('timestamp', -1).limit(limit).to_list(length=limit)
        for a in alerts:
            a.pop('_id', None)
        return alerts

    async def insert_alert(self, alert: Dict[str, Any]) -> str:
        await self.db.alerts.insert_one(alert)
        return alert.get('id', '')

    async def update_alert(self, alert_id: str, updates: Dict[str, Any]):
        await self.db.alerts.update_one({'id': alert_id}, {'$set': updates})

    async def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        trades = await self.db.trades.find().sort('created_at', -1).limit(limit).to_list(length=limit)
        for t in trades:
            t.pop('_id', None)
        return trades

    async def insert_trade(self, trade: Dict[str, Any]) -> str:
        await self.db.trades.insert_one(trade)
        return trade.get('id', '')

    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        await self.db.trades.update_one({'id': trade_id}, {'$set': updates})

    async def get_positions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        q = {'status': status} if status else {}
        positions = await self.db.positions.find(q).sort('opened_at', -1).to_list(length=100)
        for p in positions:
            p.pop('_id', None)
        return positions

    async def get_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.positions.find_one({'id': position_id}, {'_id': 0})

    async def insert_position(self, position: Dict[str, Any]) -> str:
        await self.db.positions.insert_one(position)
        return position.get('id', '')

    async def update_position(self, position_id: str, updates: Dict[str, Any]):
        if '$set' in updates or '$push' in updates:
            await self.db.positions.update_one({'id': position_id}, updates)
        else:
            await self.db.positions.update_one({'id': position_id}, {'$set': updates})

    async def get_profiles(self) -> List[Dict[str, Any]]:
        return await self.db.profiles.find({}, {'_id': 0}).to_list(100)

    async def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.profiles.find_one({'id': profile_id}, {'_id': 0})

    async def insert_profile(self, profile: Dict[str, Any]) -> str:
        await self.db.profiles.insert_one(profile)
        return profile.get('id', '')

    async def update_profile(self, profile_id: str, updates: Dict[str, Any]):
        await self.db.profiles.update_one({'id': profile_id}, {'$set': updates})

    async def delete_profile(self, profile_id: str) -> bool:
        result = await self.db.profiles.delete_one({'id': profile_id})
        return result.deleted_count > 0

    async def count_profiles(self) -> int:
        return await self.db.profiles.count_documents({})

    async def set_all_profiles_inactive(self):
        await self.db.profiles.update_many({}, {'$set': {'is_active': False}})

    async def get_discord_patterns(self) -> Optional[Dict[str, Any]]:
        return await self.db.discord_patterns.find_one({'id': 'main_patterns'}, {'_id': 0})

    async def update_discord_patterns(self, patterns: Dict[str, Any]):
        patterns['id'] = 'main_patterns'
        await self.db.discord_patterns.update_one(
            {'id': 'main_patterns'}, {'$set': patterns}, upsert=True
        )

    async def get_portfolio_summary(self) -> Dict[str, Any]:
        # M2: aggregation pipeline -- no Python-level loops over 1000 rows
        trade_agg = await self.db.trades.aggregate([
            {'$match': {'side': 'SELL', 'status': {'$in': ['executed', 'simulated']}}},
            {'$group': {
                '_id': None,
                'total_realized': {'$sum': '$realized_pnl'},
                'total_trades': {'$sum': 1},
                'winning_trades': {'$sum': {'$cond': [{'$gt': ['$realized_pnl', 0]}, 1, 0]}},
                'losing_trades': {'$sum': {'$cond': [{'$lt': ['$realized_pnl', 0]}, 1, 0]}},
                'best_trade': {'$max': '$realized_pnl'},
                'worst_trade': {'$min': '$realized_pnl'},
            }},
        ]).to_list(1)
        pos_agg = await self.db.positions.aggregate([
            {'$match': {'status': {'$in': ['open', 'partial']}}},
            {'$group': {
                '_id': None,
                'total_unrealized': {'$sum': '$unrealized_pnl'},
                'open_positions': {'$sum': 1},
            }},
        ]).to_list(1)
        closed_agg = await self.db.positions.aggregate([
            {'$match': {'status': 'closed'}},
            {'$count': 'closed_positions'},
        ]).to_list(1)

        t = trade_agg[0] if trade_agg else {}
        p = pos_agg[0] if pos_agg else {}
        c = closed_agg[0] if closed_agg else {}
        total_trades = t.get('total_trades', 0)
        winning_trades = t.get('winning_trades', 0)
        losing_trades = t.get('losing_trades', 0)
        return {
            'total_positions': p.get('open_positions', 0),
            'open_positions': p.get('open_positions', 0),
            'closed_positions': c.get('closed_positions', 0),
            'total_realized_pnl': t.get('total_realized', 0.0),
            'total_unrealized_pnl': p.get('total_unrealized', 0.0),
            'total_pnl': t.get('total_realized', 0.0) + p.get('total_unrealized', 0.0),
            'win_rate': (winning_trades / total_trades * 100) if total_trades else 0.0,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'best_trade': t.get('best_trade', 0.0) or 0.0,
            'worst_trade': t.get('worst_trade', 0.0) or 0.0,
            'average_pnl': (t.get('total_realized', 0.0) / total_trades) if total_trades else 0.0,
        }


# ---------------------------------------------------------------------------
# SQLite implementation  (C3: fully async via aiosqlite)
# ---------------------------------------------------------------------------

_INIT_SQL = '''
CREATE TABLE IF NOT EXISTS settings (
    id   TEXT PRIMARY KEY DEFAULT 'main_settings',
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_state (
    id                   TEXT    PRIMARY KEY DEFAULT 'runtime',
    consecutive_losses   INTEGER NOT NULL DEFAULT 0,
    daily_losses         INTEGER NOT NULL DEFAULT 0,
    daily_loss_amount    REAL    NOT NULL DEFAULT 0.0,
    last_loss_reset_date TEXT    NOT NULL DEFAULT '',
    shutdown_triggered   INTEGER NOT NULL DEFAULT 0,
    shutdown_reason      TEXT    NOT NULL DEFAULT '',
    auto_trading_enabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
    id        TEXT PRIMARY KEY,
    timestamp TEXT,
    data      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id           TEXT    PRIMARY KEY,
    created_at   TEXT,
    side         TEXT    DEFAULT '',
    status       TEXT    DEFAULT '',
    realized_pnl REAL    DEFAULT 0.0,
    data         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id             TEXT PRIMARY KEY,
    status         TEXT DEFAULT 'open',
    opened_at      TEXT,
    unrealized_pnl REAL DEFAULT 0.0,
    data           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id        TEXT    PRIMARY KEY,
    is_active INTEGER DEFAULT 0,
    data      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_patterns (
    id   TEXT PRIMARY KEY DEFAULT 'main_patterns',
    data TEXT NOT NULL
);
'''


class SQLiteDatabase(DatabaseInterface):
    """
    C3:  All I/O goes through aiosqlite -- no blocking sqlite3 calls.
    C16: increment_loss_counters is a single atomic UPDATE.
    M1:  update_settings protected by asyncio.Lock.
    M2:  get_portfolio_summary uses SQL SUM/COUNT/CASE.
    M6:  runtime_state is a separate table, not embedded in the settings blob.
    """

    def __init__(self, db_path: str = 'tradebot.db'):
        self.db_path = db_path
        self._settings_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialised = False

    async def _ensure_ready(self):
        if self._initialised:
            return
        async with self._init_lock:
            if self._initialised:
                return
            await self._init_db()
            self._initialised = True

    async def _init_db(self):
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.executescript(_INIT_SQL)
            # Seed default settings
            async with conn.execute(
                'SELECT id FROM settings WHERE id = ?', ('main_settings',)
            ) as cur:
                if not await cur.fetchone():
                    await conn.execute(
                        'INSERT INTO settings (id, data) VALUES (?, ?)',
                        ('main_settings', json.dumps(_default_settings()))
                    )
            # Seed default runtime state
            async with conn.execute(
                'SELECT id FROM runtime_state WHERE id = ?', ('runtime',)
            ) as cur:
                if not await cur.fetchone():
                    await conn.execute(
                        "INSERT INTO runtime_state (id) VALUES (?)", ('runtime',)
                    )
            await conn.commit()

    # -- Settings -----------------------------------------------------------

    async def get_settings(self) -> Dict[str, Any]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM settings WHERE id = ?', ('main_settings',)
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row['data']) if row else _default_settings()

    async def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_ready()
        import aiosqlite
        async with self._settings_lock:  # M1
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    'SELECT data FROM settings WHERE id = ?', ('main_settings',)
                ) as cur:
                    row = await cur.fetchone()
                settings = json.loads(row['data']) if row else _default_settings()
                settings.update(updates)
                await conn.execute(
                    'INSERT OR REPLACE INTO settings (id, data) VALUES (?, ?)',
                    ('main_settings', json.dumps(settings))
                )
                await conn.commit()
        return settings

    # -- Runtime state (M6) ------------------------------------------------

    def _row_to_runtime(self, row) -> Dict[str, Any]:
        return {
            'consecutive_losses': row['consecutive_losses'],
            'daily_losses': row['daily_losses'],
            'daily_loss_amount': row['daily_loss_amount'],
            'last_loss_reset_date': row['last_loss_reset_date'],
            'shutdown_triggered': bool(row['shutdown_triggered']),
            'shutdown_reason': row['shutdown_reason'],
            'auto_trading_enabled': bool(row['auto_trading_enabled']),
        }

    async def get_runtime_state(self) -> Dict[str, Any]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT * FROM runtime_state WHERE id = ?', ('runtime',)
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_runtime(row) if row else _default_runtime_state()

    async def update_runtime_state(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_ready()
        import aiosqlite
        allowed = {
            'consecutive_losses', 'daily_losses', 'daily_loss_amount',
            'last_loss_reset_date', 'shutdown_triggered', 'shutdown_reason',
            'auto_trading_enabled',
        }
        cols = {k: v for k, v in updates.items() if k in allowed}
        if not cols:
            return await self.get_runtime_state()
        set_clause = ', '.join(f'{k} = ?' for k in cols)
        values = list(cols.values()) + ['runtime']
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                f'UPDATE runtime_state SET {set_clause} WHERE id = ?', values
            )
            await conn.commit()
        return await self.get_runtime_state()

    async def increment_loss_counters(self, loss_amount: float) -> Dict[str, Any]:
        """C16: single atomic UPDATE -- no read-modify-write race."""
        await self._ensure_ready()
        import aiosqlite
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(
                '''UPDATE runtime_state
                   SET consecutive_losses   = consecutive_losses + 1,
                       daily_losses         = daily_losses + 1,
                       daily_loss_amount    = daily_loss_amount + ?,
                       last_loss_reset_date = ?
                   WHERE id = ?''',
                (loss_amount, today, 'runtime')
            )
            await conn.commit()
            async with conn.execute(
                'SELECT * FROM runtime_state WHERE id = ?', ('runtime',)
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_runtime(row) if row else _default_runtime_state()

    async def reset_loss_counters(self) -> Dict[str, Any]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """UPDATE runtime_state
                   SET consecutive_losses = 0,
                       daily_losses       = 0,
                       daily_loss_amount  = 0.0,
                       shutdown_triggered = 0,
                       shutdown_reason    = ''
                   WHERE id = ?""",
                ('runtime',)
            )
            await conn.commit()
        return await self.get_runtime_state()

    # -- Alerts ------------------------------------------------------------

    async def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM alerts ORDER BY timestamp DESC LIMIT ?', (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [json.loads(r['data']) for r in rows]

    async def insert_alert(self, alert: Dict[str, Any]) -> str:
        await self._ensure_ready()
        import aiosqlite
        ts = alert.get('timestamp', datetime.now(timezone.utc).isoformat())
        if hasattr(ts, 'isoformat'):
            ts = ts.isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                'INSERT INTO alerts (id, timestamp, data) VALUES (?, ?, ?)',
                (alert.get('id'), ts, json.dumps(alert))
            )
            await conn.commit()
        return alert.get('id', '')

    async def update_alert(self, alert_id: str, updates: Dict[str, Any]):
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM alerts WHERE id = ?', (alert_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise ValueError(f'Alert not found: {alert_id}')
            alert = json.loads(row['data'])
            alert.update(updates)
            await conn.execute(
                'UPDATE alerts SET data = ? WHERE id = ?', (json.dumps(alert), alert_id)
            )
            await conn.commit()

    # -- Trades ------------------------------------------------------------

    async def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM trades ORDER BY created_at DESC LIMIT ?', (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [json.loads(r['data']) for r in rows]

    async def insert_trade(self, trade: Dict[str, Any]) -> str:
        await self._ensure_ready()
        import aiosqlite
        created_at = trade.get('created_at', datetime.now(timezone.utc).isoformat())
        if hasattr(created_at, 'isoformat'):
            created_at = created_at.isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                '''INSERT INTO trades (id, created_at, side, status, realized_pnl, data)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (
                    trade.get('id'), created_at,
                    trade.get('side', ''), trade.get('status', ''),
                    float(trade.get('realized_pnl', 0.0)),
                    json.dumps(trade, default=str),
                )
            )
            await conn.commit()
        return trade.get('id', '')

    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM trades WHERE id = ?', (trade_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                trade = json.loads(row['data'])
                trade.update(updates)
                await conn.execute(
                    '''UPDATE trades
                       SET side = ?, status = ?, realized_pnl = ?, data = ?
                       WHERE id = ?''',
                    (
                        trade.get('side', ''), trade.get('status', ''),
                        float(trade.get('realized_pnl', 0.0)),
                        json.dumps(trade, default=str), trade_id,
                    )
                )
                await conn.commit()

    # -- Positions ---------------------------------------------------------

    async def get_positions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            q = ('SELECT data FROM positions WHERE status = ? ORDER BY opened_at DESC', (status,)) \
                if status else ('SELECT data FROM positions ORDER BY opened_at DESC', ())
            async with conn.execute(*q) as cur:
                rows = await cur.fetchall()
        return [json.loads(r['data']) for r in rows]

    async def get_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM positions WHERE id = ?', (position_id,)
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row['data']) if row else None

    async def insert_position(self, position: Dict[str, Any]) -> str:
        await self._ensure_ready()
        import aiosqlite
        opened_at = position.get('opened_at', datetime.now(timezone.utc).isoformat())
        if hasattr(opened_at, 'isoformat'):
            opened_at = opened_at.isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                '''INSERT INTO positions (id, status, opened_at, unrealized_pnl, data)
                   VALUES (?, ?, ?, ?, ?)''',
                (
                    position.get('id'), position.get('status', 'open'), opened_at,
                    float(position.get('unrealized_pnl', 0.0)),
                    json.dumps(position, default=str),
                )
            )
            await conn.commit()
        return position.get('id', '')

    async def update_position(self, position_id: str, updates: Dict[str, Any]):
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM positions WHERE id = ?', (position_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                pos = json.loads(row['data'])
                if '$set' in updates:
                    pos.update(updates['$set'])
                if '$push' in updates:
                    for k, v in updates['$push'].items():
                        pos.setdefault(k, []).append(v)
                if '$set' not in updates and '$push' not in updates:
                    pos.update(updates)
                await conn.execute(
                    '''UPDATE positions
                       SET status = ?, unrealized_pnl = ?, data = ?
                       WHERE id = ?''',
                    (
                        pos.get('status', 'open'),
                        float(pos.get('unrealized_pnl', 0.0)),
                        json.dumps(pos, default=str), position_id,
                    )
                )
                await conn.commit()

    # -- Profiles ----------------------------------------------------------

    async def get_profiles(self) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT data FROM profiles') as cur:
                rows = await cur.fetchall()
        return [json.loads(r['data']) for r in rows]

    async def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM profiles WHERE id = ?', (profile_id,)
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row['data']) if row else None

    async def insert_profile(self, profile: Dict[str, Any]) -> str:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                'INSERT INTO profiles (id, is_active, data) VALUES (?, ?, ?)',
                (profile.get('id'), 1 if profile.get('is_active') else 0, json.dumps(profile))
            )
            await conn.commit()
        return profile.get('id', '')

    async def update_profile(self, profile_id: str, updates: Dict[str, Any]):
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM profiles WHERE id = ?', (profile_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                profile = json.loads(row['data'])
                profile.update(updates)
                await conn.execute(
                    'UPDATE profiles SET is_active = ?, data = ? WHERE id = ?',
                    (1 if profile.get('is_active') else 0, json.dumps(profile), profile_id)
                )
                await conn.commit()

    async def delete_profile(self, profile_id: str) -> bool:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('DELETE FROM profiles WHERE id = ?', (profile_id,))
            deleted = conn.total_changes > 0
            await conn.commit()
        return deleted

    async def count_profiles(self) -> int:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT COUNT(*) AS cnt FROM profiles') as cur:
                row = await cur.fetchone()
        return row['cnt'] if row else 0

    async def set_all_profiles_inactive(self):
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('UPDATE profiles SET is_active = 0')
            await conn.commit()

    # -- Discord Patterns --------------------------------------------------

    async def get_discord_patterns(self) -> Optional[Dict[str, Any]]:
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                'SELECT data FROM discord_patterns WHERE id = ?', ('main_patterns',)
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row['data']) if row else None

    async def update_discord_patterns(self, patterns: Dict[str, Any]):
        await self._ensure_ready()
        import aiosqlite
        patterns['id'] = 'main_patterns'
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                'INSERT OR REPLACE INTO discord_patterns (id, data) VALUES (?, ?)',
                ('main_patterns', json.dumps(patterns))
            )
            await conn.commit()

    # -- Portfolio summary (M2) --------------------------------------------

    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """SQL aggregation -- never loads large result sets into Python memory."""
        await self._ensure_ready()
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                '''SELECT
                       COUNT(*)                                                  AS total_trades,
                       COALESCE(SUM(realized_pnl), 0.0)                         AS total_realized,
                       COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END), 0) AS winning_trades,
                       COALESCE(SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END), 0) AS losing_trades,
                       COALESCE(MAX(realized_pnl), 0.0) AS best_trade,
                       COALESCE(MIN(realized_pnl), 0.0) AS worst_trade
                   FROM trades
                   WHERE side = 'SELL' AND status IN ('executed', 'simulated')'''
            ) as cur:
                tr = await cur.fetchone()
            async with conn.execute(
                '''SELECT
                       COUNT(*)                               AS open_positions,
                       COALESCE(SUM(unrealized_pnl), 0.0)    AS total_unrealized
                   FROM positions
                   WHERE status IN ('open', 'partial')'''
            ) as cur:
                pr = await cur.fetchone()
            async with conn.execute(
                '''SELECT COUNT(*) AS closed_positions FROM positions WHERE status = 'closed' '''
            ) as cur:
                cr = await cur.fetchone()

        total_trades = tr['total_trades'] if tr else 0
        winning_trades = tr['winning_trades'] if tr else 0
        losing_trades = tr['losing_trades'] if tr else 0
        total_realized = tr['total_realized'] if tr else 0.0
        open_positions = pr['open_positions'] if pr else 0
        closed_positions = cr['closed_positions'] if cr else 0
        total_unrealized = pr['total_unrealized'] if pr else 0.0
        return {
            'total_positions': open_positions,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'total_realized_pnl': total_realized,
            'total_unrealized_pnl': total_unrealized,
            'total_pnl': total_realized + total_unrealized,
            'win_rate': (winning_trades / total_trades * 100) if total_trades else 0.0,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'best_trade': tr['best_trade'] if tr else 0.0,
            'worst_trade': tr['worst_trade'] if tr else 0.0,
            'average_pnl': (total_realized / total_trades) if total_trades else 0.0,
        }


# ---------------------------------------------------------------------------
# Factory / globals
# ---------------------------------------------------------------------------

def get_database(mongo_db=None, sqlite_path: str = 'tradebot.db') -> DatabaseInterface:
    if USE_SQLITE:
        return SQLiteDatabase(sqlite_path)
    if mongo_db is not None:
        return MongoDBDatabase(mongo_db)
    raise ValueError('MongoDB instance required when USE_SQLITE is false')


_db_instance: Optional[DatabaseInterface] = None


def init_database(mongo_db=None, sqlite_path: str = 'tradebot.db') -> DatabaseInterface:
    global _db_instance
    _db_instance = get_database(mongo_db, sqlite_path)
    return _db_instance


class DatabaseNotInitializedError(RuntimeError):
    pass


def get_db() -> DatabaseInterface:
    if _db_instance is None:
        raise DatabaseNotInitializedError('Call init_database() before get_db()')
    return _db_instance
