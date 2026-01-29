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
        Calculate concentration by aggregating same symbols across brokers
        STOCKS ONLY - excludes ETFs and mutual funds
        
        Returns top 5 holdings with allocation percentage
        """
        # Filter to stocks only (exclude ETFs and mutual funds)
        stock_holdings = [h for h in holdings if h.asset_type == 'stock']
        
        if not stock_holdings:
            logger.debug("No stock holdings found for concentration analysis")
            return []
        
        # Aggregate by symbol
        symbol_totals = defaultdict(lambda: {
            'symbol': '',
            'name': '',
            'value': 0,
            'allocation_pct': 0,
            'asset_type': 'stock'
        })
        
        for holding in stock_holdings:
            symbol = holding.symbol
            symbol_totals[symbol]['symbol'] = symbol
            symbol_totals[symbol]['name'] = holding.name or symbol
            symbol_totals[symbol]['value'] += float(holding.total_value)
            symbol_totals[symbol]['asset_type'] = holding.asset_type
        
        # Calculate allocation percentages
        for data in symbol_totals.values():
            data['allocation_pct'] = (data['value'] / total_value * 100) if total_value > 0 else 0
        
        # Sort by value and get top 5
        top_holdings = sorted(
            symbol_totals.values(),
            key=lambda x: x['value'],
            reverse=True
        )[:5]
        
        return top_holdings
    
    def _calculate_sector_breakdown(self, holdings: List[Holding], total_value: float) -> Dict[str, float]:
        """
        Calculate sector allocation breakdown
        
        Returns dict mapping sector name to percentage
        """
        sector_totals = defaultdict(float)
        
        for holding in holdings:
            sector = holding.sector or 'Unknown'
            sector_totals[sector] += float(holding.total_value)
        
        # Convert to percentages
        sector_percentages = {}
        for sector, value in sector_totals.items():
            pct = (value / total_value * 100) if total_value > 0 else 0
            if pct >= 1.0:  # Only include sectors with at least 1%
                sector_percentages[sector] = round(pct, 1)
        
        # Sort by percentage descending
        sector_percentages = dict(sorted(
            sector_percentages.items(),
            key=lambda x: x[1],
            reverse=True
        ))
        
        return sector_percentages
    
    def _calculate_geography_breakdown(self, holdings: List[Holding], total_value: float) -> Dict[str, float]:
        """
        Calculate geographic allocation breakdown
        
        Returns dict mapping geography to percentage
        """
        from app.services.stock_info_service import StockInfoService
        
        geo_service = StockInfoService()
        geo_totals = defaultdict(float)
        
        for holding in holdings:
            country = holding.country or 'Unknown'
            geography = geo_service._map_country_to_geography(country)
            geo_totals[geography] += float(holding.total_value)
        
        # Convert to percentages
        geo_percentages = {}
        for geo, value in geo_totals.items():
            pct = (value / total_value * 100) if total_value > 0 else 0
            if pct >= 1.0:  # Only include regions with at least 1%
                geo_percentages[geo] = round(pct, 1)
        
        # Sort by percentage descending
        geo_percentages = dict(sorted(
            geo_percentages.items(),
            key=lambda x: x[1],
            reverse=True
        ))
        
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