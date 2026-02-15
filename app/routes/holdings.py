"""
Holdings Routes

Display aggregated portfolio holdings across all brokers.

CHANGELOG:
- Added: /api/holdings/cash-breakdown endpoint
- Added: /api/holdings/asset-breakdown endpoint
- Added: /api/holdings/underlying/<symbol> endpoint for modal
"""
from flask import Blueprint, render_template, jsonify
from app.services.holdings_aggregator import (
    get_current_holdings, 
    get_cash_breakdown, 
    get_asset_breakdown,
    HoldingsAggregator
)
from app.database import db_session
from app.models import Holding, PortfolioSnapshot, BrokerAccount
from sqlalchemy import desc
import logging

logger = logging.getLogger(__name__)

holdings_bp = Blueprint('holdings', __name__)


@holdings_bp.route('/holdings')
def holdings_page():
    """
    Display aggregated holdings table
    
    Shows:
    - All holdings grouped by symbol
    - Broker breakdown for each holding
    - ETF/MF expansion to show underlying holdings
    - Overlap warnings
    - Cash vs Investment breakdown
    """
    try:
        # Get aggregated holdings data
        data = get_current_holdings()
        
        logger.info(f"Displaying {len(data['holdings'])} aggregated holdings")
        logger.info(f"Total portfolio value: ${data['total_value']}")
        logger.info(f"Investments: ${data['total_investments']} ({data['investment_percentage']:.1f}%)")
        logger.info(f"Cash: ${data['total_cash']} ({data['cash_percentage']:.1f}%)")
        logger.info(f"Detected {len(data.get('overlaps', {}))} overlaps")
        
        return render_template(
            'holdings.html',
            holdings=data['holdings'],
            investment_holdings=data.get('investment_holdings', []),
            cash_holdings=data.get('cash_holdings', []),
            total_value=data['total_value'],
            total_investments=data.get('total_investments', data['total_value']),
            total_cash=data.get('total_cash', 0),
            cash_percentage=data.get('cash_percentage', 0),
            investment_percentage=data.get('investment_percentage', 100),
            overlaps=data.get('overlaps', {}),
            direct_holdings=data.get('direct_holdings', {}),
            underlying_holdings=data.get('underlying_holdings', {})
        )
        
    except Exception as e:
        logger.error(f"Error loading holdings page: {e}", exc_info=True)
        
        # Return empty page with error
        return render_template(
            'holdings.html',
            holdings=[],
            investment_holdings=[],
            cash_holdings=[],
            total_value=0,
            total_investments=0,
            total_cash=0,
            cash_percentage=0,
            investment_percentage=0,
            overlaps={},
            direct_holdings={},
            underlying_holdings={},
            error_message=str(e)
        )


@holdings_bp.route('/api/holdings/cash-breakdown')
def api_cash_breakdown():
    """
    API endpoint for cash vs investments breakdown
    
    Returns:
        JSON: {
            'total_value': float,
            'breakdown': [
                {'label': 'Investments', 'value': float, 'percentage': float, 'color': str},
                {'label': 'Cash', 'value': float, 'percentage': float, 'color': str}
            ]
        }
    """
    try:
        data = get_cash_breakdown()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting cash breakdown: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@holdings_bp.route('/api/holdings/asset-breakdown')
def api_asset_breakdown():
    """
    API endpoint for asset type breakdown (stocks, ETFs, MFs, cash)
    
    Returns:
        JSON: {
            'total_value': float,
            'breakdown': [
                {'type': str, 'label': str, 'value': float, 'count': int, 'percentage': float, 'color': str},
                ...
            ]
        }
    """
    try:
        data = get_asset_breakdown()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting asset breakdown: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@holdings_bp.route('/api/holdings/underlying/<symbol>')
def api_underlying_holdings(symbol: str):
    """
    API endpoint to get underlying holdings for an ETF/Mutual Fund
    
    Args:
        symbol: The ETF/MF symbol (e.g., 'VTI')
        
    Returns:
        JSON: {
            'symbol': str,
            'name': str,
            'total_value': float,
            'quantity': float,
            'price': float,
            'underlying_holdings': [
                {
                    'symbol': str,
                    'name': str,
                    'weight': float,
                    'value': float,
                    'sector': str,
                    'country': str
                },
                ...
            ],
            'direct_holdings': [str]  # List of symbols held directly (for overlap detection)
        }
    """
    try:
        symbol = symbol.upper().strip()
        logger.info(f"Fetching underlying holdings for {symbol}")
        
        with db_session() as session:
            # Get the latest holding for this symbol
            accounts = session.query(BrokerAccount).filter_by(is_active=True).all()
            
            holding_obj = None
            
            for account in accounts:
                snapshot = session.query(PortfolioSnapshot).filter_by(
                    broker_account_id=account.id
                ).order_by(desc(PortfolioSnapshot.snapshot_date)).first()
                
                if snapshot:
                    holding = session.query(Holding).filter_by(
                        portfolio_snapshot_id=snapshot.id,
                        symbol=symbol
                    ).first()
                    
                    if holding:
                        holding_obj = holding
                        break
            
            if not holding_obj:
                return jsonify({
                    'error': f'Holding not found: {symbol}'
                }), 404
            
            if holding_obj.asset_type not in ['etf', 'mutual_fund']:
                return jsonify({
                    'error': f'{symbol} is not an ETF or Mutual Fund'
                }), 400
            
            # Get underlying holdings
            underlying_list = holding_obj.underlying_holdings_list or []
            
            # Get list of directly held symbols (for overlap detection)
            direct_symbols = set()
            for account in accounts:
                snapshot = session.query(PortfolioSnapshot).filter_by(
                    broker_account_id=account.id
                ).order_by(desc(PortfolioSnapshot.snapshot_date)).first()
                
                if snapshot:
                    holdings = session.query(Holding).filter(
                        Holding.portfolio_snapshot_id == snapshot.id,
                        Holding.asset_type == 'stock'
                    ).all()
                    
                    for h in holdings:
                        direct_symbols.add(h.symbol)
            
            logger.info(f"Found {len(underlying_list)} underlying holdings for {symbol}")
            logger.info(f"Found {len(direct_symbols)} directly held stocks for overlap check")
            
            return jsonify({
                'symbol': holding_obj.symbol,
                'name': holding_obj.name,
                'total_value': float(holding_obj.total_value),
                'quantity': float(holding_obj.quantity),
                'price': float(holding_obj.price),
                'asset_type': holding_obj.asset_type,
                'underlying_holdings': underlying_list,
                'direct_holdings': list(direct_symbols)
            })
            
    except Exception as e:
        logger.error(f"Error getting underlying holdings for {symbol}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@holdings_bp.route('/api/holdings/summary')
def api_holdings_summary():
    """
    API endpoint for portfolio summary
    
    Returns:
        JSON: {
            'total_value': float,
            'total_investments': float,
            'total_cash': float,
            'cash_percentage': float,
            'investment_percentage': float,
            'holdings_count': int,
            'etf_count': int,
            'mf_count': int,
            'stock_count': int
        }
    """
    try:
        data = get_current_holdings()
        
        # Count by type
        etf_count = sum(1 for h in data['holdings'] if h['asset_type'] == 'etf')
        mf_count = sum(1 for h in data['holdings'] if h['asset_type'] == 'mutual_fund')
        stock_count = sum(1 for h in data['holdings'] if h['asset_type'] == 'stock')
        cash_count = sum(1 for h in data['holdings'] if h['asset_type'] == 'cash')
        
        return jsonify({
            'total_value': float(data['total_value']),
            'total_investments': float(data.get('total_investments', data['total_value'])),
            'total_cash': float(data.get('total_cash', 0)),
            'cash_percentage': data.get('cash_percentage', 0),
            'investment_percentage': data.get('investment_percentage', 100),
            'holdings_count': len(data['holdings']),
            'etf_count': etf_count,
            'mf_count': mf_count,
            'stock_count': stock_count,
            'cash_count': cash_count
        })
        
    except Exception as e:
        logger.error(f"Error getting holdings summary: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500