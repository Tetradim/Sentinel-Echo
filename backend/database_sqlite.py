"""
SQLite Database Layer for Desktop App
This module provides SQLite support as an alternative to MongoDB for the standalone desktop version.
"""
import json
import sqlite3
from datetime import datetime, timezone  # FIXED M7
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from database_paths import configured_database_path


DATABASE_PATH = configured_database_path()


def _json_default(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    raise TypeError(f'Object of type {value.__class__.__name__} is not JSON serializable')


def _json_dumps(data: Any) -> str:
    return json.dumps(data, default=_json_default)


def get_db_path():
    return DATABASE_PATH

@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize SQLite database with required tables"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id TEXT PRIMARY KEY DEFAULT 'main_settings',
                data TEXT NOT NULL
            )
        ''')
        
        # Alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                ticker TEXT,
                strike REAL,
                option_type TEXT,
                expiration TEXT,
                entry_price REAL,
                action TEXT,
                sell_percentage REAL,
                received_at TEXT,
                processed INTEGER DEFAULT 0,
                trade_executed INTEGER DEFAULT 0,
                raw_message TEXT,
                data TEXT
            )
        ''')
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                alert_id TEXT,
                ticker TEXT,
                strike REAL,
                option_type TEXT,
                expiration TEXT,
                entry_price REAL,
                exit_price REAL,
                current_price REAL,
                quantity INTEGER,
                status TEXT,
                broker TEXT,
                executed_at TEXT,
                closed_at TEXT,
                simulated INTEGER DEFAULT 0,
                realized_pnl REAL,
                unrealized_pnl REAL,
                data TEXT,
                FOREIGN KEY (alert_id) REFERENCES alerts(id)
            )
        ''')
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                trade_id TEXT,
                ticker TEXT,
                strike REAL,
                option_type TEXT,
                expiration TEXT,
                entry_price REAL,
                current_price REAL,
                highest_price REAL,
                quantity INTEGER,
                average_down_count INTEGER DEFAULT 0,
                initial_entry_price REAL,
                data TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        ''')
        
        # Broker configs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broker_configs (
                broker_id TEXT PRIMARY KEY,
                config TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        
        # Initialize default settings if not exists
        cursor.execute('SELECT id FROM settings WHERE id = ?', ('main_settings',))
        if not cursor.fetchone():
            default_settings = {
                'auto_trading_enabled': True,
                'sell_alert_listening_enabled': True,
                'active_broker': 'alpaca',
                'source_overrides': {},
                'chrome_bridge_require_source_override': True,
                'default_quantity': 1,
                'simulation_mode': True,
                'max_position_size': 1000.0,
                'risk_per_trade': 1.0,
                'max_drawdown_percent': 20.0,
                'max_positions_per_ticker': 3,
                'max_positions_per_sector': 3,
                'averaging_down_enabled': False,
                'price_drop_threshold': 10.0,
                'buy_percentage': 25.0,
                'max_average_downs': 3,
                'take_profit_enabled': False,
                'take_profit_percentage': 50.0,
                'stop_loss_enabled': False,
                'stop_loss_percentage': 25.0,
                'bracket_order_enabled': False,
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
                'consecutive_losses': 0,
                'daily_losses': 0,
                'daily_loss_amount': 0.0,
                'shutdown_triggered': False,
                'shutdown_reason': '',
                'premium_buffer_enabled': False,
                'premium_buffer_amount': 10.0
            }
            cursor.execute(
                'INSERT INTO settings (id, data) VALUES (?, ?)',
                ('main_settings', _json_dumps(default_settings))
            )
            conn.commit()

# Settings operations
def get_settings() -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM settings WHERE id = ?', ('main_settings',))
        row = cursor.fetchone()
        if row:
            return json.loads(row['data'])
        return {}

def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    settings.update(updates)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE settings SET data = ? WHERE id = ?',
            (_json_dumps(settings), 'main_settings')
        )
        conn.commit()
    return settings

# Alert operations
def insert_alert(alert: Dict[str, Any]) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alerts (id, ticker, strike, option_type, expiration, entry_price, 
                              action, sell_percentage, received_at, processed, trade_executed, 
                              raw_message, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            alert.get('id'),
            alert.get('ticker'),
            alert.get('strike'),
            alert.get('option_type'),
            alert.get('expiration'),
            alert.get('entry_price'),
            alert.get('action') or alert.get('alert_type'),
            alert.get('sell_percentage'),
            alert.get('received_at', datetime.now(timezone.utc).isoformat()),
            1 if alert.get('processed') else 0,
            1 if alert.get('trade_executed') else 0,
            alert.get('raw_message'),
            _json_dumps(alert)
        ))
        conn.commit()
    return alert.get('id')

def get_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT data FROM alerts ORDER BY received_at DESC LIMIT ?',
            (limit,)
        )
        return [json.loads(row['data']) for row in cursor.fetchall()]

def update_alert(alert_id: str, updates: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM alerts WHERE id = ?', (alert_id,))
        row = cursor.fetchone()
        if row:
            alert = json.loads(row['data'])
            alert.update(updates)
            cursor.execute(
                'UPDATE alerts SET data = ?, processed = ?, trade_executed = ? WHERE id = ?',
                (_json_dumps(alert), 1 if alert.get('processed') else 0,
                 1 if alert.get('trade_executed') else 0, alert_id)
            )
            conn.commit()

# Trade operations
def insert_trade(trade: Dict[str, Any]) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (id, alert_id, ticker, strike, option_type, expiration,
                              entry_price, exit_price, current_price, quantity, status,
                              broker, executed_at, closed_at, simulated, realized_pnl,
                              unrealized_pnl, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade.get('id'),
            trade.get('alert_id'),
            trade.get('ticker'),
            trade.get('strike'),
            trade.get('option_type'),
            trade.get('expiration'),
            trade.get('entry_price'),
            trade.get('exit_price'),
            trade.get('current_price'),
            trade.get('quantity'),
            trade.get('status'),
            trade.get('broker'),
            trade.get('executed_at'),
            trade.get('closed_at'),
            1 if trade.get('simulated') else 0,
            trade.get('realized_pnl'),
            trade.get('unrealized_pnl'),
            _json_dumps(trade)
        ))
        conn.commit()
    return trade.get('id')

def get_trades(limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute(
                'SELECT data FROM trades WHERE status = ? ORDER BY executed_at DESC LIMIT ?',
                (status, limit)
            )
        else:
            cursor.execute(
                'SELECT data FROM trades ORDER BY executed_at DESC LIMIT ?',
                (limit,)
            )
        return [json.loads(row['data']) for row in cursor.fetchall()]

def update_trade(trade_id: str, updates: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM trades WHERE id = ?', (trade_id,))
        row = cursor.fetchone()
        if row:
            trade = json.loads(row['data'])
            trade.update(updates)
            cursor.execute('''
                UPDATE trades SET data = ?, status = ?, exit_price = ?, 
                       current_price = ?, realized_pnl = ?, unrealized_pnl = ?,
                       closed_at = ?
                WHERE id = ?
            ''', (
                _json_dumps(trade), trade.get('status'), trade.get('exit_price'),
                trade.get('current_price'), trade.get('realized_pnl'),
                trade.get('unrealized_pnl'), trade.get('closed_at'), trade_id
            ))
            conn.commit()

def get_trade_by_id(trade_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM trades WHERE id = ?', (trade_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row['data'])
        return None

# Position operations
def get_open_positions() -> List[Dict[str, Any]]:
    return get_trades(limit=100, status='open')

def get_position_by_ticker(ticker: str, strike: float, option_type: str, expiration: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT data FROM trades 
            WHERE ticker = ? AND strike = ? AND option_type = ? AND expiration = ? AND status = 'open'
        ''', (ticker, strike, option_type, expiration))
        row = cursor.fetchone()
        if row:
            return json.loads(row['data'])
        return None

# Broker config operations
def get_broker_config(broker_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT config FROM broker_configs WHERE broker_id = ?', (broker_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row['config'])
        return None

def save_broker_config(broker_id: str, config: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO broker_configs (broker_id, config)
            VALUES (?, ?)
        ''', (broker_id, _json_dumps(config)))
        conn.commit()

# FIXED C8: insert_position was missing — server.py was using insert_trade for positions
def insert_position(position: dict) -> str:
    """Insert a position record into the positions table"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO positions (id, trade_id, ticker, strike, option_type, expiration,
                                  entry_price, current_price, highest_price, quantity,
                                  average_down_count, initial_entry_price, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            position.get('id'),
            position.get('trade_ids', [None])[0] if position.get('trade_ids') else None,
            position.get('ticker'),
            position.get('strike'),
            position.get('option_type'),
            position.get('expiration'),
            position.get('entry_price'),
            position.get('current_price'),
            position.get('highest_price'),
            position.get('original_quantity'),
            position.get('average_down_count', 0),
            position.get('initial_entry_price'),
            _json_dumps(position)
        ))
        conn.commit()
    return position.get('id', '')


# Portfolio calculations
def get_portfolio_summary() -> Dict[str, Any]:
    trades = get_trades(limit=1000)
    
    open_trades = [t for t in trades if t.get('status') == 'open']
    closed_trades = [t for t in trades if t.get('status') == 'closed']
    
    total_realized = sum(t.get('realized_pnl', 0) or 0 for t in closed_trades)
    total_unrealized = sum(t.get('unrealized_pnl', 0) or 0 for t in open_trades)
    
    winning = [t for t in closed_trades if (t.get('realized_pnl', 0) or 0) > 0]
    losing = [t for t in closed_trades if (t.get('realized_pnl', 0) or 0) < 0]
    
    win_rate = (len(winning) / len(closed_trades) * 100) if closed_trades else 0
    
    pnls = [t.get('realized_pnl', 0) or 0 for t in closed_trades]
    best = max(pnls) if pnls else 0
    worst = min(pnls) if pnls else 0
    avg = sum(pnls) / len(pnls) if pnls else 0
    
    total_invested = sum(
        (t.get('entry_price', 0) or 0) * (t.get('quantity', 0) or 0) * 100
        for t in open_trades
    )
    
    current_value = sum(
        (t.get('current_price', 0) or t.get('entry_price', 0) or 0) * (t.get('quantity', 0) or 0) * 100
        for t in open_trades
    )
    
    return {
        'total_trades': len(trades),
        'open_positions': len(open_trades),
        'closed_positions': len(closed_trades),
        'total_invested': total_invested,
        'current_value': current_value,
        'total_realized_pnl': total_realized,
        'total_unrealized_pnl': total_unrealized,
        'total_pnl': total_realized + total_unrealized,
        'win_rate': win_rate,
        'winning_trades': len(winning),
        'losing_trades': len(losing),
        'best_trade': best,
        'worst_trade': worst,
        'average_pnl': avg
    }

# Initialize database on import
init_database()
