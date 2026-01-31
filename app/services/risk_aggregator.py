"""
Risk Aggregation Service - Calculate sector and geography breakdowns

Save this as: app/services/risk_aggregator.py
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
                'sectors': {...},        # Sector breakdown
                'geography': {...},      # Geographic breakdown
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
            
            # Calculate concentration (top holdings)
            concentration = self._calculate_concentration(holdings, total_value)
            
            # Calculate sector breakdown
            sectors = self._calculate_sector_breakdown(holdings, total_value)
            
            # Calculate geography breakdown
            geography = self._calculate_geography_breakdown(holdings, total_value)
            
            # Determine overall risk
            overall_risk = self._calculate_overall_risk(concentration)
            
            return {
                'concentration': concentration,
                'sectors': sectors,
                'geography': geography,
                'overall_risk': overall_risk,
                'total_value': total_value
            }
    
    def _get_latest_snapshots(self, session) -> List[PortfolioSnapshot]:
        """Get the most recent snapshot for each active broker"""
        latest_snapshots = []
        accounts = session.query(BrokerAccount).filter_by(is_active=True).all()
        
        for account in accounts:
            snapshot = session.query(PortfolioSnapshot).filter_by(
                broker_account_id=account.id
            ).order_by(desc(PortfolioSnapshot.snapshot_date)).first()
            
            if snapshot:
                latest_snapshots.append(snapshot)
        
        return latest_snapshots

    def _calculate_concentration(self, holdings: List[Holding], total_value: float) -> List[Dict]:
        """
        Calculate concentration - ONLY return stocks exceeding threshold
        Includes both direct holdings and underlying holdings from ETFs/MFs
        """
        from collections import defaultdict
        
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
        """
        from app.services.stock_info_service import StockInfoService
        from collections import defaultdict
        
        service = StockInfoService()
        sector_totals = defaultdict(float)
        
        for holding in holdings:
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
        for sector, value in sector_totals.items():
            pct = (value / total_value * 100) if total_value > 0 else 0
            if pct >= 0.1:  # Include sectors with at least 0.1%
                sector_percentages[sector] = round(pct, 1)
        
        # Sort by percentage descending
        sector_percentages = dict(sorted(
            sector_percentages.items(),
            key=lambda x: x[1],
            reverse=True
        ))
        
        logger.info(f"Sector breakdown: {sector_percentages}")
        return sector_percentages


    def _calculate_geography_breakdown(self, holdings: List[Holding], total_value: float) -> Dict[str, float]:
        """
        Calculate geographic allocation breakdown
        Includes both direct holdings AND underlying holdings from ETFs/MFs
        """
        from app.services.stock_info_service import StockInfoService
        from collections import defaultdict
        
        service = StockInfoService()
        geo_totals = defaultdict(float)
        
        for holding in holdings:
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
        for geo, value in geo_totals.items():
            pct = (value / total_value * 100) if total_value > 0 else 0
            if pct >= 0.1:  # Include regions with at least 0.1%
                geo_percentages[geo] = round(pct, 1)
        
        # Sort by percentage descending
        geo_percentages = dict(sorted(
            geo_percentages.items(),
            key=lambda x: x[1],
            reverse=True
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
            'total_value': 0
        }


def get_risk_metrics() -> Dict:
    """
    Convenience function to get risk metrics
    
    Returns:
        Risk metrics dict
    """
    aggregator = RiskAggregator()
    return aggregator.get_portfolio_risk_metrics()