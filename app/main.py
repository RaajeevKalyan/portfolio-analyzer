"""
Flask Application Entry Point
"""
from flask import Flask, render_template
from app.config import get_config
import logging
from logging.handlers import RotatingFileHandler
import os


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
    app.register_blueprint(upload_bp)
    
    @app.route('/')
    def index():
        """Dashboard page"""
        from app.database import db_session
        from app.models import BrokerAccount, PortfolioSnapshot
        from sqlalchemy import desc
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # Use db_session context manager (auto-commits)
            with db_session() as session:
                # Get all broker accounts with their latest snapshot
                brokers_data = []
                supported_brokers = ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab']
                
                for broker_name in supported_brokers:
                    # Query by broker_name only (not account_number_last4)
                    broker_account = session.query(BrokerAccount).filter_by(
                        broker_name=broker_name,
                        is_active=True
                    ).first()
                    
                    if broker_account:
                        # Get latest snapshot
                        latest_snapshot = session.query(PortfolioSnapshot).filter_by(
                            broker_account_id=broker_account.id
                        ).order_by(desc(PortfolioSnapshot.snapshot_date)).first()
                        
                        if latest_snapshot:
                            brokers_data.append({
                                'name': broker_name,
                                'display_name': broker_name.replace('_', ' ').title(),
                                'has_data': True,
                                'total_value': float(latest_snapshot.total_value),
                                'total_positions': latest_snapshot.total_positions,
                                'last_updated': latest_snapshot.snapshot_date.strftime('%b %d, %Y %I:%M %p'),
                                'account_last4': broker_account.account_number_last4
                            })
                        else:
                            # Account exists but no snapshots
                            brokers_data.append({
                                'name': broker_name,
                                'display_name': broker_name.replace('_', ' ').title(),
                                'has_data': False,
                                'total_value': 0,
                                'total_positions': 0,
                                'last_updated': None,
                                'account_last4': broker_account.account_number_last4
                            })
                    else:
                        # No account for this broker yet
                        brokers_data.append({
                            'name': broker_name,
                            'display_name': broker_name.replace('_', ' ').title(),
                            'has_data': False,
                            'total_value': 0,
                            'total_positions': 0,
                            'last_updated': None,
                            'account_last4': None
                        })
                
                # Calculate total net worth
                total_net_worth = sum(b['total_value'] for b in brokers_data if b['has_data'])
            
            return render_template('dashboard.html', 
                                brokers=brokers_data,
                                total_net_worth=total_net_worth)
                                
        except Exception as e:
            logger.error(f"Error loading dashboard data: {e}", exc_info=True)
            # Return empty dashboard on error
            return render_template('dashboard.html', 
                                brokers=[
                                    {'name': b, 'display_name': b.replace('_', ' ').title(), 'has_data': False, 
                                    'total_value': 0, 'total_positions': 0, 'last_updated': None, 'account_last4': None}
                                    for b in ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab']
                                ],
                                total_net_worth=0)
        
    @app.route('/health')
    def health():
        """Health check endpoint for Docker"""
        return {'status': 'healthy', 'service': 'portfolio-analyzer'}, 200

# Create application instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)