"""
Alert Handler with Sentinel Edge Integration
Routes alerts through Edge confidence check before execution
"""
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Import components
try:
    from analyst_formats import auto_parse
    from sentinel_edge_client import (
        create_edge_client,
        MarketConfidenceAnalyzer,
        MarketAnalysis,
        ConfidenceLevel,
    )
    EDGE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Edge client not available: {e}")
    EDGE_AVAILABLE = False


# ============= ALERT FILTER =============

@dataclass
class FilteredAlert:
    """Alert after Edge filtering"""
    original: Dict
    ticker: str
    signal_type: str
    confidence: float = 0.0
    confidence_level: str = "UNKNOWN"
    recommendation: str = "HOLD"
    should_execute: bool = False
    edge_analysis: Optional[Dict] = None
    skip_reason: str = ""


class AlertFilter:
    """
    Filters alerts through Sentinel Edge confidence check
    """
    
    def __init__(
        self,
        edge_host: str = None,
        edge_port: int = None,
        min_confidence: float = 40.0,
        enabled: bool = True,
    ):
        self.enabled = enabled and EDGE_AVAILABLE
        self.min_confidence = min_confidence
        
        if self.enabled:
            self.edge_client = create_edge_client(
                host=edge_host,
                port=edge_port,
            )
            self.analyzer = MarketConfidenceAnalyzer(self.edge_client)
            logger.info(f"[AlertFilter] Enabled with Edge at {edge_host}:{edge_port}")
        else:
            self.edge_client = None
            self.analyzer = None
            logger.info("[AlertFilter] Disabled (Edge unavailable)")
    
    async def process_alert(self, message: str) -> FilteredAlert:
        """
        Process a single alert through the filter
        
        Args:
            message: Raw Discord alert message
            
        Returns:
            FilteredAlert with confidence info
        """
        # First parse the alert
        parsed = self._parse_message(message)
        
        if not parsed or not parsed.get('ticker'):
            return FilteredAlert(
                original={'message': message},
                ticker='',
                signal_type='UNKNOWN',
                skip_reason='Could not parse message',
            )
        
        ticker = parsed['ticker']
        signal_type = parsed.get('signal_type', 'BTO')
        
        # Sentinel Echo is not the decision brain. If Edge cannot evaluate the
        # signal, the alert must stay blocked until an external decision exists.
        if not self.enabled:
            return FilteredAlert(
                original=parsed,
                ticker=ticker,
                signal_type=signal_type,
                confidence=0.0,
                confidence_level="NONE",
                recommendation="HOLD",
                should_execute=False,
                skip_reason="Edge not connected",
            )
        
        # Query Edge for confidence
        try:
            should_execute, analysis = await self.analyzer.should_execute(
                ticker, signal_type
            )
            
            return FilteredAlert(
                original=parsed,
                ticker=ticker,
                signal_type=signal_type,
                confidence=analysis.overall_confidence,
                confidence_level=analysis.confidence_level.value,
                recommendation=analysis.recommendation,
                should_execute=should_execute,
                edge_analysis=analysis.to_dict(),
                skip_reason="" if should_execute else analysis.reason,
            )
            
        except Exception as e:
            logger.error(f"[AlertFilter] Error processing {ticker}: {e}")
            return FilteredAlert(
                original=parsed,
                ticker=ticker,
                signal_type=signal_type,
                confidence=0.0,
                confidence_level="NONE",
                recommendation="HOLD",
                should_execute=False,
                skip_reason=f"Edge error: {e}",
            )
    
    async def process_batch(self, messages: List[str]) -> List[FilteredAlert]:
        """Process multiple alerts"""
        results = []
        
        for message in messages:
            result = await self.process_alert(message)
            results.append(result)
        
        return results
    
    async def get_executable_alerts(self, messages: List[str]) -> List[FilteredAlert]:
        """Get only alerts that should execute"""
        results = await self.process_batch(messages)
        return [r for r in results if r.should_execute]
    
    def _parse_message(self, message: str) -> Optional[Dict]:
        """Parse alert message to extract ticker etc"""
        if not EDGE_AVAILABLE:
            return {'ticker': 'UNKNOWN', 'signal_type': 'BTO'}
        
        result = auto_parse(message)
        if result:
            return result.to_dict() if hasattr(result, 'to_dict') else result
        return None
    
    async def close(self) -> None:
        """Cleanup"""
        if self.edge_client:
            await self.edge_client.close()


# ============= CONFIDENCE EMBED =============

def create_confidence_embed(alert: FilteredAlert) -> Dict:
    """
    Create Discord embed showing confidence info
    """
    color = {
        "HIGH": 0x00FF00,    # Green
        "MEDIUM": 0xFFFF00,  # Yellow
        "LOW": 0xFFA500,     # Orange
        "NONE": 0xFF0000,    # Red
    }.get(alert.confidence_level, 0x808080)
    
    embed = {
        "title": f"📊 Confidence Check: {alert.ticker}",
        "color": color,
        "fields": [
            {
                "name": "Signal",
                "value": alert.signal_type,
                "inline": True,
            },
            {
                "name": "Confidence",
                "value": f"{alert.confidence:.0f}% ({alert.confidence_level})",
                "inline": True,
            },
            {
                "name": "Recommendation",
                "value": alert.recommendation,
                "inline": True,
            },
        ],
    }
    
    if alert.edge_analysis:
        analysis = alert.edge_analysis
        embed["fields"].extend([
            {
                "name": "Trend",
                "value": f"{analysis.get('trend_score', 0):.0f}/100",
                "inline": True,
            },
            {
                "name": "Momentum",
                "value": f"{analysis.get('momentum_score', 0):.0f}/100",
                "inline": True,
            },
            {
                "name": "Volatility",
                "value": f"{analysis.get('volatility_score', 0):.0f}/100",
                "inline": True,
            },
        ])
    
    if alert.skip_reason:
        embed["description"] = f"⏭️ Skipped: {alert.skip_reason}"
    elif alert.should_execute:
        embed["description"] = "✅ Approved for execution"
    
    return embed


# ============= API ROUTES =============

async def register_alert_routes(app):
    """Register alert filter routes with FastAPI"""
    from fastapi import APIRouter, HTTPException
    
    router = APIRouter(prefix="/alerts", tags=["alerts"])
    
    # Create filter instance
    _filter = None
    
    def get_filter() -> AlertFilter:
        nonlocal _filter
        if _filter is None:
            _filter = AlertFilter(
                edge_host=os.environ.get('EDGE_HOST', 'localhost'),
                edge_port=int(os.environ.get('EDGE_PORT', '8000')),
                min_confidence=float(os.environ.get('MIN_CONFIDENCE', '40.0')),
            )
        return _filter
    
    @router.post("/check")
    async def check_alert(message: str):
        """Check a single alert through Edge"""
        f = get_filter()
        result = await f.process_alert(message)
        
        return {
            "alert": result.original,
            "confidence": result.confidence,
            "confidence_level": result.confidence_level,
            "recommendation": result.recommendation,
            "should_execute": result.should_execute,
            "skip_reason": result.skip_reason,
            "embed": create_confidence_embed(result),
        }
    
    @router.post("/check/batch")
    async def check_alerts(messages: List[str]):
        """Check multiple alerts"""
        f = get_filter()
        results = await f.process_batch(messages)
        
        return {
            "total": len(results),
            "executable": sum(1 for r in results if r.should_execute),
            "skipped": sum(1 for r in results if not r.should_execute),
            "results": [
                {
                    "ticker": r.ticker,
                    "confidence": r.confidence,
                    "should_execute": r.should_execute,
                    "skip_reason": r.skip_reason,
                }
                for r in results
            ],
        }
    
    @router.get("/status")
    async def get_status():
        """Get filter status"""
        f = get_filter()
        
        return {
            "enabled": f.enabled,
            "min_confidence": f.min_confidence,
            "edge_connected": f.edge_client is not None,
        }
    
    app.include_router(router)


# Export
__all__ = [
    'FilteredAlert',
    'AlertFilter',
    'create_confidence_embed',
    'register_alert_routes',
]
