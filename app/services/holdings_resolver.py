"""
Holdings Resolver Service - FINAL FIX

The fix: Write directly to holding.underlying_holdings (TEXT column)
instead of using the property holding.underlying_holdings_list
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
import mstarpy
import pandas as pd
import json

logger = logging.getLogger(__name__)


class HoldingsResolver:
    """Resolve ETF/Mutual Fund underlying holdings"""
    
    def __init__(self):
        pass
    
    def resolve_holding(self, symbol: str, asset_type: str, total_value: Decimal) -> Optional[List[Dict]]:
        """Resolve underlying holdings for an ETF or Mutual Fund"""
        if asset_type not in ['etf', 'mutual_fund']:
            logger.debug(f"Skipping {symbol} - not an ETF or mutual fund (type: {asset_type})")
            return None
        
        logger.info(f"Resolving underlying holdings for {symbol} ({asset_type})...")
        
        try:
            fund = mstarpy.Funds(term=symbol, pageSize=1)
            holdings_df = fund.holdings()
            
            if holdings_df is None or holdings_df.empty:
                logger.warning(f"No holdings data found for {symbol}")
                return None
            
            logger.info(f"Found {len(holdings_df)} holdings for {symbol}")
            
            underlying = []
            
            for idx, row in holdings_df.iterrows():
                try:
                    ticker = None
                    if 'ticker' in row and pd.notna(row['ticker']) and str(row['ticker']).strip():
                        ticker = str(row['ticker']).strip().upper()
                    elif 'secId' in row and pd.notna(row['secId']) and str(row['secId']).strip():
                        ticker = str(row['secId']).strip().upper()
                    
                    name = str(row['securityName']).strip() if pd.notna(row.get('securityName')) else ''
                    weight = float(row['weighting']) if pd.notna(row.get('weighting')) else 0.0
                    
                    if not ticker or weight == 0:
                        continue
                    
                    weight_decimal = weight / 100.0
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
            
            underlying.sort(key=lambda x: x['weight'], reverse=True)
            logger.info(f"Successfully resolved {len(underlying)} holdings for {symbol}")
            
            return underlying
                    
        except Exception as e:
            logger.error(f"Error resolving holdings for {symbol}: {e}")
            logger.exception(e)
            return None
    
    def resolve_multiple_holdings(self, holdings: List[Dict]) -> Dict[int, List[Dict]]:
        """Resolve multiple holdings in batch"""
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
    """Fetch sector/geography information for a holding using yfinance"""
    from app.services.stock_info_service import get_stock_info
    
    if holding.info_fetched:
        logger.debug(f"Info already fetched for {holding.symbol}, skipping")
        return True
    
    try:
        logger.info(f"Fetching sector/geography info for {holding.symbol}")
        stock_info = get_stock_info(holding.symbol)
        
        if stock_info:
            holding.sector = stock_info.get('sector', 'Unknown')
            holding.industry = stock_info.get('industry', 'Unknown')
            holding.country = stock_info.get('country', 'Unknown')
            holding.info_fetched = True
            
            logger.info(f"✓ Saved info for {holding.symbol}: sector={holding.sector}, country={holding.country}")
            return True
        else:
            logger.warning(f"No info returned for {holding.symbol}")
            holding.sector = 'Unknown'
            holding.industry = 'Unknown'
            holding.country = 'Unknown'
            holding.info_fetched = True
            return False
            
    except Exception as e:
        logger.error(f"Error fetching info for {holding.symbol}: {e}")
        logger.exception(e)
        holding.sector = 'Unknown'
        holding.industry = 'Unknown'
        holding.country = 'Unknown'
        holding.info_fetched = True
        return False


def fetch_sector_info_for_underlying_holdings(holding) -> int:
    """
    Fetch sector/geography info for all underlying holdings of an ETF/MF
    
    CRITICAL FIX: Writes directly to holding.underlying_holdings (TEXT column)
    """
    from app.services.stock_info_service import get_stock_info
    
    if not holding.underlying_holdings_list:
        logger.debug(f"No underlying holdings for {holding.symbol}")
        return 0
    
    try:
        # Get the list (creates a copy)
        underlying_list = holding.underlying_holdings_list
        total_underlying = len(underlying_list)
        
        logger.info(f"=" * 80)
        logger.info(f"STARTING: Fetching sector info for {total_underlying} underlying holdings in {holding.symbol}")
        logger.info(f"=" * 80)
        
        enriched_count = 0
        skipped_count = 0
        
        for idx, underlying in enumerate(underlying_list, 1):
            if 'sector' in underlying and underlying.get('sector') not in [None, 'Unknown', '', 'NOT SET']:
                logger.debug(f"  [{idx}/{total_underlying}] {underlying['symbol']} - sector already exists: {underlying.get('sector')}")
                enriched_count += 1
                skipped_count += 1
                continue
            
            symbol = underlying['symbol']
            logger.info(f"  [{idx}/{total_underlying}] Fetching sector for {symbol}...")
            
            stock_info = get_stock_info(symbol)
            
            if stock_info:
                underlying['sector'] = stock_info.get('sector', 'Unknown')
                underlying['industry'] = stock_info.get('industry', 'Unknown')
                underlying['country'] = stock_info.get('country', 'Unknown')
                underlying['geography'] = stock_info.get('geography', 'Unknown')
                enriched_count += 1
                logger.info(f"  [{idx}/{total_underlying}] ✓ {symbol}: sector={underlying['sector']}, country={underlying['country']}")
            else:
                logger.warning(f"  [{idx}/{total_underlying}] ✗ No info returned for {symbol}")
                underlying['sector'] = 'Unknown'
                underlying['industry'] = 'Unknown'
                underlying['country'] = 'Unknown'
                underlying['geography'] = 'Unknown'
        
        # CRITICAL FIX: Write directly to the TEXT column
        holding.underlying_holdings = json.dumps(underlying_list)
        
        logger.info(f"=" * 80)
        logger.info(f"COMPLETED: {holding.symbol} - Enriched {enriched_count}/{total_underlying} underlying holdings ({skipped_count} already had data)")
        logger.info(f"=" * 80)
        return enriched_count
        
    except Exception as e:
        logger.error(f"Error enriching underlying holdings for {holding.symbol}: {e}")
        logger.exception(e)
        return 0


def resolve_snapshot_holdings(snapshot_id: int) -> int:
    """Resolve all ETF/MF holdings for a given snapshot"""
    from app.database import db_session
    from app.models import Holding
    
    logger.info(f"Starting holdings resolution for snapshot {snapshot_id}")
    
    with db_session() as session:
        all_holdings = session.query(Holding).filter(
            Holding.portfolio_snapshot_id == snapshot_id
        ).all()
        
        if not all_holdings:
            logger.info(f"No holdings found for snapshot {snapshot_id}")
            return 0
        
        etf_mf_holdings = [h for h in all_holdings 
                          if h.asset_type in ['etf', 'mutual_fund'] and not h.underlying_parsed]
        
        logger.info(f"Found {len(all_holdings)} total holdings ({len(etf_mf_holdings)} ETF/MF to resolve)")
        
        # STEP 1: Resolve ETF/MF underlying holdings
        resolved_count = 0
        
        if etf_mf_holdings:
            holdings_data = [
                {
                    'id': h.id,
                    'symbol': h.symbol,
                    'asset_type': h.asset_type,
                    'total_value': h.total_value
                }
                for h in etf_mf_holdings
            ]
            
            resolver = HoldingsResolver()
            results = resolver.resolve_multiple_holdings(holdings_data)
            
            for holding in etf_mf_holdings:
                if holding.id in results:
                    holding.underlying_holdings_list = results[holding.id]
                    holding.underlying_parsed = True
                    resolved_count += 1
                    logger.info(f"Stored {len(results[holding.id])} underlying holdings for {holding.symbol}")
                else:
                    holding.underlying_parsed = True
                    logger.warning(f"Failed to resolve {holding.symbol}, marking as parsed")
            
            session.commit()
            logger.info(f"Successfully resolved {resolved_count}/{len(etf_mf_holdings)} ETF/MF holdings")
        
        # STEP 2: Fetch sector info for parent holdings
        info_fetched_count = 0
        holdings_needing_info = [h for h in all_holdings if not h.info_fetched]
        
        if holdings_needing_info:
            logger.info(f"Fetching sector info for {len(holdings_needing_info)} parent holdings...")
            
            for holding in holdings_needing_info:
                if fetch_stock_info_for_holding(holding):
                    info_fetched_count += 1
            
            session.commit()
            logger.info(f"✓ Fetched and SAVED info for {info_fetched_count}/{len(holdings_needing_info)} parent holdings")
        
        # STEP 3: Fetch sector info for UNDERLYING holdings
        underlying_enriched_count = 0
        etf_mf_with_underlying = [h for h in all_holdings 
                                  if h.asset_type in ['etf', 'mutual_fund'] and h.underlying_holdings_list]
        
        if etf_mf_with_underlying:
            logger.info(f"Fetching sector info for underlying holdings in {len(etf_mf_with_underlying)} ETFs/MFs...")
            
            for holding in etf_mf_with_underlying:
                enriched = fetch_sector_info_for_underlying_holdings(holding)
                underlying_enriched_count += enriched
            
            session.commit()
            logger.info(f"✓ Enriched and SAVED {underlying_enriched_count} total underlying holdings")
        
        logger.info(f"Snapshot {snapshot_id} complete: {resolved_count} ETF/MF resolved, " +
                   f"{info_fetched_count} parent info fetched, {underlying_enriched_count} underlying enriched")
    
    return resolved_count


def resolve_all_unresolved_holdings() -> int:
    """Resolve ALL unresolved ETF/MF holdings across all snapshots"""
    from app.database import db_session
    from app.models import Holding
    
    logger.info("Starting global holdings resolution")
    
    with db_session() as session:
        unresolved_etf_mf = session.query(Holding).filter(
            Holding.asset_type.in_(['etf', 'mutual_fund']),
            Holding.underlying_parsed == False
        ).all()
        
        holdings_needing_info = session.query(Holding).filter(
            Holding.info_fetched == False
        ).all()
        
        logger.info(f"Found {len(unresolved_etf_mf)} unresolved ETF/MF holdings")
        logger.info(f"Found {len(holdings_needing_info)} holdings needing sector/geography info")
        
        if not unresolved_etf_mf and not holdings_needing_info:
            logger.info("Nothing to resolve")
            return 0
        
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