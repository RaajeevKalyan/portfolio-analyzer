"""
Risk Aggregation Service - Calculate sector and geography breakdowns

CHANGELOG:
- Fixed: Sector chart now sorted by value descending
- Fixed: Geography includes Cash category
- Fixed: Percentages now sum to 100% (adds "Other" if needed)
- Fixed: Cash holdings properly categorized
"""
import logging
from typing import Dict, List
from collections import defaultdict
from decimal import Decimal
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding
from sqlalchemy import func, desc

logger = logging.getLogger(__name__)


class RiskAggregator:
    """Aggregate risk metrics across portfolio"""
    
    def get_portfolio_risk_metrics(self) -> Dict:
        """
        Calculate risk metrics for current portfolio
        
        Returns:
            dict: {
                'concentration': [...],  # Top holdings with allocation %
                'sectors': {...},        # Sector breakdown (sorted descending)
                'geography': {...},      # Geographic breakdown (includes Cash)
                'overall_risk': 'low'|'medium'|'high'
            }
        """
        with db_session() as session:
            # Get latest snapshots
            latest_snapshots = self._get_latest_snapshots(session)
            
            if not latest_snapshots:
                return self._empty_metrics()
            
            # Get all holdings
            snapshot_ids = [s.id for s in latest_snapshots]
            holdings = session.query(Holding).filter(
                Holding.portfolio_snapshot_id.in_(snapshot_ids)
            ).all()
            
            if not holdings:
                return self._empty_metrics()
            
            # Calculate total portfolio value
            total_value = sum(float(h.total_value) for h in holdings)
            
            # Separate cash from investments
            cash_value = sum(float(h.total_value) for h in holdings if h.asset_type == 'cash')
            investment_holdings = [h for h in holdings if h.asset_type != 'cash']
            
            # Calculate concentration (top holdings) - excludes cash
            concentration = self._calculate_concentration(investment_holdings, total_value)
            
            # Calculate sector breakdown - excludes cash
            sectors = self._calculate_sector_breakdown(investment_holdings, total_value)
            
            # Calculate geography breakdown - includes cash as separate category
            geography = self._calculate_geography_breakdown(holdings, total_value, cash_value)
            
            # Determine overall risk
            overall_risk = self._calculate_overall_risk(concentration)
            
            return {
                'concentration': concentration,
                'sectors': sectors,
                'geography': geography,
                'overall_risk': overall_risk,
                'total_value': total_value,
                'cash_value': cash_value
            }
    
    def _get_latest_snapshots(self, session) -> List[PortfolioSnapshot]:
        """Get the most recent snapshot for each active broker - OPTIMIZED"""
        from app.services.db_utils import get_latest_snapshots
        return get_latest_snapshots(session)

    def _calculate_concentration(self, holdings: List[Holding], total_value: float) -> List[Dict]:
        """
        Calculate concentration - ONLY return stocks exceeding threshold
        Includes both direct holdings and underlying holdings from ETFs/MFs
        Excludes cash holdings
        """
        # Get threshold from somewhere (default 20%)
        threshold = 20.0  # TODO: Make this configurable
        
        symbol_totals = defaultdict(lambda: {
            'symbol': '',
            'name': '',
            'value': 0,
            'allocation_pct': 0,
            'asset_type': 'stock'
        })
        
        # Process all holdings (direct stocks + underlying)
        for holding in holdings:
            # Skip cash
            if holding.asset_type == 'cash':
                continue
                
            if holding.asset_type == 'stock':
                symbol = holding.symbol
                symbol_totals[symbol]['symbol'] = symbol
                symbol_totals[symbol]['name'] = holding.name or symbol
                symbol_totals[symbol]['value'] += float(holding.total_value)
                symbol_totals[symbol]['asset_type'] = 'stock'
            
            elif holding.asset_type in ['etf', 'mutual_fund'] and holding.underlying_holdings_list:
                for underlying in holding.underlying_holdings_list:
                    symbol = underlying['symbol']
                    underlying_value = float(underlying.get('value', 0))
                    
                    symbol_totals[symbol]['symbol'] = symbol
                    symbol_totals[symbol]['name'] = underlying.get('name', symbol)
                    symbol_totals[symbol]['value'] += underlying_value
                    symbol_totals[symbol]['asset_type'] = 'stock'
        
        # Calculate allocation percentages
        for data in symbol_totals.values():
            data['allocation_pct'] = (data['value'] / total_value * 100) if total_value > 0 else 0
        
        # FILTER: Only stocks EXCEEDING threshold
        high_concentration = [
            data for data in symbol_totals.values()
            if data['allocation_pct'] > threshold
        ]
        
        # Sort by allocation descending
        high_concentration.sort(key=lambda x: x['allocation_pct'], reverse=True)
        
        logger.info(f"Found {len(high_concentration)} stocks exceeding {threshold}% threshold")
        
        return high_concentration    

    def _calculate_sector_breakdown(self, holdings: List[Holding], total_value: float) -> Dict[str, float]:
        """
        Calculate sector allocation breakdown
        Includes both direct holdings AND underlying holdings from ETFs/MFs
        Excludes cash holdings
        Results are sorted by percentage descending
        """
        from app.services.stock_info_service import StockInfoService
        
        service = StockInfoService()
        sector_totals = defaultdict(float)
        
        for holding in holdings:
            # Skip cash
            if holding.asset_type == 'cash':
                continue
            
            # Direct stock holdings - use their sector
            if holding.asset_type == 'stock':
                sector = holding.sector or 'Unknown'
                sector_totals[sector] += float(holding.total_value)
            
            # ETF/MF with underlying - aggregate underlying sectors
            elif holding.asset_type in ['etf', 'mutual_fund'] and holding.underlying_holdings_list:
                for underlying in holding.underlying_holdings_list:
                    sector = underlying.get('sector', 'Unknown')
                    underlying_value = float(underlying.get('value', 0))
                    sector_totals[sector] += underlying_value
            
            # ETF/MF without underlying - use parent sector
            elif holding.asset_type in ['etf', 'mutual_fund']:
                sector = holding.sector or 'Unknown'
                sector_totals[sector] += float(holding.total_value)
        
        # Convert to percentages
        sector_percentages = {}
        total_pct = 0
        
        for sector, value in sector_totals.items():
            pct = (value / total_value * 100) if total_value > 0 else 0
            if pct >= 0.1:  # Include sectors with at least 0.1%
                sector_percentages[sector] = round(pct, 1)
                total_pct += round(pct, 1)
        
        # SORT BY VALUE DESCENDING - this is the key fix
        sector_percentages = dict(sorted(
            sector_percentages.items(),
            key=lambda x: x[1],
            reverse=True
        ))
        
        logger.info(f"Sector breakdown (sorted): {list(sector_percentages.keys())[:5]}...")
        return sector_percentages


    def _calculate_geography_breakdown(self, holdings: List[Holding], total_value: float, 
                                       cash_value: float = 0) -> Dict[str, float]:
        """
        Calculate geographic allocation breakdown
        Includes both direct holdings AND underlying holdings from ETFs/MFs
        Includes Cash as a separate category
        Ensures total sums to 100%
        """
        from app.services.stock_info_service import StockInfoService
        
        service = StockInfoService()
        geo_totals = defaultdict(float)
        
        for holding in holdings:
            # Cash goes to "Cash" category
            if holding.asset_type == 'cash':
                geo_totals['Cash'] += float(holding.total_value)
                continue
            
            # Direct stock holdings - use their country
            if holding.asset_type == 'stock':
                country = holding.country or 'Unknown'
                geography = service._map_country_to_geography(country)
                geo_totals[geography] += float(holding.total_value)
            
            # ETF/MF with underlying - aggregate underlying geographies
            elif holding.asset_type in ['etf', 'mutual_fund'] and holding.underlying_holdings_list:
                for underlying in holding.underlying_holdings_list:
                    country = underlying.get('country', 'Unknown')
                    geography = service._map_country_to_geography(country)
                    underlying_value = float(underlying.get('value', 0))
                    geo_totals[geography] += underlying_value
            
            # ETF/MF without underlying - use parent country
            elif holding.asset_type in ['etf', 'mutual_fund']:
                country = holding.country or 'Unknown'
                geography = service._map_country_to_geography(country)
                geo_totals[geography] += float(holding.total_value)
        
        # Convert to percentages
        geo_percentages = {}
        total_pct = 0
        
        for geo, value in geo_totals.items():
            pct = (value / total_value * 100) if total_value > 0 else 0
            if pct >= 0.1:  # Include regions with at least 0.1%
                rounded_pct = round(pct, 1)
                geo_percentages[geo] = rounded_pct
                total_pct += rounded_pct
        
        # If total doesn't sum to 100%, add remainder to "Other" 
        # (this handles rounding errors and untracked value)
        if total_pct < 99.5 and total_value > 0:
            remainder = round(100 - total_pct, 1)
            if remainder >= 0.1:
                if 'Unknown' in geo_percentages:
                    geo_percentages['Unknown'] += remainder
                else:
                    geo_percentages['Other'] = remainder
        
        # Sort by percentage descending, but keep "Cash" and "Unknown"/"Other" at end
        def sort_key(item):
            geo, pct = item
            if geo == 'Cash':
                return (1, -pct)  # Cash goes near end
            elif geo in ['Unknown', 'Other']:
                return (2, -pct)  # Unknown/Other goes last
            else:
                return (0, -pct)  # Regular geographies sorted by pct
        
        geo_percentages = dict(sorted(
            geo_percentages.items(),
            key=sort_key
        ))
        
        logger.info(f"Geography breakdown: {geo_percentages}")
        return geo_percentages

    
    def _calculate_overall_risk(self, concentration: List[Dict]) -> str:
        """
        Calculate overall risk level based on concentration
        
        Returns: 'low', 'medium', or 'high'
        """
        if not concentration:
            return 'low'
        
        max_allocation = max(h['allocation_pct'] for h in concentration)
        
        if max_allocation > 30:
            return 'high'
        elif max_allocation > 20:
            return 'medium'
        else:
            return 'low'
    
    def _empty_metrics(self) -> Dict:
        """Return empty metrics structure"""
        return {
            'concentration': [],
            'sectors': {},
            'geography': {},
            'overall_risk': 'low',
            'total_value': 0,
            'cash_value': 0
        }


def get_risk_metrics() -> Dict:
    """
    Convenience function to get risk metrics
    
    Returns:
        Risk metrics dict
    """
    aggregator = RiskAggregator()
    return aggregator.get_portfolio_risk_metrics()