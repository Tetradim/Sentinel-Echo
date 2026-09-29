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
                'trim_alert_listening_enabled': True,
                'active_broker': 'alpaca',
                'source_overrides': {},
                'chrome_bridge_require_source_override': True,
                'default_quantity': 1,
                'smart_sizing_enabled': True,
                'smart_sizing_agreement_percent': 100.0,
                'smart_sizing_mixed_percent': 50.0,
                'smart_sizing_conflict_percent': 25.0,
                'entry_slippage_sizing_enabled': True,
                'entry_slippage_mode': 'tiered',
                'entry_slippage_warning_percent': 10.0,
                'entry_slippage_severe_percent': 20.0,
                'entry_slippage_warning_size_percent': 50.0,
                'entry_slippage_severe_size_percent': 25.0,
                'marketable_entry_enabled': True,
                'simulation_mode': False,
                'max_position_size': 1000.0,
                'risk_per_trade': 1.0,
                'risk_budget_sizing_enabled': True,
                'max_loss_per_trade': 100.0,
                'max_drawdown_percent': 20.0,
                'max_positions_per_ticker': 3,
                'max_positions_per_sector': 3,
                'averaging_down_enabled': False,
                'price_drop_threshold': 10.0,
                'buy_percentage': 25.0,
                'max_average_downs': 3,
                'take_profit_enabled': False,
                'take_profit_percentage': 50.0,
                'take_profit_sell_percentage': 100.0,
                'stop_loss_enabled': False,
                'stop_loss_percentage': 25.0,
                'bracket_order_enabled': False,
                'break_even_enabled': False,
                'break_even_activation_type': 'percent',
                'break_even_activation_percentage': 10.0,
                'break_even_activation_cents': 10.0,
                'stop_loss_order_type': 'market',
                'trailing_stop_enabled': False,
                'trailing_stop_type': 'percent',
                'trailing_stop_percent': 10.0,
                'trailing_stop_cents': 50.0,
                'trailing_hours': 4.0,
                'coordinated_exit_enabled': True,
                'coordinated_exit_quote_max_age_seconds': 15.0,
                'post_exit_telemetry_enabled': True,
                'post_exit_telemetry_minutes': 60,
                'coordinated_normal_stop_loss_percent': 35.0,
                'coordinated_high_risk_stop_loss_percent': 50.0,
                'coordinated_high_risk_size_percent': 25.0,
                'coordinated_emergency_stop_loss_percent': 50.0,
                'coordinated_stop_required_confirmations': 2,
                'coordinated_stop_confirmation_interval_seconds': 1.0,
                'coordinated_break_even_required_confirmations': 2,
                'coordinated_break_even_confirmation_interval_seconds': 1.0,
                'coordinated_break_even_preserve_runner': True,
                'coordinated_runner_reserve_quantity': 1,
                'coordinated_profit_stage_1_percent': 25.0,
                'coordinated_profit_stage_1_sell_percent': 50.0,
                'coordinated_profit_stage_2_percent': 35.0,
                'coordinated_profit_stage_2_sell_percent': 25.0,
                'coordinated_fast_scalp_profit_stage_1_percent': 10.0,
                'coordinated_fast_scalp_profit_stage_2_percent': 20.0,
                'coordinated_swing_activation_percent': 30.0,
                'coordinated_swing_trailing_percent': 25.0,
                'coordinated_swing_break_even_activation_percent': 30.0,
                'coordinated_swing_profit_stage_1_percent': 50.0,
                'coordinated_swing_profit_stage_2_percent': 100.0,
                'coordinated_low_premium_threshold': 0.30,
                'coordinated_medium_premium_threshold': 1.00,
                'coordinated_low_activation_percent': 15.0,
                'coordinated_low_min_activation_cents': 3.0,
                'coordinated_low_trailing_percent': 15.0,
                'coordinated_low_min_trailing_cents': 3.0,
                'coordinated_low_break_even_activation_percent': 15.0,
                'coordinated_medium_activation_percent': 20.0,
                'coordinated_medium_trailing_percent': 15.0,
                'coordinated_medium_break_even_activation_percent': 20.0,
                'coordinated_high_activation_percent': 12.0,
                'coordinated_high_trailing_percent': 10.0,
                'coordinated_high_break_even_activation_percent': 12.0,
                'coordinated_progressive_trailing_enabled': True,
                'coordinated_trailing_mode': 'tightening',
                'coordinated_trailing_step_gain_percent': 10.0,
                'coordinated_trailing_step_tighten_percent': 1.0,
                'coordinated_trailing_min_percent': 8.0,
                'coordinated_trailing_volatility_gate_percent': 8.0,
                'coordinated_elastic_activation_percent': 5.0,
                'coordinated_elastic_min_activation_cents': 3.0,
                'coordinated_elastic_trailing_start_percent': 6.0,
                'coordinated_elastic_trailing_step_gain_percent': 10.0,
                'coordinated_elastic_trailing_step_widen_percent': 1.0,
                'coordinated_elastic_trailing_max_percent': 10.0,
                'coordinated_trailing_spread_multiplier': 2.0,
                'coordinated_loss_ladder_enabled': True,
                'coordinated_loss_ladder': [
                    {'loss_percent': 12.0, 'quantity_mode': 'percent_original', 'quantity': 10.0, 'confirmations': 2},
                    {'loss_percent': 18.0, 'quantity_mode': 'percent_original', 'quantity': 20.0, 'confirmations': 2},
                    {'loss_percent': 25.0, 'quantity_mode': 'percent_original', 'quantity': 30.0, 'confirmations': 2},
                    {'loss_percent': 35.0, 'quantity_mode': 'percent_remaining', 'quantity': 100.0, 'confirmations': 1},
                ],
                'core_runner_enabled': False,
                'core_runner_allocation_mode': 'greater_of',
                'core_runner_allocation_percent': 20.0,
                'core_runner_fixed_contracts': 1,
                'core_runner_min_contracts': 1,
                'core_runner_max_contracts': 2,
                'core_runner_allow_single_contract': False,
                'core_runner_activation_mfe_percent': 100.0,
                'core_runner_reserve_candidates_from_profit': True,
                'core_runner_loss_ladder_consumes_candidates': True,
                'core_runner_protect_loss_ladder': True,
                'core_runner_protect_hard_stop': True,
                'core_runner_protect_break_even': True,
                'core_runner_protect_profit_stages': True,
                'core_runner_protect_ordinary_trailing': True,
                'core_runner_protect_reversal_warning': True,
                'core_runner_protect_contextual_trims': True,
                'core_runner_confirmed_reversal_exits': True,
                'core_runner_catastrophic_stop_percent': 65.0,
                'core_runner_catastrophic_confirmations': 2,
                'core_runner_catastrophic_confirmation_interval_seconds': 3.0,
                'core_runner_trailing_enabled': True,
                'core_runner_trailing_mode': 'tiered',
                'core_runner_fixed_trailing_percent': 35.0,
                'core_runner_trailing_tiers': [
                    {'mfe_percent': 100.0, 'trail_percent': 35.0},
                    {'mfe_percent': 300.0, 'trail_percent': 30.0},
                    {'mfe_percent': 500.0, 'trail_percent': 25.0},
                    {'mfe_percent': 1000.0, 'trail_percent': 20.0},
                ],
                'core_runner_min_trailing_cents': 0.0,
                'core_runner_spread_multiplier': 2.0,
                'core_runner_trailing_confirmations': 2,
                'core_runner_trailing_confirmation_interval_seconds': 3.0,
                'core_runner_minimum_activation_seconds': 0,
                'core_runner_require_fresh_high': False,
                'core_runner_allow_floor_to_move_down': False,
                'core_runner_analyst_override_percent': 80.0,
                'core_runner_explicit_full_exit_overrides': True,
                'core_runner_contextual_full_exit_overrides': False,
                'core_runner_zero_dte_liquidation_enabled': True,
                'core_runner_zero_dte_liquidation_time': '15:40',
                'reversal_exit_enabled': True,
                'reversal_warning_confirmations': 3,
                'reversal_confirmed_confirmations': 5,
                'reversal_warning_sell_percent': 25.0,
                'reversal_premium_drawdown_percent': 12.0,
                'reversal_reduce_min_return_percent': 5.0,
                'reversal_reduce_min_mfe_percent': 20.0,
                'adaptive_trailing_enabled': True,
                'adaptive_trailing_min_percent': 8.0,
                'adaptive_trailing_max_percent': 35.0,
                'zero_dte_liquidation_enabled': True,
                'zero_dte_liquidation_time': '15:40',
                'fill_confirmation_timeout_seconds': 180,
                'fill_background_poll_interval_seconds': 15,
                'exit_reprice_interval_seconds': 5,
                'profit_exit_reprice_interval_seconds': 3,
                'profit_exit_marketable_offset_cents': 1.0,
                'auto_shutdown_enabled': False,
                'max_consecutive_losses': 3,
                'max_daily_losses': 5,
                'max_daily_loss_amount': 250.0,
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
    from models import Settings

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM settings WHERE id = ?', ('main_settings',))
        row = cursor.fetchone()
        if row:
            return {**Settings().model_dump(mode="json"), **json.loads(row['data'])}
        return Settings().model_dump(mode="json")

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
