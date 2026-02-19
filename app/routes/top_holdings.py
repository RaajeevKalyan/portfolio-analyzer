"""
Top Holdings Routes - Aggregated stock holdings across all portfolios

Shows top 10 stocks by total value, combining:
1. Direct holdings (stocks you own directly)
2. Indirect holdings (stocks held through ETFs/MFs, weighted by fund value and stock weight)
"""
from flask import Blueprint, jsonify
import logging
from collections import defaultdict
from app.services.holdings_aggregator import HoldingsAggregator
from app.database import db_session
from app.models import Holding, UnderlyingHolding

logger = logging.getLogger(__name__)

top_holdings_bp = Blueprint('top_holdings', __name__)


@top_holdings_bp.route('/api/top-holdings', methods=['GET'])
def get_top_holdings():
    """
    Get top 10 stocks by total value across all portfolios
    
    Combines:
    - Direct stock holdings
    - Indirect holdings through ETFs/MFs (weighted by fund value × stock weight)
    
    Returns:
        JSON with top holdings and breakdown
    """
    try:
        # Get aggregated holdings
        aggregator = HoldingsAggregator()
        holdings_data = aggregator.get_aggregated_holdings()
        holdings = holdings_data.get('holdings', [])
        
        if not holdings:
            return jsonify({
                'success': True,
                'data': {
                    'top_holdings': [],
                    'total_stock_value': 0,
                    'message': 'No holdings found'
                }
            })
        
        # Aggregate stock values
        # Key: symbol, Value: {name, direct_value, indirect_value, indirect_sources: [{fund, value}]}
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
        
        # Process each holding
        for holding in holdings:
            symbol = holding.get('symbol', '')
            asset_type = holding.get('asset_type', '')
            value = float(holding.get('total_value', 0))
            
            if asset_type == 'stock':
                # Direct stock holding
                stock_totals[symbol]['symbol'] = symbol
                stock_totals[symbol]['name'] = holding.get('name', symbol)
                stock_totals[symbol]['direct_value'] += value
                stock_totals[symbol]['direct_shares'] += float(holding.get('quantity', 0))
                stock_totals[symbol]['sector'] = holding.get('sector', '')
                stock_totals[symbol]['country'] = holding.get('country', '')
                
            elif asset_type in ['etf', 'mutual_fund']:
                # Get underlying holdings for this fund
                underlying = holding.get('underlying_holdings', [])
                
                for uh in underlying:
                    uh_symbol = uh.get('symbol', '')
                    uh_weight = float(uh.get('weight', 0))  # Already decimal (0.07 = 7%)
                    uh_value = float(uh.get('value', 0))  # Pre-calculated value
                    
                    if not uh_symbol or uh_value <= 0:
                        continue
                    
                    # Add to stock totals
                    if not stock_totals[uh_symbol]['symbol']:
                        stock_totals[uh_symbol]['symbol'] = uh_symbol
                        stock_totals[uh_symbol]['name'] = uh.get('name', uh_symbol)
                        stock_totals[uh_symbol]['sector'] = uh.get('sector', '')
                        stock_totals[uh_symbol]['country'] = uh.get('country', '')
                    
                    stock_totals[uh_symbol]['indirect_value'] += uh_value
                    stock_totals[uh_symbol]['indirect_sources'].append({
                        'fund': symbol,
                        'fund_name': holding.get('name', symbol),
                        'weight': uh_weight,
                        'value': uh_value
                    })
        
        # Convert to list and calculate totals
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
                    'indirect_sources': data['indirect_sources'][:5],  # Limit to top 5 sources
                    'num_funds': len(data['indirect_sources']),
                    'sector': data['sector'],
                    'country': data['country'],
                    'is_also_held': data['direct_value'] > 0 and data['indirect_value'] > 0
                })
        
        # Sort by total value and get top 10
        all_stocks.sort(key=lambda x: x['total_value'], reverse=True)
        top_10 = all_stocks[:10]
        
        # Calculate total stock exposure
        total_stock_value = sum(s['total_value'] for s in all_stocks)
        total_direct = sum(s['direct_value'] for s in all_stocks)
        total_indirect = sum(s['indirect_value'] for s in all_stocks)
        
        return jsonify({
            'success': True,
            'data': {
                'top_holdings': top_10,
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