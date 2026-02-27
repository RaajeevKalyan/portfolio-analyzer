"""
Database Query Utilities - Optimized SQL Queries

Provides efficient SQL queries for common operations:
- Getting latest snapshots (single query instead of N+1)
- Aggregating holdings by symbol
- Filtering by asset type

These replace the N+1 query patterns found throughout the codebase.
"""
from sqlalchemy import func, desc
from sqlalchemy.orm import joinedload
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def get_latest_snapshot_ids(session) -> List[int]:
    """
    Get the latest snapshot ID for each active broker in a SINGLE query.
    
    This replaces the N+1 pattern of:
        accounts = query(BrokerAccount).all()
        for account in accounts:
            snapshot = query(PortfolioSnapshot).filter_by(broker_account_id=account.id).first()
    
    Returns:
        List of snapshot IDs
    """
    from app.models import BrokerAccount, PortfolioSnapshot
    
    # Subquery: get max snapshot date per broker
    subq = session.query(
        PortfolioSnapshot.broker_account_id,
        func.max(PortfolioSnapshot.snapshot_date).label('max_date')
    ).group_by(PortfolioSnapshot.broker_account_id).subquery()
    
    # Main query: join to get snapshot IDs for active brokers only
    snapshots = session.query(PortfolioSnapshot.id).join(
        subq,
        (PortfolioSnapshot.broker_account_id == subq.c.broker_account_id) &
        (PortfolioSnapshot.snapshot_date == subq.c.max_date)
    ).join(
        BrokerAccount,
        BrokerAccount.id == PortfolioSnapshot.broker_account_id
    ).filter(
        BrokerAccount.is_active == True
    ).all()
    
    return [s[0] for s in snapshots]


def get_latest_snapshots(session) -> List:
    """
    Get the latest PortfolioSnapshot objects for each active broker in a SINGLE query.
    
    Returns:
        List of PortfolioSnapshot objects with broker_account eager-loaded
    """
    from app.models import BrokerAccount, PortfolioSnapshot
    
    # Subquery: get max snapshot date per broker
    subq = session.query(
        PortfolioSnapshot.broker_account_id,
        func.max(PortfolioSnapshot.snapshot_date).label('max_date')
    ).group_by(PortfolioSnapshot.broker_account_id).subquery()
    
    # Main query with eager loading
    snapshots = session.query(PortfolioSnapshot).options(
        joinedload(PortfolioSnapshot.broker_account)
    ).join(
        subq,
        (PortfolioSnapshot.broker_account_id == subq.c.broker_account_id) &
        (PortfolioSnapshot.snapshot_date == subq.c.max_date)
    ).join(
        BrokerAccount,
        BrokerAccount.id == PortfolioSnapshot.broker_account_id
    ).filter(
        BrokerAccount.is_active == True
    ).all()
    
    return snapshots


def get_holdings_by_snapshot_ids(session, snapshot_ids: List[int], asset_types: Optional[List[str]] = None):
    """
    Get all holdings for given snapshot IDs, optionally filtered by asset type.
    
    Args:
        session: Database session
        snapshot_ids: List of snapshot IDs to query
        asset_types: Optional list of asset types to filter (e.g., ['stock'], ['etf', 'mutual_fund'])
        
    Returns:
        List of Holding objects
    """
    from app.models import Holding
    
    if not snapshot_ids:
        return []
    
    query = session.query(Holding).filter(
        Holding.portfolio_snapshot_id.in_(snapshot_ids)
    )
    
    if asset_types:
        query = query.filter(Holding.asset_type.in_(asset_types))
    
    return query.all()


def get_aggregated_holdings_by_symbol(session, snapshot_ids: List[int], asset_types: Optional[List[str]] = None) -> List[Dict]:
    """
    Get holdings aggregated by symbol using SQL GROUP BY.
    
    Much more efficient than loading all holdings and aggregating in Python.
    
    Args:
        session: Database session
        snapshot_ids: List of snapshot IDs to query
        asset_types: Optional list of asset types to filter
        
    Returns:
        List of dicts with symbol, name, total_value, total_quantity, asset_type, sector, country
    """
    from app.models import Holding
    
    if not snapshot_ids:
        return []
    
    query = session.query(
        Holding.symbol,
        Holding.name,
        Holding.asset_type,
        Holding.sector,
        Holding.country,
        func.sum(Holding.total_value).label('total_value'),
        func.sum(Holding.quantity).label('total_quantity')
    ).filter(
        Holding.portfolio_snapshot_id.in_(snapshot_ids)
    )
    
    if asset_types:
        query = query.filter(Holding.asset_type.in_(asset_types))
    
    results = query.group_by(
        Holding.symbol
    ).order_by(
        desc('total_value')
    ).all()
    
    return [{
        'symbol': r.symbol,
        'name': r.name,
        'asset_type': r.asset_type,
        'sector': r.sector or '',
        'country': r.country or '',
        'total_value': float(r.total_value) if r.total_value else 0,
        'total_quantity': float(r.total_quantity) if r.total_quantity else 0
    } for r in results]


def get_top_holdings_by_value(session, snapshot_ids: List[int], asset_types: Optional[List[str]] = None, limit: int = 50) -> List[Dict]:
    """
    Get top N holdings by total value, aggregated by symbol.
    
    Args:
        session: Database session
        snapshot_ids: List of snapshot IDs
        asset_types: Optional asset type filter
        limit: Maximum number of results
        
    Returns:
        List of top holdings dicts
    """
    from app.models import Holding
    
    if not snapshot_ids:
        return []
    
    query = session.query(
        Holding.symbol,
        Holding.name,
        Holding.asset_type,
        Holding.sector,
        Holding.country,
        func.sum(Holding.total_value).label('total_value'),
        func.sum(Holding.quantity).label('total_quantity')
    ).filter(
        Holding.portfolio_snapshot_id.in_(snapshot_ids)
    )
    
    if asset_types:
        query = query.filter(Holding.asset_type.in_(asset_types))
    
    results = query.group_by(
        Holding.symbol
    ).order_by(
        desc('total_value')
    ).limit(limit).all()
    
    return [{
        'symbol': r.symbol,
        'name': r.name,
        'asset_type': r.asset_type,
        'sector': r.sector or '',
        'country': r.country or '',
        'total_value': float(r.total_value) if r.total_value else 0,
        'total_quantity': float(r.total_quantity) if r.total_quantity else 0
    } for r in results]


def get_portfolio_summary(session, snapshot_ids: List[int]) -> Dict:
    """
    Get portfolio summary (total value, cash, investments) in a single query.
    
    Returns:
        Dict with total_value, cash_value, investment_value, holding_count
    """
    from app.models import Holding
    
    if not snapshot_ids:
        return {
            'total_value': 0,
            'cash_value': 0,
            'investment_value': 0,
            'holding_count': 0
        }
    
    # Single query for all summaries
    result = session.query(
        func.sum(Holding.total_value).label('total_value'),
        func.sum(
            func.case(
                (Holding.asset_type == 'cash', Holding.total_value),
                else_=0
            )
        ).label('cash_value'),
        func.count(Holding.id).label('holding_count')
    ).filter(
        Holding.portfolio_snapshot_id.in_(snapshot_ids)
    ).first()
    
    total_value = float(result.total_value) if result.total_value else 0
    cash_value = float(result.cash_value) if result.cash_value else 0
    
    return {
        'total_value': total_value,
        'cash_value': cash_value,
        'investment_value': total_value - cash_value,
        'holding_count': result.holding_count or 0
    }