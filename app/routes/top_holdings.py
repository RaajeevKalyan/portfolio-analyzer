"""
Top Holdings Routes - Optimized with SQL Queries

Shows top stocks by total value, combining:
1. Direct holdings (stocks you own directly)
2. Indirect holdings (stocks held through ETFs/MFs)

OPTIMIZATION:
- Uses direct SQL queries instead of loading all holdings into Python
- Batch fetches prices via yf.Tickers() for top 50 stocks only
- Minimizes API calls and memory usage
"""
from flask import Blueprint, jsonify
import logging
from collections import defaultdict
from sqlalchemy import func, desc
from app.database import db_session
from app.models import Holding, PortfolioSnapshot, BrokerAccount
from app.services.db_utils import get_latest_snapshot_ids

logger = logging.getLogger(__name__)

top_holdings_bp = Blueprint('top_holdings', __name__)


def get_top_direct_stocks(session, snapshot_ids, limit=100):
    """
    Get top direct stock holdings using SQL aggregation.
    
    Returns:
        List of dicts with symbol, name, total_value, total_quantity, sector, country
    """
    if not snapshot_ids:
        return []
    
    # SQL query to aggregate stocks by symbol across all snapshots
    results = session.query(
        Holding.symbol,
        Holding.name,
        func.sum(Holding.total_value).label('total_value'),
        func.sum(Holding.quantity).label('total_quantity'),
        Holding.sector,
        Holding.country
    ).filter(
        Holding.portfolio_snapshot_id.in_(snapshot_ids),
        Holding.asset_type == 'stock'
    ).group_by(
        Holding.symbol
    ).order_by(
        desc('total_value')
    ).limit(limit).all()
    
    return [{
        'symbol': r.symbol,
        'name': r.name,
        'total_value': float(r.total_value) if r.total_value else 0,
        'total_quantity': float(r.total_quantity) if r.total_quantity else 0,
        'sector': r.sector or '',
        'country': r.country or ''
    } for r in results]


def get_top_underlying_stocks(session, snapshot_ids, limit=100):
    """
    Get top stocks from underlying holdings of ETFs/MFs.
    
    The underlying_holdings_list property returns parsed JSON array of holdings.
    We need to extract and aggregate these.
    
    Returns:
        Dict of symbol -> {name, total_value, sources: [{fund, value, weight}]}
    """
    if not snapshot_ids:
        return {}
    
    # Get all ETF/MF holdings with their underlying data
    funds = session.query(Holding).filter(
        Holding.portfolio_snapshot_id.in_(snapshot_ids),
        Holding.asset_type.in_(['etf', 'mutual_fund'])
    ).all()
    
    # Aggregate underlying holdings in Python (JSON parsing via property)
    underlying_totals = defaultdict(lambda: {
        'symbol': '',
        'name': '',
        'total_value': 0,
        'sources': []
    })
    
    for fund in funds:
        fund_symbol = fund.symbol
        fund_value = float(fund.total_value) if fund.total_value else 0
        
        # Use the underlying_holdings_list property which handles JSON parsing
        underlying_list = fund.underlying_holdings_list or []
        
        for uh in underlying_list:
            symbol = uh.get('symbol', '')
            if not symbol:
                continue
            
            name = uh.get('name', symbol)
            value = float(uh.get('value', 0))
            weight = float(uh.get('weight', 0))
            
            if value <= 0:
                continue
            
            data = underlying_totals[symbol]
            if not data['symbol']:
                data['symbol'] = symbol
                data['name'] = name
            
            data['total_value'] += value
            data['sources'].append({
                'fund': fund_symbol,
                'value': value,
                'weight': weight
            })
    
    # Sort by total value and limit
    sorted_underlying = sorted(
        underlying_totals.items(),
        key=lambda x: x[1]['total_value'],
        reverse=True
    )[:limit]
    
    return dict(sorted_underlying)


def batch_fetch_prices(symbols):
    """
    Batch fetch current prices for multiple symbols using yf.Tickers.
    
    Args:
        symbols: List of stock symbols
        
    Returns:
        Dict of symbol -> price
    """
    if not symbols:
        return {}
    
    prices = {}
    
    try:
        import yfinance as yf
        
        # Filter to valid-looking symbols (avoid Morningstar IDs)
        valid_symbols = [s for s in symbols if s and len(s) <= 5 and s.isalpha()]
        
        if not valid_symbols:
            return {}
        
        # Batch fetch - single API call for all symbols
        tickers_str = " ".join(valid_symbols)
        logger.info(f"Batch fetching prices for {len(valid_symbols)} symbols")
        
        tickers = yf.Tickers(tickers_str)
        
        for symbol in valid_symbols:
            try:
                ticker = tickers.tickers.get(symbol)
                if ticker:
                    info = ticker.info
                    if info:
                        price = info.get('currentPrice') or info.get('previousClose') or info.get('regularMarketPrice')
                        if price and price > 0:
                            prices[symbol] = float(price)
            except Exception as e:
                logger.debug(f"Could not get price for {symbol}: {e}")
                continue
        
        logger.info(f"Got prices for {len(prices)} symbols")
        
    except Exception as e:
        logger.error(f"Batch price fetch error: {e}")
    
    return prices


@top_holdings_bp.route('/api/top-holdings', methods=['GET'])
def get_top_holdings():
    """
    Get top stocks by total value across all portfolios.
    
    Optimized flow:
    1. SQL query for top 100 direct stock holdings
    2. Extract top 100 underlying holdings from ETF/MF JSON
    3. Merge and aggregate by symbol
    4. Sort and take top 50
    5. Batch fetch prices for symbols needing quantity calculation
    """
    try:
        with db_session() as session:
            # Step 1: Get latest snapshot IDs
            snapshot_ids = get_latest_snapshot_ids(session)
            
            if not snapshot_ids:
                return jsonify({
                    'success': True,
                    'data': {
                        'top_holdings': [],
                        'total_stock_value': 0,
                        'total_direct_value': 0,
                        'total_indirect_value': 0,
                        'total_unique_stocks': 0,
                        'message': 'No holdings found'
                    }
                })
            
            logger.info(f"Processing {len(snapshot_ids)} snapshots")
            
            # Step 2: Get top direct stocks (SQL aggregation)
            direct_stocks = get_top_direct_stocks(session, snapshot_ids, limit=100)
            logger.info(f"Found {len(direct_stocks)} direct stock holdings")
            
            # Step 3: Get top underlying stocks
            underlying_stocks = get_top_underlying_stocks(session, snapshot_ids, limit=100)
            logger.info(f"Found {len(underlying_stocks)} underlying stock holdings")
        
        # Step 4: Merge direct and indirect holdings
        stock_totals = defaultdict(lambda: {
            'symbol': '',
            'name': '',
            'direct_value': 0,
            'direct_shares': 0,
            'indirect_value': 0,
            'indirect_sources': [],
            'sector': '',
            'country': ''
        })
        
        # Add direct holdings
        for ds in direct_stocks:
            symbol = ds['symbol']
            stock_totals[symbol]['symbol'] = symbol
            stock_totals[symbol]['name'] = ds['name']
            stock_totals[symbol]['direct_value'] = ds['total_value']
            stock_totals[symbol]['direct_shares'] = ds['total_quantity']
            stock_totals[symbol]['sector'] = ds['sector']
            stock_totals[symbol]['country'] = ds['country']
        
        # Add indirect holdings
        for symbol, us_data in underlying_stocks.items():
            if not stock_totals[symbol]['symbol']:
                stock_totals[symbol]['symbol'] = symbol
                stock_totals[symbol]['name'] = us_data['name']
            
            stock_totals[symbol]['indirect_value'] = us_data['total_value']
            stock_totals[symbol]['indirect_sources'] = us_data['sources'][:5]  # Top 5 sources
        
        # Step 5: Build result list and sort
        all_stocks = []
        for symbol, data in stock_totals.items():
            total_value = data['direct_value'] + data['indirect_value']
            if total_value > 0:
                all_stocks.append({
                    'symbol': symbol,
                    'name': data['name'],
                    'total_value': round(total_value, 2),
                    'direct_value': round(data['direct_value'], 2),
                    'direct_shares': round(data['direct_shares'], 4),
                    'indirect_value': round(data['indirect_value'], 2),
                    'indirect_sources': data['indirect_sources'],
                    'num_funds': len(data['indirect_sources']),
                    'sector': data['sector'],
                    'country': data['country'],
                    'is_also_held': data['direct_value'] > 0 and data['indirect_value'] > 0
                })
        
        all_stocks.sort(key=lambda x: x['total_value'], reverse=True)
        top_50 = all_stocks[:50]
        
        # Step 6: Batch fetch prices for stocks needing quantity calculation
        # These are stocks with indirect_value but no direct_shares (can't calculate price)
        symbols_needing_price = [
            s['symbol'] for s in top_50 
            if s['indirect_value'] > 0 and s['direct_shares'] == 0
        ]
        
        prices = {}
        if symbols_needing_price:
            prices = batch_fetch_prices(symbols_needing_price)
        
        # Step 7: Calculate total shares for each stock
        for stock in top_50:
            direct_shares = stock['direct_shares']
            indirect_shares = 0
            
            if stock['indirect_value'] > 0:
                # Get price from direct holdings or batch fetch
                if direct_shares > 0 and stock['direct_value'] > 0:
                    price = stock['direct_value'] / direct_shares
                else:
                    price = prices.get(stock['symbol'], 0)
                
                if price > 0:
                    indirect_shares = stock['indirect_value'] / price
            
            total_shares = direct_shares + indirect_shares
            stock['total_shares'] = round(total_shares, 4) if total_shares > 0 else None
        
        # Step 8: Get sector/country from cache for indirect-only holdings
        try:
            from app.services.stock_info_service import StockInfoService
            stock_info_service = StockInfoService()
            
            for stock in top_50:
                if not stock['sector']:
                    cached = stock_info_service.cache.get(stock['symbol'], {})
                    if cached:
                        stock['sector'] = cached.get('sector', '') or ''
                        stock['country'] = cached.get('country', '') or ''
        except Exception as e:
            logger.debug(f"Could not load stock info cache: {e}")
        
        # Calculate totals
        total_stock_value = sum(s['total_value'] for s in all_stocks)
        total_direct = sum(s['direct_value'] for s in all_stocks)
        total_indirect = sum(s['indirect_value'] for s in all_stocks)
        
        logger.info(f"Top holdings: {len(all_stocks)} unique stocks, ${total_stock_value:.2f} total")
        
        return jsonify({
            'success': True,
            'data': {
                'top_holdings': top_50[:25],  # Return top 25 for display
                'total_stock_value': round(total_stock_value, 2),
                'total_direct_value': round(total_direct, 2),
                'total_indirect_value': round(total_indirect, 2),
                'total_unique_stocks': len(all_stocks)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting top holdings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500