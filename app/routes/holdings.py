"""
Holdings Routes

Display aggregated portfolio holdings across all brokers.
"""
from flask import Blueprint, render_template
from app.services.holdings_aggregator import get_current_holdings
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
    """
    try:
        # Get aggregated holdings data
        data = get_current_holdings()
        
        logger.info(f"Displaying {len(data['holdings'])} aggregated holdings")
        logger.info(f"Total portfolio value: ${data['total_value']}")
        logger.info(f"Detected {len(data.get('overlaps', {}))} overlaps")
        
        return render_template(
            'holdings.html',
            holdings=data['holdings'],
            total_value=data['total_value'],
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
            total_value=0,
            overlaps={},
            direct_holdings={},
            underlying_holdings={},
            error_message=str(e)
        )