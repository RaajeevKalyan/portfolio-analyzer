"""
Updated Holdings Resolver - Fetches sector/country for underlying holdings

Replace app/services/holdings_resolver.py with this version
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
import mstarpy
import pandas as pd
from app.services.stock_info_service import get_stock_info
import time

logger = logging.getLogger(__name__)


class HoldingsResolver:
    """Resolve ETF/Mutual Fund underlying holdings and fetch sector data"""
    
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
        """
        if asset_type not in ['etf', 'mutual_fund']:
            logger.debug(f"Skipping {symbol} - not an ETF or mutual fund (type: {asset_type})")
            return None
        
        logger.info(f"Resolving underlying holdings for {symbol} ({asset_type})...")
        
        try:
            # Initialize mstarpy Funds object
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
                    # Extract ticker symbol
                    ticker = None
                    if 'ticker' in row and pd.notna(row['ticker']) and str(row['ticker']).strip():
                        ticker = str(row['ticker']).strip().upper()
                    elif 'secId' in row and pd.notna(row['secId']) and str(row['secId']).strip():
                        ticker = str(row['secId']).strip().upper()
                    
                    # Get name
                    name = str(row['securityName']).strip() if pd.notna(row.get('securityName')) else ''
                    
                    # Get weight (percentage format, e.g., 3.70392 = 3.70%)
                    weight = float(row['weighting']) if pd.notna(row.get('weighting')) else 0.0
                    
                    # Skip if no ticker or weight
                    if not ticker or weight == 0:
                        continue
                    
                    # Convert weight to decimal
                    weight_decimal = weight / 100.0
                    
                    # Calculate estimated value based on weight
                    estimated_value = float(total_value) * weight_decimal
                    
                    underlying.append({
                        'symbol': ticker,
                        'name': name or ticker,
                        'weight': round(weight_decimal, 6),
                        'value': round(estimated_value, 2),
                        'shares': None
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


def fetch_stock_info_for_holding(holding) -> bool:
    """
    Fetch sector/geography information for a holding using mstarpy
    
    Args:
        holding: Holding model object
        
    Returns:
        bool: True if successful
    """
    if holding.info_fetched:
        logger.debug(f"Info already fetched for {holding.symbol}, skipping")
        return True
    
    try:
        logger.info(f"Fetching sector/geography info for {holding.symbol}")
        stock_info = get_stock_info(holding.symbol)
        
        if stock_info:
            holding.sector = stock_info.get('sector')
            holding.industry = stock_info.get('industry')
            holding.country = stock_info.get('country')
            holding.info_fetched = True
            logger.info(f"✓ Info fetched for {holding.symbol}: {stock_info.get('sector')} / {stock_info.get('country')}")
            return True
        else:
            logger.warning(f"Could not fetch info for {holding.symbol}")
            holding.info_fetched = True
            return False
            
    except Exception as e:
        logger.error(f"Error fetching info for {holding.symbol}: {e}")
        holding.info_fetched = True
        return False


def fetch_sector_info_for_underlying_holdings(holding) -> int:
    """
    Fetch sector/geography info for all underlying holdings of an ETF/MF
    
    Args:
        holding: Holding model object with underlying_holdings_list
        
    Returns:
        Number of underlying holdings successfully enriched with sector data
    """
    if not holding.underlying_holdings_list:
        logger.debug(f"No underlying holdings for {holding.symbol}")
        return 0
    
    try:
        logger.info(f"Fetching sector info for {len(holding.underlying_holdings_list)} underlying holdings in {holding.symbol}")
        
        enriched_count = 0
        
        for underlying in holding.underlying_holdings_list:
            # Check if we already have sector info
            if 'sector' in underlying and underlying['sector'] != 'Unknown':
                enriched_count += 1
                continue
            
            # Fetch sector info for this underlying holding
            symbol = underlying['symbol']
            stock_info = get_stock_info(symbol)
            
            if stock_info:
                # Add sector/country data to underlying holding
                underlying['sector'] = stock_info.get('sector', 'Unknown')
                underlying['industry'] = stock_info.get('industry', 'Unknown')
                underlying['country'] = stock_info.get('country', 'Unknown')
                underlying['geography'] = stock_info.get('geography', 'Unknown')
                enriched_count += 1
                
                # Small delay to be respectful to Morningstar
                time.sleep(0.1)
        
        # Update the holding with enriched data
        # The property setter will handle JSON serialization
        holding.underlying_holdings_list = holding.underlying_holdings_list
        
        logger.info(f"Enriched {enriched_count}/{len(holding.underlying_holdings_list)} underlying holdings for {holding.symbol}")
        return enriched_count
        
    except Exception as e:
        logger.error(f"Error enriching underlying holdings for {holding.symbol}: {e}")
        return 0


def resolve_snapshot_holdings(snapshot_id: int) -> int:
    """
    Resolve all ETF/MF holdings for a given snapshot
    AND fetch sector/geography info for ALL holdings (including underlying)
    
    Args:
        snapshot_id: Portfolio snapshot ID
        
    Returns:
        Number of holdings successfully resolved
    """
    from app.database import db_session
    from app.models import Holding
    
    logger.info(f"Starting holdings resolution for snapshot {snapshot_id}")
    
    with db_session() as session:
        # Get all holdings for this snapshot
        all_holdings = session.query(Holding).filter(
            Holding.portfolio_snapshot_id == snapshot_id
        ).all()
        
        if not all_holdings:
            logger.info(f"No holdings found for snapshot {snapshot_id}")
            return 0
        
        # Separate ETF/MF from regular stocks
        etf_mf_holdings = [h for h in all_holdings 
                          if h.asset_type in ['etf', 'mutual_fund'] and not h.underlying_parsed]
        
        logger.info(f"Found {len(all_holdings)} total holdings ({len(etf_mf_holdings)} ETF/MF to resolve)")
        
        # Resolve ETF/MF underlying holdings
        resolved_count = 0
        
        if etf_mf_holdings:
            # Prepare data for resolver
            holdings_data = [
                {
                    'id': h.id,
                    'symbol': h.symbol,
                    'asset_type': h.asset_type,
                    'total_value': h.total_value
                }
                for h in etf_mf_holdings
            ]
            
            # Resolve holdings
            resolver = HoldingsResolver()
            results = resolver.resolve_multiple_holdings(holdings_data)
            
            # Update database with results
            for holding in etf_mf_holdings:
                if holding.id in results:
                    # Store underlying holdings as JSON
                    holding.underlying_holdings_list = results[holding.id]
                    holding.underlying_parsed = True
                    resolved_count += 1
                    logger.info(f"Stored {len(results[holding.id])} underlying holdings for {holding.symbol}")
                else:
                    # Mark as parsed even if failed
                    holding.underlying_parsed = True
                    logger.warning(f"Failed to resolve {holding.symbol}, marking as parsed")
            
            # Commit after resolving underlying holdings
            session.commit()
            logger.info(f"Successfully resolved {resolved_count}/{len(etf_mf_holdings)} ETF/MF holdings")
        
        # Fetch sector/geography info for ALL holdings (parent holdings)
        info_fetched_count = 0
        holdings_needing_info = [h for h in all_holdings if not h.info_fetched]
        
        if holdings_needing_info:
            logger.info(f"Fetching sector/geography info for {len(holdings_needing_info)} parent holdings...")
            
            for holding in holdings_needing_info:
                if fetch_stock_info_for_holding(holding):
                    info_fetched_count += 1
                time.sleep(0.1)  # Small delay
            
            # Commit after fetching parent info
            session.commit()
            logger.info(f"Successfully fetched info for {info_fetched_count}/{len(holdings_needing_info)} parent holdings")
        
        # NEW: Fetch sector info for UNDERLYING holdings
        underlying_enriched_count = 0
        etf_mf_with_underlying = [h for h in all_holdings 
                                  if h.asset_type in ['etf', 'mutual_fund'] and h.underlying_holdings_list]
        
        if etf_mf_with_underlying:
            logger.info(f"Fetching sector info for underlying holdings in {len(etf_mf_with_underlying)} ETFs/MFs...")
            
            for holding in etf_mf_with_underlying:
                enriched = fetch_sector_info_for_underlying_holdings(holding)
                underlying_enriched_count += enriched
            
            # Commit after enriching underlying holdings
            session.commit()
            logger.info(f"Enriched {underlying_enriched_count} total underlying holdings")
        
        logger.info(f"Snapshot {snapshot_id} complete: {resolved_count} ETF/MF resolved, " +
                   f"{info_fetched_count} parent info fetched, {underlying_enriched_count} underlying enriched")
    
    return resolved_count


def resolve_all_unresolved_holdings() -> int:
    """
    Resolve ALL unresolved ETF/MF holdings across all snapshots
    AND fetch sector/geography info for all holdings
    """
    from app.database import db_session
    from app.models import Holding
    
    logger.info("Starting global holdings resolution")
    
    with db_session() as session:
        # Get all unresolved ETF/MF holdings
        unresolved_etf_mf = session.query(Holding).filter(
            Holding.asset_type.in_(['etf', 'mutual_fund']),
            Holding.underlying_parsed == False
        ).all()
        
        # Get all holdings missing sector/geography info
        holdings_needing_info = session.query(Holding).filter(
            Holding.info_fetched == False
        ).all()
        
        logger.info(f"Found {len(unresolved_etf_mf)} unresolved ETF/MF holdings")
        logger.info(f"Found {len(holdings_needing_info)} holdings needing sector/geography info")
        
        if not unresolved_etf_mf and not holdings_needing_info:
            logger.info("Nothing to resolve")
            return 0
        
        # Group by snapshot
        snapshots_to_process = set()
        
        for h in unresolved_etf_mf:
            snapshots_to_process.add(h.portfolio_snapshot_id)
        
        for h in holdings_needing_info:
            snapshots_to_process.add(h.portfolio_snapshot_id)
        
        logger.info(f"Processing {len(snapshots_to_process)} snapshots...")
        
        total_resolved = 0
        
        for snapshot_id in snapshots_to_process:
            logger.info(f"Processing snapshot {snapshot_id}")
            resolved = resolve_snapshot_holdings(snapshot_id)
            total_resolved += resolved
        
        logger.info(f"Global resolution complete: {total_resolved} ETF/MF holdings resolved")
        
    return total_resolved