"""
Portfolio Projection Service - Future Value and Risk Metrics

Calculates:
1. Future portfolio value projections based on historical returns
2. Best/worst case scenarios using standard deviation
3. Risk metrics: Sharpe ratio, Beta, volatility for top funds

Uses yfinance for historical data and risk metrics.
"""
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache file for projection data
PROJECTION_CACHE_FILE = Path('/app/data/projection_cache.json')

# Risk-free rate (approximate 10-year Treasury yield)
RISK_FREE_RATE = 0.04  # 4%

# Historical inflation rate for real returns
INFLATION_RATE = 0.03  # 3%


@dataclass
class FundRiskMetrics:
    """Risk metrics for a fund"""
    symbol: str
    name: str
    portfolio_value: float
    beta: float
    sharpe_ratio: float
    std_dev_annual: float  # Annual standard deviation (volatility)
    annual_return: float  # Historical annual return
    alpha: float  # Jensen's alpha


@dataclass 
class ProjectionScenario:
    """Portfolio projection scenario"""
    year: int
    base_case: float
    best_case: float  # +1 std dev
    worst_case: float  # -1 std dev
    very_worst_case: float  # -2 std dev


class PortfolioProjectionService:
    """Service for portfolio projections and risk analysis"""
    
    def __init__(self):
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load projection cache"""
        try:
            if PROJECTION_CACHE_FILE.exists():
                with open(PROJECTION_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    # Check if cache is still valid (30 days)
                    if data.get('timestamp', 0) > (datetime.now().timestamp() - 30 * 24 * 3600):
                        return data
        except Exception as e:
            logger.warning(f"Error loading projection cache: {e}")
        return {}
    
    def _save_cache(self):
        """Save projection cache"""
        try:
            PROJECTION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.cache['timestamp'] = datetime.now().timestamp()
            with open(PROJECTION_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving projection cache: {e}")
    
    def get_fund_risk_metrics(self, symbol: str, portfolio_value: float, fund_name: str = "", lookback_years: int = 5) -> Optional[FundRiskMetrics]:
        """
        Get risk metrics for a single fund
        
        Args:
            symbol: Fund ticker symbol
            portfolio_value: Current value in portfolio
            fund_name: Display name
            lookback_years: Years of historical data (3, 5, or 10)
            
        Returns:
            FundRiskMetrics or None if data unavailable
        """
        cache_key = f"risk_{symbol}_{lookback_years}y"
        
        # Check cache
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            metrics = FundRiskMetrics(
                symbol=symbol,
                name=fund_name or cached.get('name', symbol),
                portfolio_value=portfolio_value,
                beta=cached.get('beta', 0),
                sharpe_ratio=cached.get('sharpe_ratio', 0),
                std_dev_annual=cached.get('std_dev_annual', 0),
                annual_return=cached.get('annual_return', 0),
                alpha=cached.get('alpha', 0)
            )
            return metrics
        
        try:
            logger.info(f"Fetching risk metrics for {symbol} ({lookback_years}-year lookback)...")
            ticker = yf.Ticker(symbol)
            
            # Get historical data based on lookback period
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_years*365)
            
            hist = ticker.history(start=start_date, end=end_date, interval="1mo")
            
            if hist is None or hist.empty or len(hist) < 24:
                logger.warning(f"Insufficient historical data for {symbol}")
                return None
            
            # Calculate monthly returns
            hist['Return'] = hist['Close'].pct_change()
            monthly_returns = hist['Return'].dropna()
            
            if len(monthly_returns) < 12:
                logger.warning(f"Not enough return data for {symbol}")
                return None
            
            # Get benchmark (S&P 500) for beta calculation
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(start=start_date, end=end_date, interval="1mo")
            spy_hist['Return'] = spy_hist['Close'].pct_change()
            spy_returns = spy_hist['Return'].dropna()
            
            # Align dates
            common_dates = monthly_returns.index.intersection(spy_returns.index)
            fund_returns = monthly_returns.loc[common_dates]
            market_returns = spy_returns.loc[common_dates]
            
            # Calculate metrics
            # Annual return (geometric mean)
            total_return = (1 + fund_returns).prod() - 1
            years = len(fund_returns) / 12
            annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
            
            # Standard deviation (annualized)
            monthly_std = fund_returns.std()
            std_dev_annual = monthly_std * np.sqrt(12)
            
            # Beta
            covariance = fund_returns.cov(market_returns)
            market_variance = market_returns.var()
            beta = covariance / market_variance if market_variance > 0 else 1.0
            
            # Sharpe Ratio
            excess_return = annual_return - RISK_FREE_RATE
            sharpe_ratio = excess_return / std_dev_annual if std_dev_annual > 0 else 0
            
            # Alpha (Jensen's Alpha)
            market_annual_return = (1 + market_returns).prod() ** (12/len(market_returns)) - 1
            expected_return = RISK_FREE_RATE + beta * (market_annual_return - RISK_FREE_RATE)
            alpha = annual_return - expected_return
            
            # Get name from info if not provided
            if not fund_name:
                info = ticker.info or {}
                fund_name = info.get('shortName', info.get('longName', symbol))
            
            # Cache the results
            self.cache[cache_key] = {
                'name': fund_name,
                'beta': round(beta, 3),
                'sharpe_ratio': round(sharpe_ratio, 3),
                'std_dev_annual': round(std_dev_annual, 4),
                'annual_return': round(annual_return, 4),
                'alpha': round(alpha, 4)
            }
            self._save_cache()
            
            logger.info(f"  {symbol}: Beta={beta:.2f}, Sharpe={sharpe_ratio:.2f}, StdDev={std_dev_annual*100:.1f}%")
            
            return FundRiskMetrics(
                symbol=symbol,
                name=fund_name,
                portfolio_value=portfolio_value,
                beta=round(beta, 3),
                sharpe_ratio=round(sharpe_ratio, 3),
                std_dev_annual=round(std_dev_annual, 4),
                annual_return=round(annual_return, 4),
                alpha=round(alpha, 4)
            )
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_portfolio_risk_metrics(self, holdings: List[Dict], lookback_years: int = 5) -> Dict:
        """
        Get risk metrics for top 10 funds in portfolio
        
        Args:
            holdings: List of holdings from HoldingsAggregator
            lookback_years: Years of historical data (3, 5, or 10)
            
        Returns:
            Dict with fund risk metrics and portfolio summary
        """
        # Filter to ETFs and Mutual Funds
        funds = [h for h in holdings if h.get('asset_type') in ['etf', 'mutual_fund']]
        
        # Sort by value and take top 10
        funds.sort(key=lambda x: float(x.get('total_value', 0)), reverse=True)
        top_funds = funds[:10]
        
        if not top_funds:
            return {
                'fund_metrics': [],
                'portfolio_beta': 0,
                'portfolio_sharpe': 0,
                'portfolio_volatility': 0,
                'total_analyzed_value': 0,
                'lookback_years': lookback_years
            }
        
        fund_metrics = []
        total_value = 0
        weighted_beta = 0
        weighted_volatility = 0
        weighted_return = 0
        
        for holding in top_funds:
            symbol = holding.get('symbol', '')
            value = float(holding.get('total_value', 0))
            name = holding.get('name', symbol)
            
            metrics = self.get_fund_risk_metrics(symbol, value, name, lookback_years)
            
            if metrics:
                fund_metrics.append({
                    'symbol': metrics.symbol,
                    'name': metrics.name,
                    'portfolio_value': metrics.portfolio_value,
                    'beta': metrics.beta,
                    'sharpe_ratio': metrics.sharpe_ratio,
                    'std_dev_annual': metrics.std_dev_annual,
                    'volatility_pct': metrics.std_dev_annual * 100,
                    'annual_return': metrics.annual_return,
                    'annual_return_pct': metrics.annual_return * 100,
                    'alpha': metrics.alpha,
                    'alpha_pct': metrics.alpha * 100
                })
                
                total_value += value
                weighted_beta += value * metrics.beta
                weighted_volatility += value * metrics.std_dev_annual
                weighted_return += value * metrics.annual_return
        
        # Calculate portfolio-level metrics
        if total_value > 0:
            portfolio_beta = weighted_beta / total_value
            portfolio_volatility = weighted_volatility / total_value
            portfolio_return = weighted_return / total_value
            portfolio_sharpe = (portfolio_return - RISK_FREE_RATE) / portfolio_volatility if portfolio_volatility > 0 else 0
        else:
            portfolio_beta = 0
            portfolio_volatility = 0
            portfolio_return = 0
            portfolio_sharpe = 0
        
        return {
            'fund_metrics': fund_metrics,
            'portfolio_beta': round(portfolio_beta, 3),
            'portfolio_sharpe': round(portfolio_sharpe, 3),
            'portfolio_volatility': round(portfolio_volatility * 100, 2),
            'portfolio_return': round(portfolio_return * 100, 2),
            'total_analyzed_value': total_value,
            'lookback_years': lookback_years
        }
    
    def project_portfolio_value(
        self, 
        current_value: float,
        years: int = 10,
        custom_return: float = None,
        custom_volatility: float = None
    ) -> List[ProjectionScenario]:
        """
        Project future portfolio value with confidence intervals
        
        Args:
            current_value: Current portfolio value
            years: Number of years to project
            custom_return: Override annual return rate
            custom_volatility: Override volatility
            
        Returns:
            List of ProjectionScenario for each year
        """
        # Default to historical S&P 500 averages if not provided
        annual_return = custom_return if custom_return is not None else 0.10  # 10% nominal
        volatility = custom_volatility if custom_volatility is not None else 0.15  # 15% std dev
        
        # Real return (after inflation)
        real_return = annual_return - INFLATION_RATE
        
        projections = []
        
        for year in range(1, years + 1):
            # Base case: compound at real return rate
            base_case = current_value * ((1 + real_return) ** year)
            
            # Adjust for uncertainty that grows with time
            # Use sqrt(year) scaling for standard deviation
            year_std = volatility * np.sqrt(year)
            
            # Best case: +1 standard deviation
            best_return = real_return + year_std / year  # Annualized adjustment
            best_case = current_value * ((1 + best_return) ** year)
            
            # Worst case: -1 standard deviation
            worst_return = real_return - year_std / year
            worst_case = current_value * ((1 + worst_return) ** year)
            
            # Very worst case: -2 standard deviations
            very_worst_return = real_return - 2 * year_std / year
            very_worst_case = current_value * ((1 + very_worst_return) ** year)
            
            projections.append(ProjectionScenario(
                year=year,
                base_case=round(base_case, 2),
                best_case=round(best_case, 2),
                worst_case=round(worst_case, 2),
                very_worst_case=round(max(0, very_worst_case), 2)  # Can't go below 0
            ))
        
        return projections
    
    def get_projection_summary(self, holdings: List[Dict], total_value: float, lookback_years: int = 5) -> Dict:
        """
        Get complete projection analysis for dashboard
        
        Args:
            holdings: List of holdings
            total_value: Total portfolio value
            lookback_years: Years of historical data (3, 5, or 10)
        
        Returns:
            Dict with projections and risk metrics
        """
        # Get risk metrics first (this gives us historical return and volatility)
        risk_data = self.get_portfolio_risk_metrics(holdings, lookback_years)
        
        # Use portfolio metrics if available, otherwise use defaults
        if risk_data['total_analyzed_value'] > 0:
            annual_return = risk_data['portfolio_return'] / 100
            volatility = risk_data['portfolio_volatility'] / 100
        else:
            annual_return = 0.08  # Default 8%
            volatility = 0.15  # Default 15%
        
        # Generate projections
        projections = self.project_portfolio_value(
            total_value,
            years=10,
            custom_return=annual_return + INFLATION_RATE,  # Add back inflation for nominal
            custom_volatility=volatility
        )
        
        return {
            'current_value': total_value,
            'risk_metrics': risk_data,
            'projections': [
                {
                    'year': p.year,
                    'base_case': p.base_case,
                    'best_case': p.best_case,
                    'worst_case': p.worst_case,
                    'very_worst_case': p.very_worst_case
                }
                for p in projections
            ],
            'assumptions': {
                'historical_return': round(annual_return * 100, 2),
                'volatility': round(volatility * 100, 2),
                'inflation_rate': INFLATION_RATE * 100,
                'risk_free_rate': RISK_FREE_RATE * 100,
                'lookback_years': lookback_years
            },
            'cache_timestamp': self.cache.get('timestamp', 0)
        }