"""
Advanced Analytics Routes
- Custom charts endpoint
- Heatmap endpoint
- Reports endpoint
- Performance metrics
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime, timezone

from advanced_analytics import (
    AdvancedAnalytics, 
    advanced_analytics,
    ChartData,
    HeatmapData,
    ReportData
)

router = APIRouter(prefix="/analytics", tags=["Advanced Analytics"])


@router.get("/heatmap")
async def get_heatmap(
    include_positions: bool = Query(True, description="Include open positions")
):
    """
    Get sector/ticker heatmap data for visualization
    """
    try:
        from database import get_db
        db = get_db()
        
        # Fetch trades
        trades = await db.get_trades(limit=500) if hasattr(db, 'get_trades') else []
        
        # Fetch positions
        positions = await db.get_positions() if include_positions and hasattr(db, 'get_positions') else []
        
        heatmap = advanced_analytics.generate_heatmap(trades, positions)
        
        return {
            "success": True,
            "data": [
                {
                    "sector": h.sector,
                    "ticker": h.ticker,
                    "pnl_percent": h.pnl_percent,
                    "position_count": h.position_count,
                    "avg_pnl": h.avg_pnl,
                    "win_rate": h.win_rate
                }
                for h in heatmap
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/time-series")
async def get_time_series(
    interval: str = Query("day", description="Interval: hour, day, week, month"),
    limit: int = Query(100, description="Max data points")
):
    """
    Get time series chart data for P&L visualization
    """
    try:
        from database import get_db
        db = get_db()
        
        # Fetch trades
        trades = await db.get_trades(limit=500) if hasattr(db, 'get_trades') else []
        
        series = advanced_analytics.generate_time_series(trades, interval)
        
        # Limit results
        series = series[-limit:] if len(series) > limit else series
        
        return {
            "success": True,
            "data": [
                {
                    "timestamp": s.timestamp,
                    "value": s.value,
                    "label": s.label
                }
                for s in series
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/advanced")
async def get_advanced_metrics():
    """
    Get advanced performance metrics (Sharpe, Max Drawdown, etc.)
    """
    try:
        from database import get_db
        db = get_db()
        
        trades = await db.get_trades(limit=500) if hasattr(db, 'get_trades') else []
        
        sharpe = advanced_analytics.calculate_sharpe_ratio(trades)
        max_dd = advanced_analytics.calculate_max_drawdown(trades)
        
        return {
            "success": True,
            "data": {
                "sharpe_ratio": sharpe,
                "max_drawdown_percent": max_dd,
                "trades_analyzed": len(trades)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/daily")
async def get_daily_report(date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)")):
    """
    Get daily P&L report
    """
    try:
        from database import get_db
        db = get_db()
        
        trades = await db.get_trades(limit=500) if hasattr(db, 'get_trades') else []
        
        report_date = None
        if date:
            try:
                report_date = datetime.fromisoformat(date)
            except ValueError:
                pass
        
        report = advanced_analytics.generate_daily_report(trades, report_date)
        
        return {
            "success": True,
            "data": {
                "title": report.title,
                "sections": report.sections,
                "generated_at": report.generated_at,
                "period": report.period
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/weekly")
async def get_weekly_report():
    """
    Get weekly performance summary
    """
    try:
        from database import get_db
        db = get_db()
        
        trades = await db.get_trades(limit=500) if hasattr(db, 'get_trades') else []
        
        report = advanced_analytics.generate_weekly_report(trades)
        
        return {
            "success": True,
            "data": {
                "title": report.title,
                "sections": report.sections,
                "generated_at": report.generated_at,
                "period": report.period
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/tax")
async def get_tax_report(year: int = Query(datetime.now().year, description="Tax year")):
    """
    Get tax report (8949 format)
    """
    try:
        from database import get_db
        db = get_db()
        
        trades = await db.get_trades(limit=1000) if hasattr(db, 'get_trades') else []
        
        tax_report = advanced_analytics.generate_tax_report(trades, year)
        
        return {
            "success": True,
            "data": tax_report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_performance_stats():
    """
    Get comprehensive performance statistics
    """
    try:
        from database import get_db
        db = get_db()
        
        trades = await db.get_trades(limit=500) if hasattr(db, 'get_trades') else []
        
        sharpe = advanced_analytics.calculate_sharpe_ratio(trades)
        max_dd = advanced_analytics.calculate_max_drawdown(trades)
        
        # Calculate additional stats
        total_pnl = sum(t.get('realized_pnl', 0) or 0 for t in trades)
        wins = len([t for t in trades if (t.get('realized_pnl', 0) or 0) > 0])
        losses = len([t for t in trades if (t.get('realized_pnl', 0) or 0) < 0])
        
        return {
            "success": True,
            "data": {
                "total_trades": len(trades),
                "total_pnl": total_pnl,
                "wins": wins,
                "losses": losses,
                "win_rate": wins / len(trades) * 100 if trades else 0,
                "sharpe_ratio": sharpe,
                "max_drawdown_percent": max_dd,
                "avg_pnl": total_pnl / len(trades) if trades else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))