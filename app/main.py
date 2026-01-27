"""
Flask Application Entry Point
"""
from flask import Flask, render_template
from app.config import get_config
import logging
from logging.handlers import RotatingFileHandler
import os
from app.services.holdings_aggregator import get_current_holdings
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot
import traceback
import sys


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
            ALL_BROKERS = ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab']
            
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
            
            print("Rendering template...", file=sys.stderr)
            result = render_template('dashboard.html',
                                    brokers=brokers_data,
                                    total_net_worth=total_net_worth,
                                    holdings=holdings)
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

# Create application instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)