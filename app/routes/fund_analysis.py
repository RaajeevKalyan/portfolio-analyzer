"""
Fund Analysis Routes - Expense Ratio and Peer Comparison

API endpoints:
- GET /api/fund-analysis/expenses - Get expense analysis for all funds
- GET /api/fund-analysis/peers/<category_id> - Get peer recommendations for a category
- GET /api/fund-analysis/compare/<symbol> - Compare fund with peers
- GET /api/fund-analysis/nav/<security_id> - Get NAV history for charting
"""
from flask import Blueprint, jsonify, request
import logging
from app.services.fund_analysis_service import FundAnalysisService
from app.services.holdings_aggregator import HoldingsAggregator

logger = logging.getLogger(__name__)

fund_analysis_bp = Blueprint('fund_analysis', __name__)


@fund_analysis_bp.route('/api/fund-analysis/expenses', methods=['GET'])
def get_expense_analysis():
    """
    Get expense ratio analysis for all ETF/Mutual Fund holdings
    
    Returns:
        JSON with top funds by expense ratio and annual costs
    """
    try:
        # Get current holdings
        aggregator = HoldingsAggregator()
        holdings_data = aggregator.get_aggregated_holdings()
        holdings = holdings_data.get('holdings', [])
        
        if not holdings:
            return jsonify({
                'success': True,
                'data': {
                    'top_funds': [],
                    'total_annual_expenses': 0,
                    'total_fund_value': 0,
                    'weighted_expense_ratio': 0,
                    'peer_recommendations': {},
                    'categories_analyzed': []
                },
                'message': 'No holdings found'
            })
        
        # Analyze fund expenses
        analyzer = FundAnalysisService()
        analysis = analyzer.get_expense_analysis_summary(holdings)
        
        return jsonify({
            'success': True,
            'data': analysis
        })
        
    except Exception as e:
        logger.error(f"Error in expense analysis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@fund_analysis_bp.route('/api/fund-analysis/peers/<category_id>', methods=['GET'])
def get_category_peers(category_id):
    """
    Get peer fund recommendations for a category
    
    Args:
        category_id: Morningstar category ID
        
    Query params:
        min_rating: Minimum medalist rating (Gold, Silver, Bronze)
        exclude: Comma-separated symbols to exclude
        
    Returns:
        JSON with peer fund recommendations
    """
    try:
        min_rating = request.args.get('min_rating', 'Silver')
        exclude = request.args.get('exclude', '').split(',')
        exclude = [s.strip() for s in exclude if s.strip()]
        
        analyzer = FundAnalysisService()
        peers = analyzer.find_category_peers(
            category_id=category_id,
            category_name="",  # Will be looked up
            exclude_symbols=exclude,
            min_rating=min_rating
        )
        
        return jsonify({
            'success': True,
            'data': {
                'peers': [
                    {
                        'symbol': p.ticker,
                        'name': p.name,
                        'expense_ratio': p.expense_ratio,
                        'expense_ratio_pct': p.expense_ratio * 100,
                        'medalist_rating': p.medalist_rating,
                        'star_rating': p.star_rating,
                        'return_m12': p.return_m12,
                        'return_m36': p.return_m36,
                        'return_m60': p.return_m60,
                        'fund_size': p.fund_size,
                        'security_id': p.security_id
                    }
                    for p in peers
                ],
                'category_id': category_id,
                'min_rating': min_rating
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting peers: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@fund_analysis_bp.route('/api/fund-analysis/nav/<security_id>', methods=['GET'])
def get_nav_history(security_id):
    """
    Get NAV history for a fund (for charting)
    
    Args:
        security_id: Morningstar security ID
        
    Query params:
        days: Number of days of history (default 365)
        
    Returns:
        JSON with NAV history data
    """
    try:
        days = int(request.args.get('days', 365))
        
        analyzer = FundAnalysisService()
        nav_df = analyzer.get_fund_nav_history(security_id, days)
        
        if nav_df is None or nav_df.empty:
            return jsonify({
                'success': True,
                'data': {
                    'nav_history': [],
                    'security_id': security_id
                }
            })
        
        # Convert to list of dicts for JSON
        history = []
        for _, row in nav_df.iterrows():
            history.append({
                'date': str(row.get('date', '')),
                'nav': float(row.get('nav', 0)),
                'total_return': float(row.get('totalReturn', 0))
            })
        
        return jsonify({
            'success': True,
            'data': {
                'nav_history': history,
                'security_id': security_id
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting NAV history: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@fund_analysis_bp.route('/api/fund-analysis/compare/<symbol>', methods=['GET'])
def compare_fund_with_peers(symbol):
    """
    Compare a fund's performance with its category peers
    
    Args:
        symbol: Fund ticker symbol
        
    Query params:
        days: Number of days of history (default 365)
        
    Returns:
        JSON with fund and peer performance data
    """
    import time
    request_start = time.time()
    
    try:
        days = int(request.args.get('days', 365))
        
        logger.info(f"[COMPARE] Starting comparison for {symbol}, days={days}")
        
        analyzer = FundAnalysisService()
        
        # Get fund info
        logger.info(f"[COMPARE] Searching for fund {symbol}...")
        fund_search_start = time.time()
        fund_data = analyzer._search_fund(symbol.upper())
        logger.info(f"[COMPARE] Fund search took {time.time() - fund_search_start:.1f}s")
        
        if not fund_data:
            return jsonify({
                'success': False,
                'error': f'Fund not found: {symbol}'
            }), 404
        
        logger.info(f"[COMPARE] Fund {symbol}: category='{fund_data.get('category')}', security_id={fund_data.get('security_id')}")
        
        # Get peers in same category
        peers = []
        category_name = fund_data.get('category', '')
        if category_name and category_name != 'Unknown':
            peer_search_start = time.time()
            peers = analyzer.find_category_peers(
                category_id=fund_data.get('category_id', ''),
                category_name=category_name,
                exclude_symbols=[symbol.upper()],
                min_rating='Silver'
            )
            logger.info(f"[COMPARE] Found {len(peers)} peers in {time.time() - peer_search_start:.1f}s")
        else:
            logger.warning(f"[COMPARE] No category for {symbol}, skipping peer search")
        
        # Get NAV history for fund
        logger.info(f"[COMPARE] Fetching NAV history for {symbol}...")
        nav_start = time.time()
        fund_nav = []
        if fund_data.get('security_id') or symbol:
            nav_df = analyzer.get_fund_nav_history(
                fund_data.get('security_id', ''), 
                days, 
                symbol=symbol.upper()
            )
            if nav_df is not None:
                for _, row in nav_df.iterrows():
                    fund_nav.append({
                        'date': str(row.get('date', '')),
                        'nav': float(row.get('nav', 0)),
                        'total_return': float(row.get('totalReturn', 0))
                    })
        logger.info(f"[COMPARE] Fund NAV: {len(fund_nav)} records in {time.time() - nav_start:.1f}s")
        
        # Get NAV history for top 3 peers
        peer_navs = {}
        for i, peer in enumerate(peers[:3]):
            logger.info(f"[COMPARE] Fetching NAV for peer {i+1}/3: {peer.ticker}...")
            peer_nav_start = time.time()
            nav_df = analyzer.get_fund_nav_history(
                peer.security_id if peer.security_id else '', 
                days,
                symbol=peer.ticker
            )
            if nav_df is not None and len(nav_df) > 0:
                peer_navs[peer.ticker] = [
                    {
                        'date': str(row.get('date', '')),
                        'nav': float(row.get('nav', 0)),
                        'total_return': float(row.get('totalReturn', 0))
                    }
                    for _, row in nav_df.iterrows()
                ]
                logger.info(f"[COMPARE] Peer {peer.ticker}: {len(peer_navs[peer.ticker])} records in {time.time() - peer_nav_start:.1f}s")
            else:
                logger.warning(f"[COMPARE] Peer {peer.ticker}: NO NAV data in {time.time() - peer_nav_start:.1f}s")
        
        total_time = time.time() - request_start
        logger.info(f"[COMPARE] COMPLETE for {symbol}: fund_nav={len(fund_nav)}, peers_with_nav={len(peer_navs)}, total_time={total_time:.1f}s")
        
        return jsonify({
            'success': True,
            'data': {
                'fund': {
                    'symbol': symbol.upper(),
                    'name': fund_data.get('name', ''),
                    'category': fund_data.get('category', ''),
                    'expense_ratio': fund_data.get('expense_ratio', 0),
                    'expense_ratio_pct': fund_data.get('expense_ratio', 0) * 100,
                    'medalist_rating': fund_data.get('medalist_rating', ''),
                    'star_rating': fund_data.get('star_rating', 0),
                    'return_m12': fund_data.get('return_m12', 0),
                    'return_m36': fund_data.get('return_m36', 0),
                    'return_m60': fund_data.get('return_m60', 0),
                    'nav_history': fund_nav
                },
                'peers': [
                    {
                        'symbol': p.ticker,
                        'name': p.name,
                        'expense_ratio': p.expense_ratio,
                        'expense_ratio_pct': p.expense_ratio * 100,
                        'medalist_rating': p.medalist_rating,
                        'star_rating': p.star_rating,
                        'return_m12': p.return_m12,
                        'nav_history': peer_navs.get(p.ticker, [])
                    }
                    for p in peers[:5]
                ],
                'category': fund_data.get('category', ''),
                'category_id': fund_data.get('category_id', '')
            }
        })
        
    except Exception as e:
        logger.error(f"Error comparing fund: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500