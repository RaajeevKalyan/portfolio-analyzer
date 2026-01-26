"""
Holdings Resolver Service

Resolves underlying holdings for ETFs and Mutual Funds using mstarpy.
Updated for mstarpy 8.0.3 API
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
import mstarpy
import pandas as pd

logger = logging.getLogger(__name__)


class HoldingsResolver:
    """Resolve ETF/Mutual Fund underlying holdings"""
    
    def __init__(self):
        pass
    
    def resolve_holding(self, symbol: str, asset_type: str, total_value: Decimal) -> Optional[List[Dict]]:
        """
        Resolve underlying holdings for an ETF or Mutual Fund
        
        Args:
            symbol: Ticker symbol (e.g., 'VTI', 'DBMAX')
            asset_type: Type of asset ('etf' or 'mutual_fund')
            total_value: Total value of the holding (for calculating weighted values)
            
        Returns:
            List of dicts with underlying holdings, or None if failed
            Format: [
                {
                    'symbol': 'AAPL',
                    'name': 'Apple Inc.',
                    'weight': 0.0712,  # 7.12%
                    'value': 1234.56,   # Estimated value based on weight
                    'shares': None      # Not directly provided
                },
                ...
            ]
        """
        if asset_type not in ['etf', 'mutual_fund']:
            logger.debug(f"Skipping {symbol} - not an ETF or mutual fund (type: {asset_type})")
            return None
        
        logger.info(f"Resolving underlying holdings for {symbol} ({asset_type})...")
        
        try:
            # Initialize mstarpy Funds object (8.0.3 API)
            fund = mstarpy.Funds(term=symbol, pageSize=1)
            
            # Get portfolio holdings
            holdings_df = fund.holdings()
            
            if holdings_df is None or holdings_df.empty:
                logger.warning(f"No holdings data found for {symbol}")
                return None
            
            logger.info(f"Found {len(holdings_df)} holdings for {symbol}")
            
            # Process holdings DataFrame
            underlying = []
            
            for idx, row in holdings_df.iterrows():
                try:
                    # Extract data from DataFrame row
                    # Try ticker first, fall back to secId
                    ticker = None
                    if 'ticker' in row and pd.notna(row['ticker']) and str(row['ticker']).strip():
                        ticker = str(row['ticker']).strip().upper()
                    elif 'secId' in row and pd.notna(row['secId']) and str(row['secId']).strip():
                        ticker = str(row['secId']).strip().upper()
                    
                    # Get name
                    name = str(row['securityName']).strip() if pd.notna(row.get('securityName')) else ''
                    
                    # Get weight (already in percentage format, e.g., 3.70392 = 3.70%)
                    weight = float(row['weighting']) if pd.notna(row.get('weighting')) else 0.0
                    
                    # Skip if no ticker or weight
                    if not ticker or weight == 0:
                        continue
                    
                    # Convert weight to decimal (mstarpy 8.0.3 returns percentage)
                    weight_decimal = weight / 100.0
                    
                    # Calculate estimated value based on weight
                    estimated_value = float(total_value) * weight_decimal
                    
                    underlying.append({
                        'symbol': ticker,
                        'name': name or ticker,
                        'weight': round(weight_decimal, 6),  # Store as decimal (0.0370 = 3.70%)
                        'value': round(estimated_value, 2),
                        'shares': None  # Not directly provided by mstarpy
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing holding row in {symbol}: {e}")
                    continue
            
            if len(underlying) == 0:
                logger.warning(f"No valid holdings extracted for {symbol}")
                return None
            
            # Sort by weight descending
            underlying.sort(key=lambda x: x['weight'], reverse=True)

            logger.info(f"Successfully resolved {len(underlying)} holdings for {symbol}")
            top_5 = [(h['symbol'], round(h['weight']*100, 2)) for h in underlying[:5]]
            logger.debug(f"Top 5 holdings for {symbol}: {top_5}")

            return underlying
                    
        except Exception as e:
            logger.error(f"Error resolving holdings for {symbol}: {e}")
            logger.exception(e)
            return None
    
    def resolve_multiple_holdings(self, holdings: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Resolve multiple holdings in batch
        
        Args:
            holdings: List of dicts with keys: id, symbol, asset_type, total_value
            
        Returns:
            Dict mapping holding_id to underlying holdings list
            {
                123: [{symbol: 'AAPL', weight: 0.05, ...}, ...],
                124: [{symbol: 'MSFT', weight: 0.03, ...}, ...],
                ...
            }
        """
        results = {}
        
        for holding in holdings:
            holding_id = holding['id']
            symbol = holding['symbol']
            asset_type = holding['asset_type']
            total_value = holding['total_value']
            
            logger.info(f"Processing holding {holding_id}: {symbol} ({asset_type})")
            
            underlying = self.resolve_holding(symbol, asset_type, total_value)
            
            if underlying:
                results[holding_id] = underlying
                logger.info(f"Resolved {len(underlying)} underlying holdings for {symbol}")
            else:
                logger.warning(f"Could not resolve holdings for {symbol}")
        
        return results


def resolve_snapshot_holdings(snapshot_id: int) -> int:
    """
    Resolve all ETF/MF holdings for a given snapshot
    
    Args:
        snapshot_id: Portfolio snapshot ID
        
    Returns:
        Number of holdings successfully resolved
    """
    from app.database import db_session
    from app.models import Holding
    
    logger.info(f"Starting holdings resolution for snapshot {snapshot_id}")
    
    with db_session() as session:
        # Get all ETF/MF holdings that haven't been parsed yet
        holdings = session.query(Holding).filter(
            Holding.portfolio_snapshot_id == snapshot_id,
            Holding.asset_type.in_(['etf', 'mutual_fund']),
            Holding.underlying_parsed == False
        ).all()
        
        if not holdings:
            logger.info(f"No unresolved ETF/MF holdings found for snapshot {snapshot_id}")
            return 0
        
        logger.info(f"Found {len(holdings)} ETF/MF holdings to resolve")
        
        # Prepare data for resolver
        holdings_data = [
            {
                'id': h.id,
                'symbol': h.symbol,
                'asset_type': h.asset_type,
                'total_value': h.total_value
            }
            for h in holdings
        ]
        
        # Resolve holdings
        resolver = HoldingsResolver()
        results = resolver.resolve_multiple_holdings(holdings_data)
        
        # Update database with results
        resolved_count = 0
        
        for holding in holdings:
            if holding.id in results:
                # Store underlying holdings as JSON
                holding.underlying_holdings_list = results[holding.id]
                holding.underlying_parsed = True
                resolved_count += 1
                logger.info(f"Stored {len(results[holding.id])} underlying holdings for {holding.symbol}")
            else:
                # Mark as parsed even if failed (to avoid retrying indefinitely)
                holding.underlying_parsed = True
                logger.warning(f"Failed to resolve {holding.symbol}, marking as parsed to skip future attempts")
        
        logger.info(f"Successfully resolved {resolved_count}/{len(holdings)} ETF/MF holdings")
        
    return resolved_count


def resolve_all_unresolved_holdings() -> int:
    """
    Resolve ALL unresolved ETF/MF holdings across all snapshots
    
    Useful for backfilling or fixing data
    
    Returns:
        Total number of holdings resolved
    """
    from app.database import db_session
    from app.models import Holding
    
    logger.info("Starting global holdings resolution")
    
    with db_session() as session:
        # Get all unresolved ETF/MF holdings
        holdings = session.query(Holding).filter(
            Holding.asset_type.in_(['etf', 'mutual_fund']),
            Holding.underlying_parsed == False
        ).all()
        
        if not holdings:
            logger.info("No unresolved ETF/MF holdings found")
            return 0
        
        logger.info(f"Found {len(holdings)} unresolved ETF/MF holdings across all snapshots")
        
        # Group by snapshot for better logging
        by_snapshot = {}
        for h in holdings:
            by_snapshot.setdefault(h.portfolio_snapshot_id, []).append(h)
        
        total_resolved = 0
        
        for snapshot_id, snapshot_holdings in by_snapshot.items():
            logger.info(f"Resolving {len(snapshot_holdings)} holdings for snapshot {snapshot_id}")
            resolved = resolve_snapshot_holdings(snapshot_id)
            total_resolved += resolved
        
        logger.info(f"Global resolution complete: {total_resolved} holdings resolved")
        
    return total_resolved