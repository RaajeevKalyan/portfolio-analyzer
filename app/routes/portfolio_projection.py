"""
Portfolio Projection Routes - Future Value and Risk Metrics API

Endpoints:
- GET /api/portfolio/projections - Get future value projections
- GET /api/portfolio/risk-metrics - Get risk metrics for top funds
"""
from flask import Blueprint, jsonify, request
import logging
from app.services.portfolio_projection_service import PortfolioProjectionService
from app.services.holdings_aggregator import HoldingsAggregator

logger = logging.getLogger(__name__)

portfolio_projection_bp = Blueprint('portfolio_projection', __name__)


@portfolio_projection_bp.route('/api/portfolio/projections', methods=['GET'])
def get_portfolio_projections():
    """
    Get future portfolio value projections with confidence intervals
    
    Returns:
        JSON with projections and risk metrics
    """
    try:
        # Get current holdings
        aggregator = HoldingsAggregator()
        holdings_data = aggregator.get_aggregated_holdings()
        holdings = holdings_data.get('holdings', [])
        total_value = float(holdings_data.get('total_value', 0))
        
        if total_value == 0:
            return jsonify({
                'success': True,
                'data': {
                    'current_value': 0,
                    'risk_metrics': {
                        'fund_metrics': [],
                        'portfolio_beta': 0,
                        'portfolio_sharpe': 0,
                        'portfolio_volatility': 0
                    },
                    'projections': [],
                    'assumptions': {}
                },
                'message': 'No holdings found'
            })
        
        # Get projections
        service = PortfolioProjectionService()
        projection_data = service.get_projection_summary(holdings, total_value)
        
        return jsonify({
            'success': True,
            'data': projection_data
        })
        
    except Exception as e:
        logger.error(f"Error getting projections: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@portfolio_projection_bp.route('/api/portfolio/risk-metrics', methods=['GET'])
def get_risk_metrics():
    """
    Get risk metrics (beta, sharpe, volatility) for top funds
    
    Returns:
        JSON with fund-level and portfolio-level risk metrics
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
                    'fund_metrics': [],
                    'portfolio_beta': 0,
                    'portfolio_sharpe': 0,
                    'portfolio_volatility': 0,
                    'total_analyzed_value': 0
                },
                'message': 'No holdings found'
            })
        
        # Get risk metrics
        service = PortfolioProjectionService()
        risk_data = service.get_portfolio_risk_metrics(holdings)
        
        return jsonify({
            'success': True,
            'data': risk_data
        })
        
    except Exception as e:
        logger.error(f"Error getting risk metrics: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500