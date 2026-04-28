"""
Options Greeks Calculator
- Delta, Gamma, Theta, Vega
- Real-time Greeks calculation
"""
import math
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Black-Scholes parameters
RISK_FREE_RATE = 0.05  # 5% default


@dataclass
class Greeks:
    """Option Greeks"""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'delta': round(self.delta, 4),
            'gamma': round(self.gamma, 4),
            'theta': round(self.theta, 4),
            'vega': round(self.vega, 4),
            'rho': round(self.rho, 4)
        }


class GreeksCalculator:
    """Calculate option Greeks using Black-Scholes"""
    
    @staticmethod
    def normal_cdf(x: float) -> float:
        """Standard normal CDF"""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    @staticmethod
    def normal_pdf(x: float) -> float:
        """Standard normal PDF"""
        return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    
    @staticmethod
    def black_scholes(
        S: float,      # Spot price
        K: float,      # Strike price
        T: float,     # Time to expiration (years)
        r: float,    # Risk-free rate
        sigma: float, # Volatility
        option_type: str = 'call'
    ) -> Greeks:
        """Calculate Greeks using Black-Scholes model"""
        
        if T <= 0 or sigma <= 0:
            return Greeks()
        
        # d1 and d2
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        sqrt_T = math.sqrt(T)
        
        if option_type.lower() == 'call':
            # Call options
            delta = GreeksCalculator.normal_cdf(d1)
            rho = K * T * math.exp(-r * T) * GreeksCalculator.normal_cdf(d2)
            theta = (-S * sigma * GreeksCalculator.normal_pdf(d1) / (2 * sqrt_T) 
                    - r * K * math.exp(-r * T) * GreeksCalculator.normal_cdf(d2))
        else:
            # Put options
            delta = GreeksCalculator.normal_cdf(d1) - 1
            rho = -K * T * math.exp(-r * T) * GreeksCalculator.normal_cdf(-d2)
            theta = (-S * sigma * GreeksCalculator.normal_pdf(d1) / (2 * sqrt_T) 
                    + r * K * math.exp(-r * T) * GreeksCalculator.normal_cdf(-d2))
        
        # Common Greeks
        gamma = GreeksCalculator.normal_pdf(d1) / (S * sigma * sqrt_T)
        vega = S * sqrt_T * GreeksCalculator.normal_pdf(d1)
        
        # Convert theta to daily
        theta = theta / 365
        
        return Greeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho
        )
    
    @staticmethod
    def calculate_greeks(
        ticker: str,
        strike: float,
        expiration: str,
        option_type: str,
        spot_price: float,
        iv: float = 0.30,
        risk_free_rate: float = RISK_FREE_RATE
    ) -> Greeks:
        """Calculate Greeks for an option
        
        Args:
            ticker: Stock ticker
            strike: Strike price
            expiration: Expiration date (YYYY-MM-DD)
            option_type: CALL or PUT
            spot_price: Current stock price
            iv: Implied volatility (default 30%)
            risk_free_rate: Risk-free rate (default 5%)
        """
        from datetime import datetime, timezone
        
        # Calculate time to expiration
        try:
            exp_date = datetime.fromisoformat(expiration)
        except ValueError:
            exp_date = datetime.strptime(expiration, '%Y-%m-%d')
        
        now = datetime.now(timezone.utc)
        if exp_date.tzinfo is None:
            exp_date = exp_date.replace(tzinfo=timezone.utc)
        
        T = max((exp_date - now).total_seconds() / (365.25 * 24 * 3600), 0.001)
        
        return GreeksCalculator.black_scholes(
            S=spot_price,
            K=strike,
            T=T,
            r=risk_free_rate,
            sigma=iv,
            option_type=option_type
        )
    
    @staticmethod
    def calculate_portfolio_greeks(positions: list, prices: Dict[str, float]) -> Dict:
        """Calculate aggregate portfolio Greeks
        
        Args:
            positions: List of position dicts
            prices: Dict of ticker -> spot price
        """
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0
        
        for pos in positions:
            ticker = pos.get('ticker', '')
            strike = pos.get('strike', 0)
            expiration = pos.get('expiration', '')
            option_type = pos.get('option_type', 'CALL')
            quantity = pos.get('quantity', 1)
            spot = prices.get(ticker, 0)
            iv = pos.get('iv', 0.30)
            
            if not all([ticker, strike, expiration, spot]):
                continue
            
            greeks = GreeksCalculator.calculate_greeks(
                ticker=ticker,
                strike=strike,
                expiration=expiration,
                option_type=option_type,
                spot_price=spot,
                iv=iv
            )
            
            # Multiply by quantity and 100 shares per contract
            multiplier = quantity * 100
            
            total_delta += greeks.delta * multiplier
            total_gamma += greeks.gamma * multiplier
            total_theta += greeks.theta * multiplier
            total_vega += greeks.vega * multiplier
        
        return {
            'delta': round(total_delta, 2),
            'gamma': round(total_gamma, 4),
            'theta': round(total_theta, 2),
            'vega': round(total_vega, 2),
            'position_count': len(positions)
        }
    
    @staticmethod
    def estimate_iv(
        S: float,
        K: float,
        T: float,
        r: float,
        market_price: float,
        option_type: str = 'call'
    ) -> Optional[float]:
        """Estimate implied volatility from market price
        
        Uses Newton-Raphson iteration
        """
        if T <= 0 or market_price <= 0:
            return None
        
        # Initial guess
        sigma = 0.30
        
        for _ in range(100):  # Max iterations
            greeks = GreeksCalculator.black_scholes(S, K, T, r, sigma, option_type)
            
            # Calculate option price
            d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            
            if option_type.lower() == 'call':
                price = S * GreeksCalculator.normal_cdf(d1) - K * math.exp(-r * T) * GreeksCalculator.normal_cdf(d2)
            else:
                price = K * math.exp(-r * T) * GreeksCalculator.normal_cdf(-d2) - S * GreeksCalculator.normal_cdf(-d1)
            
            # Check convergence
            error = market_price - price
            if abs(error) < 0.01:
                return sigma
            
            # Update sigma
            vega = greeks.vega
            if abs(vega) < 0.0001:
                break
            
            sigma = sigma + error / vega
            sigma = max(0.01, min(sigma, 5.0))  # Bound sigma
        
        return sigma


# Export
GreeksCalculator = GreeksCalculator()
Greeks = Greeks

__all__ = ['GreeksCalculator', 'Greeks', 'calculate_greeks', 'calculate_portfolio_greeks']