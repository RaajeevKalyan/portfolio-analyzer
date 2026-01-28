"""
Flask Application Entry Point
"""
from flask import Flask, render_template, jsonify
from app.config import get_config
import logging
from logging.handlers import RotatingFileHandler
import os
from app.services.holdings_aggregator import get_current_holdings
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding
from app.services.risk_aggregator import get_risk_metrics
import traceback
import sys
from sqlalchemy import func


def create_app():
    """Application factory"""
    app = Flask(__name__)
    
    # Load configuration
    config = get_config()
    app.config.from_object(config)


    # Validate configuration
    config.validate()


    # Setup logging
    setup_logging(app)

    # Config settings
    app.config['DEBUG'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = True
    
    # Error handler - goes HERE, after config, before routes
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Catch all exceptions and print full traceback"""
        print("\n" + "="*80, file=sys.stderr)
        print("EXCEPTION CAUGHT:", file=sys.stderr)
        print("="*80, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("="*80 + "\n", file=sys.stderr)
        
        return f"""
        <html>
        <head><title>Error</title></head>
        <body>
            <h1>Internal Server Error</h1>
            <pre>{traceback.format_exc()}</pre>
        </body>
        </html>
        """, 500

    # *** ADD THIS - Initialize database ***
    from app.database import init_db
    with app.app_context():
        init_db()
    
    # Register routes
    register_routes(app)
    
    # Create necessary directories
    os.makedirs('/app/data', exist_ok=True)
    os.makedirs('/app/logs', exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    app.logger.info('Portfolio Risk Analyzer started')
    
    return app


def setup_logging(app):
    """Configure application logging"""
    if not app.debug:
        # File handler
        file_handler = RotatingFileHandler(
            app.config['LOG_FILE'],
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)


def register_routes(app):
    """Register application routes"""
    
    # Register blueprints
    from app.routes.upload import upload_bp
    from app.routes.holdings import holdings_bp
    app.register_blueprint(upload_bp)
    app.register_blueprint(holdings_bp)
    
    @app.route('/')
    def dashboard():
        """Dashboard showing all broker accounts and aggregated holdings"""
        try:
            print("\n=== DASHBOARD ROUTE CALLED ===", file=sys.stderr)
            
            # Define all supported brokers
            ALL_BROKERS = ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab',
                           'ally', 'etrade']
            
            with db_session() as session:
                # Get all broker accounts from DB
                db_brokers = session.query(BrokerAccount).all()
                
                # Create a map of broker_name -> BrokerAccount
                broker_map = {b.broker_name: b for b in db_brokers}
                
                brokers_data = []
                total_net_worth = 0
                
                # Show all brokers, whether they have data or not
                for broker_name in ALL_BROKERS:
                    broker = broker_map.get(broker_name)
                    
                    if broker:
                        # Get latest snapshot for this broker
                        latest_snapshot = session.query(PortfolioSnapshot)\
                            .filter(PortfolioSnapshot.broker_account_id == broker.id)\
                            .order_by(PortfolioSnapshot.snapshot_date.desc())\
                            .first()
                        
                        if latest_snapshot:
                            total_net_worth += float(latest_snapshot.total_value)
                            brokers_data.append({
                                'name': broker_name,
                                'display_name': broker_name.replace('_', ' ').title(),
                                'account_last4': broker.account_number_last4,
                                'has_data': True,
                                'total_value': float(latest_snapshot.total_value),
                                'total_positions': latest_snapshot.total_positions,
                                'last_updated': latest_snapshot.snapshot_date.strftime('%b %d, %Y')
                            })
                        else:
                            # Broker exists but no snapshots
                            brokers_data.append({
                                'name': broker_name,
                                'display_name': broker_name.replace('_', ' ').title(),
                                'account_last4': broker.account_number_last4,
                                'has_data': False,
                                'total_value': 0,
                                'total_positions': 0,
                                'last_updated': None
                            })
                    else:
                        # Broker doesn't exist in DB yet
                        brokers_data.append({
                            'name': broker_name,
                            'display_name': broker_name.replace('_', ' ').title(),
                            'account_last4': None,
                            'has_data': False,
                            'total_value': 0,
                            'total_positions': 0,
                            'last_updated': None
                        })
            
            print(f"Total net worth: ${total_net_worth}", file=sys.stderr)
            
            # Get aggregated holdings
            print("Getting holdings...", file=sys.stderr)
            holdings_data = get_current_holdings()
            holdings = holdings_data.get('holdings', [])
            print(f"Got {len(holdings)} holdings", file=sys.stderr)
            
            # NEW: Get risk metrics
            print("Getting risk metrics...", file=sys.stderr)
            risk_metrics = get_risk_metrics()
            print(f"Risk metrics calculated: {risk_metrics.get('overall_risk')} risk", file=sys.stderr)
            
            print("Rendering template...", file=sys.stderr)
            result = render_template('dashboard.html',
                                    brokers=brokers_data,
                                    total_net_worth=total_net_worth,
                                    holdings=holdings,
                                    risk_metrics=risk_metrics)  # ADD THIS
            print("Template rendered successfully!", file=sys.stderr)
            return result
                                
        except Exception as e:
            print("\n" + "="*80, file=sys.stderr)
            print("ERROR IN DASHBOARD ROUTE:", file=sys.stderr)
            print("="*80, file=sys.stderr)
            print(str(e), file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            print("="*80 + "\n", file=sys.stderr)
            raise

    @app.route('/health')
    def health():
        """Health check endpoint for Docker"""
        return {'status': 'healthy', 'service': 'portfolio-analyzer'}, 200

    @app.route('/api/holdings/underlying/<symbol>')
    def get_underlying_holdings(symbol):
        """Get underlying holdings for a specific ETF/MF symbol"""
        try:
            from app.services.holdings_aggregator import get_current_holdings
            
            # Get all current holdings to find this symbol
            holdings_data = get_current_holdings()
            all_holdings = holdings_data.get('holdings', [])
            
            # Find the requested symbol
            target_holding = None
            for holding in all_holdings:
                if holding['symbol'].upper() == symbol.upper():
                    target_holding = holding
                    break
            
            if not target_holding:
                return jsonify({'error': 'Symbol not found'}), 404
            
            # Get direct holdings (to detect overlaps)
            direct_symbols = [h['symbol'] for h in all_holdings if not h['is_etf_or_mf']]
            
            # Fetch underlying holdings from database
            with db_session() as session:
                # Get latest snapshots
                from sqlalchemy import desc
                
                latest_snapshots_subquery = session.query(
                    PortfolioSnapshot.broker_account_id,
                    func.max(PortfolioSnapshot.snapshot_date).label('max_date')
                ).group_by(PortfolioSnapshot.broker_account_id).subquery()
                
                latest_snapshots = session.query(PortfolioSnapshot).join(
                    latest_snapshots_subquery,
                    (PortfolioSnapshot.broker_account_id == latest_snapshots_subquery.c.broker_account_id) &
                    (PortfolioSnapshot.snapshot_date == latest_snapshots_subquery.c.max_date)
                ).all()
                
                snapshot_ids = [s.id for s in latest_snapshots]
                
                # Get all holdings for this symbol
                holdings = session.query(Holding).filter(
                    Holding.portfolio_snapshot_id.in_(snapshot_ids),
                    Holding.symbol == symbol.upper()
                ).all()
                
                if not holdings:
                    return jsonify({'error': 'No holdings found for this symbol'}), 404
                
                # Aggregate underlying holdings across all instances of this fund
                underlying_aggregated = {}
                total_fund_value = 0
                total_fund_quantity = 0
                fund_name = ""
                
                for holding in holdings:
                    if not fund_name:
                        fund_name = holding.name
                    
                    total_fund_value += float(holding.total_value)
                    total_fund_quantity += float(holding.quantity)
                    
                    if not holding.underlying_holdings_list:
                        continue
                    
                    # Process each underlying holding
                    for underlying in holding.underlying_holdings_list:
                        u_symbol = underlying.get('symbol')
                        u_name = underlying.get('name', u_symbol)
                        u_weight = underlying.get('weight', 0)
                        
                        if u_symbol not in underlying_aggregated:
                            underlying_aggregated[u_symbol] = {
                                'symbol': u_symbol,
                                'name': u_name,
                                'weight': 0,
                                'value': 0
                            }
                        
                        # Weight is already a decimal (e.g., 0.072 for 7.2%)
                        # Value for this holding = weight * holding's total value
                        u_value = u_weight * float(holding.total_value)
                        
                        underlying_aggregated[u_symbol]['weight'] += u_weight * (float(holding.total_value) / total_fund_value) if total_fund_value > 0 else 0
                        underlying_aggregated[u_symbol]['value'] += u_value
                
                # Convert to list and sort by value
                underlying_list = list(underlying_aggregated.values())
                underlying_list.sort(key=lambda x: x['value'], reverse=True)
                
                # Calculate average price
                avg_price = total_fund_value / total_fund_quantity if total_fund_quantity > 0 else 0
                
                return jsonify({
                    'symbol': symbol.upper(),
                    'name': fund_name,
                    'total_value': float(total_fund_value),
                    'quantity': float(total_fund_quantity),
                    'price': float(avg_price),
                    'underlying_holdings': underlying_list,
                    'direct_holdings': direct_symbols  # For overlap detection
                })
                
        except Exception as e:
            print(f"Error fetching underlying holdings: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return jsonify({'error': str(e)}), 500


# Create application instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)