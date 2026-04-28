"""
Advanced Trading Analytics
- Custom charts data generation
- Sector/ticker heatmaps
- Performance reporting
- Advanced metrics
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import statistics
import json

logger = logging.getLogger(__name__)


# Sector mappings for heatmap
SECTOR_MAP = {
    'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'GOOG': 'Technology',
    'AMZN': 'Consumer', 'META': 'Technology', 'NVDA': 'Technology', 'AMD': 'Technology',
    'INTC': 'Technology', 'CRM': 'Technology', 'ORCL': 'Technology', 'ADBE': 'Technology',
    'TSLA': 'Consumer', 'BRK.B': 'Financial', 'JPM': 'Financial', 'BAC': 'Financial',
    'WFC': 'Financial', 'GS': 'Financial', 'MS': 'Financial', 'C': 'Financial',
    'V': 'Financial', 'MA': 'Financial', 'PYPL': 'Financial', 'SQ': 'Financial',
    'JNJ': 'Healthcare', 'UNH': 'Healthcare', 'PFE': 'Healthcare', 'ABBV': 'Healthcare',
    'LLY': 'Healthcare', 'TMO': 'Healthcare', 'ABT': 'Healthcare', 'MRK': 'Healthcare',
    'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy', 'EOG': 'Energy',
    'SLB': 'Energy', 'PSX': 'Energy', 'VLO': 'Energy', 'MPC': 'Energy',
    'WMT': 'Consumer', 'HD': 'Consumer', 'LOW': 'Consumer', 'TGT': 'Consumer',
    'COST': 'Consumer', 'TJX': 'Consumer', 'DG': 'Consumer', 'ROST': 'Consumer',
    'DIS': 'Media', 'CMCSA': 'Media', 'T': 'Communications', 'VZ': 'Communications',
    'TMUS': 'Communications', 'NFLX': 'Media', 'PARA': 'Media', 'WBD': 'Media',
    'BA': 'Industrial', 'CAT': 'Industrial', 'GE': 'Industrial', 'HON': 'Industrial',
    'UPS': 'Industrial', 'RTX': 'Industrial', 'LMT': 'Industrial', 'DE': 'Industrial',
    'JNPR': 'Industrial', 'ITW': 'Industrial', 'ETN': 'Industrial', 'PH': 'Industrial',
    'AMGN': 'Healthcare', 'GILD': 'Healthcare', 'BIIB': 'Healthcare', 'REGN': 'Healthcare',
    'VRTX': 'Healthcare', 'ISRG': 'Healthcare', 'MDT': 'Healthcare', 'SYK': 'Healthcare',
    'USB': 'Financial', 'SPGI': 'Financial', 'AXP': 'Financial', 'SCHW': 'Financial',
    'COF': 'Financial', 'BLK': 'Financial', 'STT': 'Financial', 'BK': 'Financial',
}


@dataclass
class HeatmapData:
    """Heatmap data point for visualization"""
    sector: str
    ticker: str
    pnl_percent: float
    position_count: int
    avg_pnl: float
    win_rate: float


@dataclass
class ChartData:
    """Chart data point for custom charts"""
    timestamp: str
    value: float
    label: Optional[str] = None


@dataclass
class ReportData:
    """Report data structure"""
    title: str
    sections: List[Dict[str, Any]]
    generated_at: str
    period: str


class AdvancedAnalytics:
    """Advanced analytics with custom charts, heatmaps, and reporting"""
    
    def __init__(self):
        self.cache = {}
        self.cache_timeout = 300  # 5 minutes
    
    def get_sector(self, ticker: str) -> str:
        """Get sector for ticker"""
        return SECTOR_MAP.get(ticker.upper(), 'Other')
    
    def generate_heatmap(self, trades: List[Dict], positions: List[Dict]) -> List[HeatmapData]:
        """Generate sector/ticker heatmap data"""
        sector_data = defaultdict(lambda: {
            'tickers': set(),
            'pnl': [],
            'wins': 0,
            'losses': 0,
            'count': 0
        })
        
        # Process trades
        for trade in trades:
            ticker = trade.get('ticker', '').upper()
            sector = self.get_sector(ticker)
            pnl = trade.get('realized_pnl', 0) or 0
            
            sector_data[sector]['tickers'].add(ticker)
            sector_data[sector]['pnl'].append(pnl)
            sector_data[sector]['count'] += 1
            if pnl > 0:
                sector_data[sector]['wins'] += 1
            elif pnl < 0:
                sector_data[sector]['losses'] += 1
        
        # Process open positions
        for pos in positions:
            ticker = pos.get('ticker', '').upper()
            sector = self.get_sector(ticker)
            unrealized = pos.get('unrealized_pnl', 0) or 0
            
            sector_data[sector]['tickers'].add(ticker)
            sector_data[sector]['pnl'].append(unrealized)
            sector_data[sector]['count'] += 1
        
        # Generate heatmap data
        heatmap = []
        for sector, data in sector_data.items():
            if not data['pnl']:
                continue
                
            total_pnl = sum(data['pnl'])
            avg_pnl = total_pnl / len(data['pnl']) if data['pnl'] else 0
            pnl_percent = (avg_pnl / 100) * 100  # Normalize to percentage
            
            heatmap.append(HeatmapData(
                sector=sector,
                ticker=', '.join(list(data['tickers'])[:3]),
                pnl_percent=pnl_percent,
                position_count=data['count'],
                avg_pnl=avg_pnl,
                win_rate=(data['wins'] / data['count'] * 100) if data['count'] > 0 else 0
            ))
        
        return sorted(heatmap, key=lambda x: x.pnl_percent, reverse=True)
    
    def generate_time_series(self, trades: List[Dict], interval: str = 'day') -> List[ChartData]:
        """Generate time series chart data
        
        Args:
            trades: List of trade dictionaries
            interval: 'hour', 'day', 'week', 'month'
        """
        time_data = defaultdict(float)
        
        for trade in trades:
            executed_at = trade.get('executed_at')
            if not executed_at:
                continue
            
            try:
                dt = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
                
                # Group by interval
                if interval == 'hour':
                    key = dt.strftime('%Y-%m-%d %H:00')
                elif interval == 'day':
                    key = dt.strftime('%Y-%m-%d')
                elif interval == 'week':
                    key = dt.strftime('%Y-W%W')
                elif interval == 'month':
                    key = dt.strftime('%Y-%m')
                else:
                    key = dt.strftime('%Y-%m-%d')
                
                pnl = trade.get('realized_pnl', 0) or 0
                time_data[key] += pnl
            except (ValueError, AttributeError):
                continue
        
        # Convert to cumulative
        result = []
        cumulative = 0
        sorted_keys = sorted(time_data.keys())
        
        for key in sorted_keys:
            cumulative += time_data[key]
            result.append(ChartData(
                timestamp=key,
                value=round(cumulative, 2),
                label=key
            ))
        
        return result
    
    def calculate_sharpe_ratio(self, trades: List[Dict], risk_free_rate: float = 0.05) -> float:
        """Calculate Sharpe ratio"""
        if len(trades) < 2:
            return 0.0
        
        returns = []
        for trade in trades:
            pnl = trade.get('realized_pnl', 0) or 0
            # Assume trade value of $1000 for simplicity
            returns.append(pnl / 1000)
        
        if not returns or statistics.stdev(returns) == 0:
            return 0.0
        
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)
        
        # Annualize (assuming daily trades)
        annualized_return = avg_return * 252
        annualized_std = std_return * (252 ** 0.5)
        
        sharpe = (annualized_return - risk_free_rate) / annualized_std if annualized_std > 0 else 0
        return round(sharpe, 2)
    
    def calculate_max_drawdown(self, trades: List[Dict]) -> float:
        """Calculate maximum drawdown percentage"""
        if not trades:
            return 0.0
        
        cumulative = 0
        peak = 0
        max_dd = 0
        
        for trade in trades:
            pnl = trade.get('realized_pnl', 0) or 0
            cumulative += pnl
            
            if cumulative > peak:
                peak = cumulative
            
            dd = (peak - cumulative) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return round(max_dd * 100, 2)
    
    def generate_daily_report(self, trades: List[Dict], date: Optional[datetime] = None) -> ReportData:
        """Generate daily P&L report"""
        if date is None:
            date = datetime.now(timezone.utc)
        
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        # Filter today's trades
        day_trades = []
        for trade in trades:
            executed_at = trade.get('executed_at')
            if not executed_at:
                continue
            try:
                dt = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
                if day_start <= dt < day_end:
                    day_trades.append(trade)
            except (ValueError, AttributeError):
                continue
        
        # Calculate metrics
        total_pnl = sum(t.get('realized_pnl', 0) or 0 for t in day_trades)
        wins = len([t for t in day_trades if (t.get('realized_pnl', 0) or 0) > 0])
        losses = len([t for t in day_trades if (t.get('realized_pnl', 0) or 0) < 0])
        
        sections = [
            {
                'title': 'Summary',
                'data': [
                    f"Total Trades: {len(day_trades)}",
                    f"Wins: {wins}",
                    f"Losses: {losses}",
                    f"Win Rate: {wins/len(day_trades)*100:.1f}%" if day_trades else "Win Rate: 0%",
                    f"Total P&L: ${total_pnl:,.2f}"
                ]
            },
            {
                'title': 'Trade Details',
                'data': [
                    f"{t.get('ticker')} {t.get('strike')}{t.get('option_type', '')}: ${t.get('realized_pnl', 0):.2f}"
                    for t in day_trades[:10]
                ]
            }
        ]
        
        return ReportData(
            title=f"Daily Report - {date.strftime('%Y-%m-%d')}",
            sections=sections,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period='day'
        )
    
    def generate_weekly_report(self, trades: List[Dict]) -> ReportData:
        """Generate weekly performance summary"""
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Filter week's trades
        week_trades = []
        for trade in trades:
            executed_at = trade.get('executed_at')
            if not executed_at:
                continue
            try:
                dt = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
                if dt >= week_start:
                    week_trades.append(trade)
            except (ValueError, AttributeError):
                continue
        
        # Calculate metrics
        total_pnl = sum(t.get('realized_pnl', 0) or 0 for t in week_trades)
        wins = len([t for t in week_trades if (t.get('realized_pnl', 0) or 0) > 0])
        
        # Top performers
        by_ticker = defaultdict(float)
        for trade in week_trades:
            ticker = trade.get('ticker', '')
            pnl = trade.get('realized_pnl', 0) or 0
            by_ticker[ticker] += pnl
        
        top_tickers = sorted(by_ticker.items(), key=lambda x: x[1], reverse=True)[:5]
        
        sections = [
            {
                'title': 'Weekly Summary',
                'data': [
                    f"Total Trades: {len(week_trades)}",
                    f"Wins: {wins}",
                    f"Win Rate: {wins/len(week_trades)*100:.1f}%" if week_trades else "N/A",
                    f"Total P&L: ${total_pnl:,.2f}"
                ]
            },
            {
                'title': 'Top Performers',
                'data': [f"{t}: ${p:,.2f}" for t, p in top_tickers]
            }
        ]
        
        return ReportData(
            title=f"Weekly Report - {week_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}",
            sections=sections,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period='week'
        )
    
    def generate_tax_report(self, trades: List[Dict], year: int) -> Dict:
        """Generate tax report in 8949 format"""
        year_trades = []
        for trade in trades:
            executed_at = trade.get('executed_at')
            if not executed_at:
                continue
            try:
                dt = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
                if dt.year == year:
                    year_trades.append(trade)
            except (ValueError, AttributeError):
                continue
        
        # Group by term (short-term vs long-term)
        short_term = []
        long_term = []
        
        for trade in year_trades:
            executed_at = trade.get('executed_at')
            pnl = trade.get('realized_pnl', 0) or 0
            
            try:
                dt = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
                days_held = (datetime.now(timezone.utc) - dt).days
                
                if days_held > 365:
                    long_term.append({
                        'ticker': trade.get('ticker'),
                        'pnl': pnl,
                        'acquired': dt.strftime('%Y-%m-%d'),
                        'sold': datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    })
                else:
                    short_term.append({
                        'ticker': trade.get('ticker'),
                        'pnl': pnl,
                        'acquired': dt.strftime('%Y-%m-%d'),
                        'sold': datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    })
            except (ValueError, AttributeError):
                continue
        
        return {
            'year': year,
            'short_term_gain': sum(t['pnl'] for t in short_term),
            'long_term_gain': sum(t['pnl'] for t in long_term),
            'short_term_count': len(short_term),
            'long_term_count': len(long_term),
            'short_term_trades': short_term,
            'long_term_trades': long_term
        }


# Performance caching decorator
def cache_result(timeout: int = 300):
    """Cache decorator for expensive analytics"""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            now = datetime.now(timezone.utc).timestamp()
            
            if not hasattr(self, '_cache'):
                self._cache = {}
            
            if cache_key in self._cache:
                cached_time, cached_value = self._cache[cache_key]
                if now - cached_time < timeout:
                    return cached_value
            
            result = func(self, *args, **kwargs)
            self._cache[cache_key] = (now, result)
            return result
        return wrapper
    return decorator


# Performance-optimized analytics instance
advanced_analytics = AdvancedAnalytics()