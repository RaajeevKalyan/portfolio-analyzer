"""
Holdings Resolver - FIXED for mstarpy 8.0.3

Uses screener_universe() to search for US funds specifically.

CHANGELOG:
- Added: Asset type verification after mstarpy lookup (Issue #2)
- Fixed: Removed international ticker warning, now handles them properly (Issue #3)
- Added: Resolution tracking integration for UI progress display (Issue #4)
- Added: Better logging for sector/country data confirmation
- Fixed: Update asset_type in database if mstarpy returns different type
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
import mstarpy as ms
import pandas as pd
import json

logger = logging.getLogger(__name__)


class HoldingsResolver:
    """Resolve ETF/Mutual Fund underlying holdings"""
    
    def __init__(self):
        pass
    
    def _search_us_fund(self, symbol: str) -> Optional[Dict]:
        """
        Search for US-domiciled fund using screener_universe
        STRICT: Only returns funds on US exchanges
        
        Also returns the correct asset_type based on mstarpy data.
        """
        symbol = symbol.upper().strip()
        us_exchanges = ["ARCX", "XNAS", "XNYS", "BATS", "NYSE", "NASDAQ"]
        
        for inv_type, type_name, db_type in [("FE", "ETF", "etf"), ("FO", "Mutual Fund", "mutual_fund")]:
            try:
                results = ms.screener_universe(
                    symbol,
                    language="en-gb",
                    field=["name", "ticker", "exchange", "isin", "investmentType"],
                    filters={"investmentType": inv_type},
                    pageSize=100
                )
                
                if results:
                    # Collect ALL ticker matches
                    matches = []
                    for result in results:
                        meta = result.get("meta", {})
                        fields = result.get("fields", {})
                        
                        ticker = meta.get("ticker", "") or ""
                        exchange = meta.get("exchange", "") or ""
                        
                        if ticker.upper() == symbol:
                            matches.append({
                                "securityID": meta.get("securityID"),
                                "ticker": ticker,
                                "name": fields.get("name", {}).get("value", "Unknown"),
                                "exchange": exchange,
                                "type": type_name,
                                "db_asset_type": db_type  # The type to store in database
                            })
                    
                    if matches:
                        logger.info(f"  Found {len(matches)} matches for {symbol} as {type_name}")
                        for match in matches:
                            logger.info(f"    - {match['name']} ({match['exchange']})")
                        
                        # CRITICAL: Pick FIRST US exchange match ONLY
                        for match in matches:
                            if match['exchange'] in us_exchanges:
                                logger.info(f"  ✓ Selected US exchange: {match['exchange']}")
                                return match
                        
                        logger.info(f"  No US exchange found for {symbol}, trying first available")
                        # If no US exchange, return first match anyway (for international ETFs listed elsewhere)
                        return matches[0]
            
            except Exception as e:
                logger.warning(f"Error searching {type_name} for {symbol}: {e}")
                continue
        
        return None
    
    def resolve_holding(self, symbol: str, asset_type: str, total_value: Decimal) -> Optional[Dict]:
        """
        Resolve underlying holdings for an ETF or Mutual Fund
        
        Args:
            symbol: Ticker symbol (e.g., 'VTI', 'POGAX')
            asset_type: Type of asset ('etf' or 'mutual_fund')
            total_value: Total value of the holding
            
        Returns:
            Dict with:
            - 'holdings': List of underlying holdings
            - 'verified_asset_type': The asset type confirmed by mstarpy (may differ from input)
        """
        if asset_type not in ['etf', 'mutual_fund']:
            logger.debug(f"Skipping {symbol} - not an ETF or mutual fund")
            return None
        
        logger.info(f"Resolving underlying holdings for {symbol} ({asset_type})...")
        
        try:
            # STEP 1: Search for the fund to get security ID
            logger.info(f"  Searching for US fund: {symbol}")
            fund_info = self._search_us_fund(symbol)
            
            if not fund_info:
                logger.warning(f"No fund found for {symbol}")
                return None
            
            sec_id = fund_info["securityID"]
            fund_name = fund_info["name"]
            exchange = fund_info["exchange"]
            verified_asset_type = fund_info.get("db_asset_type", asset_type)
            
            # Check if mstarpy returned a different asset type
            if verified_asset_type != asset_type:
                logger.info(f"  Asset type update: {symbol} was {asset_type}, mstarpy says {verified_asset_type}")
            
            logger.info(f"  Found: {fund_name} ({exchange}) - SecID: {sec_id}")
            
            # STEP 2: Get holdings using security ID
            fund = ms.Funds(sec_id)
            holdings_df = fund.holdings(holdingType="equity")
            
            if holdings_df is None or holdings_df.empty:
                # Try all holdings if equity is empty
                holdings_df = fund.holdings()
            
            if holdings_df is None or holdings_df.empty:
                logger.warning(f"No holdings data found for {symbol}")
                return {
                    'holdings': None,
                    'verified_asset_type': verified_asset_type
                }
            
            logger.info(f"Found {len(holdings_df)} holdings for {symbol}")
            
            # STEP 3: Log sample tickers for debugging (no warning, just info)
            sample_tickers = []
            for idx, row in holdings_df.head(10).iterrows():
                if 'ticker' in row and pd.notna(row['ticker']):
                    ticker = str(row['ticker']).strip().upper()
                    sample_tickers.append(ticker)
            
            if sample_tickers:
                logger.info(f"  Sample holdings: {sample_tickers[:5]}")
                # Note: International tickers are fine, we handle them in stock_info_service
            
            # STEP 4: Process holdings DataFrame
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
                return {
                    'holdings': None,
                    'verified_asset_type': verified_asset_type
                }
            
            underlying.sort(key=lambda x: x['weight'], reverse=True)
            logger.info(f"Successfully resolved {len(underlying)} holdings for {symbol}")
            
            return {
                'holdings': underlying,
                'verified_asset_type': verified_asset_type
            }
                    
        except Exception as e:
            logger.error(f"Error resolving holdings for {symbol}: {e}")
            logger.exception(e)
            return None
    
    def resolve_multiple_holdings(self, holdings: List[Dict]) -> Dict[int, Dict]:
        """
        Resolve multiple holdings in batch
        
        Returns:
            Dict mapping holding_id to:
            - 'holdings': List of underlying holdings
            - 'verified_asset_type': Asset type confirmed by mstarpy
        """
        results = {}
        
        for holding in holdings:
            holding_id = holding['id']
            symbol = holding['symbol']
            asset_type = holding['asset_type']
            total_value = holding['total_value']
            
            logger.info(f"Processing holding {holding_id}: {symbol} ({asset_type})")
            
            result = self.resolve_holding(symbol, asset_type, total_value)
            
            if result:
                results[holding_id] = result
                if result.get('holdings'):
                    logger.info(f"Resolved {len(result['holdings'])} underlying holdings for {symbol}")
                else:
                    logger.warning(f"No underlying holdings found for {symbol}")
            else:
                logger.warning(f"Could not resolve holdings for {symbol}")
        
        return results


def fetch_stock_info_for_holding(holding) -> bool:
    """
    Fetch sector/geography information for a holding using yfinance
    
    Returns True if info was fetched successfully (or was already fetched)
    """
    from app.services.stock_info_service import get_stock_info
    from app.services.resolution_tracker import update_progress, log_error
    
    if holding.info_fetched:
        logger.debug(f"Info already fetched for {holding.symbol}, skipping")
        return True
    
    try:
        logger.info(f"Fetching sector/geography info for {holding.symbol}")
        update_progress('parent_info', symbol=holding.symbol)
        
        stock_info = get_stock_info(holding.symbol)
        
        if stock_info:
            holding.sector = stock_info.get('sector', 'Unknown')
            holding.industry = stock_info.get('industry', 'Unknown')
            holding.country = stock_info.get('country', 'Unknown')
            holding.info_fetched = True
            
            # Log confirmation that data was saved
            logger.info(f"✓ SAVED info for {holding.symbol}: sector={holding.sector}, industry={holding.industry}, country={holding.country}")
            return True
        else:
            logger.warning(f"No info returned for {holding.symbol}")
            holding.sector = 'Unknown'
            holding.industry = 'Unknown'
            holding.country = 'Unknown'
            holding.info_fetched = True
            log_error(holding.symbol, "No info returned from yfinance")
            return False
            
    except Exception as e:
        logger.error(f"Error fetching info for {holding.symbol}: {e}")
        logger.exception(e)
        holding.sector = 'Unknown'
        holding.industry = 'Unknown'
        holding.country = 'Unknown'
        holding.info_fetched = True
        log_error(holding.symbol, str(e))
        return False


def fetch_sector_info_for_underlying_holdings(holding) -> int:
    """
    Fetch sector/geography info for all underlying holdings
    
    Returns count of successfully enriched holdings
    """
    from app.services.stock_info_service import get_stock_info
    from app.services.resolution_tracker import update_progress, log_error
    
    if not holding.underlying_holdings_list:
        logger.debug(f"No underlying holdings for {holding.symbol}")
        return 0
    
    try:
        underlying_list = holding.underlying_holdings_list
        total_underlying = len(underlying_list)
        
        logger.info(f"=" * 80)
        logger.info(f"STARTING: Fetching sector info for {total_underlying} underlying holdings in {holding.symbol}")
        logger.info(f"=" * 80)
        
        enriched_count = 0
        skipped_count = 0
        
        for idx, underlying in enumerate(underlying_list, 1):
            # Check if already has sector data
            existing_sector = underlying.get('sector')
            if existing_sector and existing_sector not in [None, 'Unknown', '', 'NOT SET']:
                logger.debug(f"  [{idx}/{total_underlying}] {underlying['symbol']} - already has sector: {existing_sector}")
                enriched_count += 1
                skipped_count += 1
                continue
            
            symbol = underlying['symbol']
            update_progress('underlying_info', symbol=f"{holding.symbol} → {symbol}", processed=idx, total=total_underlying)
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
                log_error(symbol, f"No info returned (underlying of {holding.symbol})")
        
        # CRITICAL: Write directly to TEXT column
        holding.underlying_holdings = json.dumps(underlying_list)
        
        logger.info(f"=" * 80)
        logger.info(f"COMPLETED: {holding.symbol} - Enriched {enriched_count}/{total_underlying} underlying holdings ({skipped_count} already had data)")
        logger.info(f"✓ SAVED underlying holdings JSON for {holding.symbol}")
        logger.info(f"=" * 80)
        return enriched_count
        
    except Exception as e:
        logger.error(f"Error enriching underlying holdings for {holding.symbol}: {e}")
        logger.exception(e)
        log_error(holding.symbol, f"Error enriching underlying: {str(e)}")
        return 0


def resolve_snapshot_holdings(snapshot_id: int) -> int:
    """
    Resolve all ETF/MF holdings for a given snapshot
    
    This is the main entry point called by the background task.
    Includes resolution tracking for UI updates.
    """
    from app.database import db_session
    from app.models import Holding
    from app.services.resolution_tracker import start_resolution, update_progress, complete_resolution, log_error
    
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
        
        # Estimate total underlying symbols (rough estimate: ~100 per ETF/MF)
        estimated_underlying = len(etf_mf_holdings) * 100
        
        logger.info(f"Found {len(all_holdings)} total holdings ({len(etf_mf_holdings)} ETF/MF to resolve)")
        
        # Start resolution tracking with detailed counts
        start_resolution(
            snapshot_id, 
            total_symbols=len(all_holdings) + estimated_underlying,
            parent_total=len(all_holdings),
            underlying_total=estimated_underlying
        )
        
        # STEP 1: Resolve ETF/MF underlying holdings
        resolved_count = 0
        actual_underlying_count = 0
        
        if etf_mf_holdings:
            update_progress('etf_resolution', message=f"Resolving {len(etf_mf_holdings)} ETF/MF holdings")
            
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
                    result = results[holding.id]
                    
                    # Update underlying holdings
                    if result.get('holdings'):
                        holding.underlying_holdings_list = result['holdings']
                        actual_underlying_count += len(result['holdings'])
                        resolved_count += 1
                        logger.info(f"Stored {len(result['holdings'])} underlying holdings for {holding.symbol}")
                    
                    # Update asset_type if mstarpy returned a different type (Issue #2)
                    verified_type = result.get('verified_asset_type')
                    if verified_type and verified_type != holding.asset_type:
                        logger.info(f"Updating asset_type for {holding.symbol}: {holding.asset_type} → {verified_type}")
                        holding.asset_type = verified_type
                    
                    holding.underlying_parsed = True
                else:
                    holding.underlying_parsed = True
                    logger.warning(f"Failed to resolve {holding.symbol}, marking as parsed")
                    log_error(holding.symbol, "Failed to resolve underlying holdings")
            
            session.commit()
            
            # Update tracker with actual underlying count now that we know it
            update_progress('etf_resolution', underlying_total=actual_underlying_count)
            logger.info(f"Successfully resolved {resolved_count}/{len(etf_mf_holdings)} ETF/MF holdings")
            logger.info(f"Total underlying symbols to process: {actual_underlying_count}")
        
        # STEP 2: Fetch sector info for parent holdings
        info_fetched_count = 0
        holdings_needing_info = [h for h in all_holdings if not h.info_fetched]
        
        if holdings_needing_info:
            update_progress('parent_info', message=f"Fetching info for {len(holdings_needing_info)} holdings",
                          parent_processed=0)
            logger.info(f"Fetching sector info for {len(holdings_needing_info)} parent holdings...")
            
            for idx, holding in enumerate(holdings_needing_info, 1):
                update_progress('parent_info', symbol=holding.symbol, parent_processed=idx)
                if fetch_stock_info_for_holding(holding):
                    info_fetched_count += 1
                
                # Commit periodically to save progress
                if idx % 10 == 0:
                    session.commit()
            
            session.commit()
            logger.info(f"✓ Fetched and SAVED info for {info_fetched_count}/{len(holdings_needing_info)} parent holdings")
        
        # STEP 3: Fetch sector info for UNDERLYING holdings
        underlying_enriched_count = 0
        etf_mf_with_underlying = [h for h in all_holdings 
                                  if h.asset_type in ['etf', 'mutual_fund'] and h.underlying_holdings_list]
        
        if etf_mf_with_underlying:
            # Calculate actual total underlying
            total_underlying = sum(len(h.underlying_holdings_list) for h in etf_mf_with_underlying)
            update_progress('underlying_info', 
                          message=f"Enriching {total_underlying} underlying holdings",
                          underlying_total=total_underlying,
                          underlying_processed=0)
            logger.info(f"Fetching sector info for {total_underlying} underlying holdings...")
            
            processed_underlying = 0
            for holding in etf_mf_with_underlying:
                enriched = fetch_sector_info_for_underlying_holdings_with_tracking(
                    holding, 
                    processed_underlying,
                    total_underlying
                )
                underlying_enriched_count += enriched
                processed_underlying += len(holding.underlying_holdings_list or [])
                
                # Commit after each holding's underlying is processed
                session.commit()
            
            logger.info(f"✓ Enriched and SAVED {underlying_enriched_count} total underlying holdings")
        
        # Complete resolution tracking
        complete_resolution(
            success=True,
            message=f"Resolved {resolved_count} ETF/MF, {info_fetched_count} parent info, {underlying_enriched_count} underlying"
        )
        
        logger.info(f"Snapshot {snapshot_id} complete: {resolved_count} ETF/MF resolved, " +
                   f"{info_fetched_count} parent info fetched, {underlying_enriched_count} underlying enriched")
    
    return resolved_count


def fetch_sector_info_for_underlying_holdings_with_tracking(holding, processed_so_far: int, total_underlying: int) -> int:
    """
    Fetch sector/geography info for all underlying holdings with progress tracking
    
    Returns count of successfully enriched holdings
    """
    from app.services.stock_info_service import get_stock_info, StockInfoService
    from app.services.resolution_tracker import update_progress, log_error
    
    if not holding.underlying_holdings_list:
        logger.debug(f"No underlying holdings for {holding.symbol}")
        return 0
    
    # Get the service to check cache
    service = StockInfoService()
    
    try:
        underlying_list = holding.underlying_holdings_list
        total_in_holding = len(underlying_list)
        
        logger.info(f"Processing {total_in_holding} underlying holdings in {holding.symbol}")
        
        enriched_count = 0
        
        for idx, underlying in enumerate(underlying_list, 1):
            symbol = underlying['symbol']
            global_idx = processed_so_far + idx
            
            # Check if already has sector data
            existing_sector = underlying.get('sector')
            if existing_sector and existing_sector not in [None, 'Unknown', '', 'NOT SET']:
                enriched_count += 1
                update_progress('underlying_info', 
                              symbol=f"{holding.symbol} → {symbol} (cached)",
                              underlying_processed=global_idx,
                              cached=True)
                continue
            
            # Check if in cache (no API call needed)
            is_cached = symbol in service.cache
            
            update_progress('underlying_info', 
                          symbol=f"{holding.symbol} → {symbol}",
                          underlying_processed=global_idx,
                          cached=is_cached)
            
            stock_info = get_stock_info(symbol)
            
            if stock_info:
                underlying['sector'] = stock_info.get('sector', 'Unknown')
                underlying['industry'] = stock_info.get('industry', 'Unknown')
                underlying['country'] = stock_info.get('country', 'Unknown')
                underlying['geography'] = stock_info.get('geography', 'Unknown')
                enriched_count += 1
            else:
                underlying['sector'] = 'Unknown'
                underlying['industry'] = 'Unknown'
                underlying['country'] = 'Unknown'
                underlying['geography'] = 'Unknown'
                log_error(symbol, f"No info returned (underlying of {holding.symbol})")
        
        # Save updated underlying holdings
        holding.underlying_holdings = json.dumps(underlying_list)
        
        logger.info(f"Completed {holding.symbol}: enriched {enriched_count}/{total_in_holding}")
        return enriched_count
        
    except Exception as e:
        logger.error(f"Error enriching underlying holdings for {holding.symbol}: {e}")
        logger.exception(e)
        log_error(holding.symbol, f"Error enriching underlying: {str(e)}")
        return 0


def resolve_all_unresolved_holdings() -> int:
    """Resolve ALL unresolved ETF/MF holdings across all snapshots"""
    from app.database import db_session
    from app.models import Holding
    from app.services.resolution_tracker import start_resolution, complete_resolution
    
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
