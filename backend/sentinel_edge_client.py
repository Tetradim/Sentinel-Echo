"""
Sentinel Edge Integration Client
Allows Sentinel Echo to query Sentinel Edge for market confidence analysis
"""
import os
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidence levels for trade signals"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass
class MarketAnalysis:
    """Market analysis result from Sentinel Edge"""
    ticker: str
    timestamp: datetime
    
    # Confidence scores (0-100)
    overall_confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.NONE
    
    # Individual metrics
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volatility_score: float = 0.0
    liquidity_score: float = 0.0
    
    # Technical signals
    signals: List[str] = field(default_factory=list)
    
    # Recommendation
    recommendation: str = "HOLD"  # BUY, SELL, HOLD
    reason: str = ""
    
    # Raw response
    raw_data: Dict = field(default_factory=dict)
    
    @property
    def is_buyable(self) -> bool:
        """Check if signal is worth acting on"""
        return (
            self.confidence_level in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]
            and self.recommendation in ["BUY", "STRONG_BUY"]
        )
    
    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'timestamp': self.timestamp.isoformat(),
            'overall_confidence': self.overall_confidence,
            'confidence_level': self.confidence_level.value,
            'trend_score': self.trend_score,
            'momentum_score': self.momentum_score,
            'volatility_score': self.volatility_score,
            'liquidity_score': self.liquidity_score,
            'signals': self.signals,
            'recommendation': self.recommendation,
            'reason': self.reason,
            'is_buyable': self.is_buyable,
        }


@dataclass
class EdgeConfig:
    """Sentinel Edge connection config"""
    host: str = "localhost"
    port: int = 8000
    api_key: str = ""
    timeout: int = 30
    use_ssl: bool = False
    
    @property
    def base_url(self) -> str:
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}"


class SentinelEdgeClient:
    """Client for Sentinel Edge market analysis"""
    
    def __init__(self, config: EdgeConfig = None):
        self.config = config or EdgeConfig()
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                headers={
                    "X-API-Key": self.config.api_key,
                    "Content-Type": "application/json",
                }
            )
        return self._session
    
    async def close(self) -> None:
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def analyze(self, ticker: str, signal_type: str = "BTO") -> MarketAnalysis:
        """
        Analyze a ticker and return confidence score
        
        Args:
            ticker: Stock/option ticker to analyze
            signal_type: Type of signal (BTO, STC, etc.)
            
        Returns:
            MarketAnalysis with confidence scores
        """
        try:
            session = await self._get_session()
            
            # Call Sentinel Edge API
            url = f"{self.config.base_url}/api/v1/analyze"
            payload = {
                "ticker": ticker.upper(),
                "signal_type": signal_type,
                "timestamp": datetime.now().isoformat(),
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_response(data)
                else:
                    error_text = await response.text()
                    logger.warning(f"[Edge] API error {response.status}: {error_text}")
                    return self._create_fallback_analysis(ticker, f"API error: {response.status}")
        
        except aiohttp.ClientError as e:
            logger.warning(f"[Edge] Connection error: {e}")
            return self._create_fallback_analysis(ticker, f"Connection error: {e}")
        except asyncio.TimeoutError:
            logger.warning(f"[Edge] Request timeout for {ticker}")
            return self._create_fallback_analysis(ticker, "Timeout")
        except Exception as e:
            logger.error(f"[Edge] Unexpected error: {e}")
            return self._create_fallback_analysis(ticker, str(e))
    
    def _parse_response(self, data: Dict) -> MarketAnalysis:
        """Parse Sentinel Edge response"""
        return MarketAnalysis(
            ticker=data.get('ticker', ''),
            timestamp=datetime.now(),
            overall_confidence=data.get('confidence', 0.0),
            confidence_level=self._get_confidence_level(data.get('confidence', 0)),
            trend_score=data.get('trend_score', 0.0),
            momentum_score=data.get('momentum_score', 0.0),
            volatility_score=data.get('volatility_score', 0.0),
            liquidity_score=data.get('liquidity_score', 0.0),
            signals=data.get('signals', []),
            recommendation=data.get('recommendation', 'HOLD'),
            reason=data.get('reason', ''),
            raw_data=data,
        )
    
    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Convert numeric confidence to level"""
        if confidence >= 70:
            return ConfidenceLevel.HIGH
        elif confidence >= 40:
            return ConfidenceLevel.MEDIUM
        elif confidence >= 20:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.NONE
    
    def _create_fallback_analysis(self, ticker: str, error: str) -> MarketAnalysis:
        """Create fallback analysis when Edge is unavailable"""
        # Missing analyzer data must not look like a usable confidence signal.
        return MarketAnalysis(
            ticker=ticker,
            timestamp=datetime.now(),
            overall_confidence=0.0,
            confidence_level=ConfidenceLevel.NONE,
            recommendation="HOLD",
            reason=f"Edge unavailable: {error}",
        )
    
    async def batch_analyze(self, tickers: List[str]) -> Dict[str, MarketAnalysis]:
        """Analyze multiple tickers"""
        results = {}
        
        # Run in parallel
        tasks = [self.analyze(ticker) for ticker in tickers]
        analyses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for ticker, analysis in zip(tickers, analyses):
            if isinstance(analysis, Exception):
                logger.error(f"[Edge] Error analyzing {ticker}: {analysis}")
                results[ticker] = self._create_fallback_analysis(ticker, str(analysis))
            else:
                results[ticker] = analysis
        
        return results
    
    async def health_check(self) -> bool:
        """Check if Sentinel Edge is available"""
        try:
            session = await self._get_session()
            url = f"{self.config.base_url}/health"
            
            async with session.get(url) as response:
                return response.status == 200
        except Exception:
            return False


# ============= ANALYZER INTEGRATION =============

class MarketConfidenceAnalyzer:
    """Analyzes alerts against Sentinel Edge before trading"""
    
    def __init__(self, edge_client: SentinelEdgeClient):
        self.edge = edge_client
        self.min_confidence = 40.0  # Minimum confidence to execute
    
    async def should_execute(self, ticker: str, signal_type: str = "BTO") -> tuple[bool, MarketAnalysis]:
        """
        Determine if an alert should be executed
        
        Returns:
            (should_execute, analysis)
        """
        analysis = await self.edge.analyze(ticker, signal_type)
        
        should_execute = (
            analysis.is_buyable 
            and analysis.overall_confidence >= self.min_confidence
        )
        
        logger.info(
            f"[Confidence] {ticker}: {analysis.overall_confidence:.0f}% "
            f"({analysis.confidence_level.value}) -> "
            f"{'EXECUTE' if should_execute else 'SKIP'}"
        )
        
        return should_execute, analysis
    
    async def filter_alerts(self, alerts: List[Dict]) -> List[Dict]:
        """
        Filter alerts based on confidence
        
        Args:
            alerts: List of parsed alert dicts
            
        Returns:
            Filtered list of alerts to execute
        """
        filtered = []
        
        for alert in alerts:
            ticker = alert.get('ticker', '')
            signal_type = alert.get('signal_type', 'BTO')
            
            should_execute, analysis = await self.should_execute(ticker, signal_type)
            
            if should_execute:
                alert['confidence'] = analysis.overall_confidence
                alert['recommendation'] = analysis.recommendation
                alert['edge_analysis'] = analysis.to_dict()
                filtered.append(alert)
            else:
                logger.info(f"[Filter] Skipping {ticker}: {analysis.reason}")
        
        return filtered


# ============= FACTORY =============

def create_edge_client(
    host: str = None,
    port: int = None,
    api_key: str = None,
) -> SentinelEdgeClient:
    """Create Sentinel Edge client from config"""
    return SentinelEdgeClient(EdgeConfig(
        host=host or os.environ.get('EDGE_HOST', 'localhost'),
        port=port or int(os.environ.get('EDGE_PORT', '8000')),
        api_key=api_key or os.environ.get('EDGE_API_KEY', ''),
    ))


# Export
__all__ = [
    'ConfidenceLevel',
    'MarketAnalysis',
    'EdgeConfig',
    'SentinelEdgeClient',
    'MarketConfidenceAnalyzer',
    'create_edge_client',
]
