"""
Flask Application Entry Point

CHANGELOG:
- Added: Cash vs Investment breakdown data passed to dashboard
- Added: Asset type breakdown data
- Improved: Resolution progress endpoint with more details
- Added: Better logging for debugging
"""
from flask import Flask, render_template, jsonify
from app.config import get_config
import logging
from logging.handlers import RotatingFileHandler
import os
from app.services.holdings_aggregator import get_current_holdings, get_cash_breakdown, get_asset_breakdown
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
    from app.routes.fund_analysis import fund_analysis_bp
    from app.routes.portfolio_projection import portfolio_projection_bp
    from app.routes.top_holdings import top_holdings_bp
    app.register_blueprint(upload_bp)
    app.register_blueprint(holdings_bp)
    app.register_blueprint(fund_analysis_bp)
    app.register_blueprint(portfolio_projection_bp)
    app.register_blueprint(top_holdings_bp)
    
    @app.route('/')
    def dashboard():
        """Dashboard showing all broker accounts and aggregated holdings"""
        try:
            print("\n=== DASHBOARD ROUTE CALLED ===", file=sys.stderr)
            
            # Define all supported brokers
            ALL_BROKERS = ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab',
                           'ally', 'etrade', 'wellsfargo']
            
            with db_session() as session:
                # OPTIMIZED: Single query to get all brokers with their latest snapshots
                from sqlalchemy import func
                from sqlalchemy.orm import joinedload
                
                # Subquery: get max snapshot date per broker
                latest_date_subq = session.query(
                    PortfolioSnapshot.broker_account_id,
                    func.max(PortfolioSnapshot.snapshot_date).label('max_date')
                ).group_by(PortfolioSnapshot.broker_account_id).subquery()
                
                # Get all brokers with their latest snapshot (if any) in ONE query
                brokers_with_snapshots = session.query(
                    BrokerAccount,
                    PortfolioSnapshot
                ).outerjoin(
                    latest_date_subq,
                    BrokerAccount.id == latest_date_subq.c.broker_account_id
                ).outerjoin(
                    PortfolioSnapshot,
                    (PortfolioSnapshot.broker_account_id == BrokerAccount.id) &
                    (PortfolioSnapshot.snapshot_date == latest_date_subq.c.max_date)
                ).all()
                
                # Create map of broker_name -> (BrokerAccount, PortfolioSnapshot)
                broker_map = {b.broker_name: (b, s) for b, s in brokers_with_snapshots}
                
                brokers_data = []
                total_net_worth = 0
                
                # Show all brokers, whether they have data or not
                for broker_name in ALL_BROKERS:
                    broker_data = broker_map.get(broker_name)
                    
                    if broker_data:
                        broker, latest_snapshot = broker_data
                        
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
            
            # Get aggregated holdings (includes cash breakdown)
            print("Getting holdings...", file=sys.stderr)
            holdings_data = get_current_holdings()
            holdings = holdings_data.get('holdings', [])
            
            # Sort holdings by allocation percentage (descending)
            holdings = sorted(holdings, key=lambda h: float(h.get('allocation_pct', 0)), reverse=True)
            
            # Extract cash vs investment data
            total_cash = float(holdings_data.get('total_cash', 0))
            total_investments = float(holdings_data.get('total_investments', total_net_worth))
            cash_percentage = holdings_data.get('cash_percentage', 0)
            investment_percentage = holdings_data.get('investment_percentage', 100)
            
            print(f"Got {len(holdings)} holdings", file=sys.stderr)
            print(f"Investments: ${total_investments} ({investment_percentage:.1f}%)", file=sys.stderr)
            print(f"Cash: ${total_cash} ({cash_percentage:.1f}%)", file=sys.stderr)
            
            # Get asset type breakdown
            print("Getting asset breakdown...", file=sys.stderr)
            asset_breakdown = get_asset_breakdown()
            print(f"Asset breakdown: {len(asset_breakdown.get('breakdown', []))} types", file=sys.stderr)
            
            # Get risk metrics
            print("Getting risk metrics...", file=sys.stderr)
            risk_metrics = get_risk_metrics()
            print(f"Risk metrics calculated: {risk_metrics.get('overall_risk')} risk", file=sys.stderr)
            
            print("Rendering template...", file=sys.stderr)
            result = render_template('dashboard.html',
                                    brokers=brokers_data,
                                    total_net_worth=total_net_worth,
                                    holdings=holdings,
                                    # Cash breakdown data
                                    total_cash=total_cash,
                                    total_investments=total_investments,
                                    cash_percentage=cash_percentage,
                                    investment_percentage=investment_percentage,
                                    # Asset breakdown for charts
                                    asset_breakdown=asset_breakdown,
                                    # Risk metrics
                                    risk_metrics=risk_metrics)
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
    
    @app.route('/favicon.ico')
    def favicon():
        """Return empty favicon to prevent 404 errors"""
        return '', 204  # No content
    
    # Suppress noisy 404 logging for common missing assets
    @app.errorhandler(404)
    def handle_404(e):
        """Handle 404 errors quietly for static assets"""
        from flask import request
        # Don't log 404s for common static asset requests
        ignored_paths = ['/favicon.ico', '/apple-touch-icon', '/robots.txt', '/sitemap.xml']
        if any(request.path.startswith(p) for p in ignored_paths):
            return '', 404
        # For actual page 404s, return a proper error page
        print(f"404 Not Found: {request.path}", file=sys.stderr)
        return f"<h1>404 Not Found</h1><p>The requested URL {request.path} was not found.</p>", 404

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
            
            # Get direct holdings (to detect overlaps) - exclude cash
            direct_symbols = [h['symbol'] for h in all_holdings 
                            if not h['is_etf_or_mf'] and h['asset_type'] != 'cash']
            
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
                        u_sector = underlying.get('sector', 'Unknown')
                        u_country = underlying.get('country', 'Unknown')
                        
                        if u_symbol not in underlying_aggregated:
                            underlying_aggregated[u_symbol] = {
                                'symbol': u_symbol,
                                'name': u_name,
                                'weight': 0,
                                'value': 0,
                                'sector': u_sector,
                                'country': u_country
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
    
    @app.route('/api/resolution/progress')
    def resolution_progress():
        """
        Get current holdings resolution progress
        
        Returns JSON with:
        - is_resolving: bool (if still fetching data)
        - cached_symbols: int
        - requests_this_hour: int
        - rate_limit: int
        - unresolved_count: int
        - etf_mf_unresolved: int
        - current_symbol: str (if currently processing)
        """
        try:
            from app.services.stock_info_service import get_progress_stats
            from app.services.resolution_tracker import get_resolution_status
            
            # Get stock info progress stats
            stats = get_progress_stats()
            
            # Get resolution tracker status
            resolution_status = get_resolution_status()
            
            # Check if any holdings still need sector info
            with db_session() as session:
                unresolved = session.query(Holding).filter(
                    Holding.info_fetched == False
                ).count()
                
                etf_mf_unresolved = session.query(Holding).filter(
                    Holding.asset_type.in_(['etf', 'mutual_fund']),
                    Holding.underlying_parsed == False
                ).count()
                
                # Get total holdings for percentage calculation
                total_holdings = session.query(Holding).count()
                resolved_holdings = session.query(Holding).filter(
                    Holding.info_fetched == True
                ).count()
                
                # Count total underlying symbols that need processing
                total_underlying = 0
                resolved_etfs = session.query(Holding).filter(
                    Holding.asset_type.in_(['etf', 'mutual_fund']),
                    Holding.underlying_parsed == True
                ).all()
                
                for etf in resolved_etfs:
                    if etf.underlying_holdings_list:
                        total_underlying += len(etf.underlying_holdings_list)
            
            is_resolving = resolution_status.get('is_running', False) or (unresolved > 0) or (etf_mf_unresolved > 0)
            
            # Get progress from tracker (more accurate)
            tracker_progress = resolution_status.get('progress_percentage', 0)
            tracker_remaining = resolution_status.get('total_remaining', unresolved + total_underlying)
            
            # Calculate progress percentage (use tracker value if available, else compute)
            if resolution_status.get('is_running'):
                progress_pct = tracker_progress
            else:
                progress_pct = (resolved_holdings / total_holdings * 100) if total_holdings > 0 else 100
            
            return jsonify({
                'is_resolving': is_resolving,
                'unresolved_count': unresolved,
                'etf_mf_unresolved': etf_mf_unresolved,
                'total_holdings': total_holdings,
                'resolved_holdings': resolved_holdings,
                'progress_percentage': round(progress_pct, 1),
                'cached_symbols': stats.get('cached_symbols', 0),
                'requests_this_hour': stats.get('requests_this_hour', 0),
                'rate_limit': stats.get('rate_limit', 2000),
                'current_symbol': resolution_status.get('current_symbol', None),
                'current_step': resolution_status.get('current_step', None),
                'started_at': resolution_status.get('started_at', None),
                'last_update': resolution_status.get('last_update', None),
                # NEW: Detailed tracking from resolution_tracker
                'parent_symbols_total': resolution_status.get('parent_symbols_total', total_holdings),
                'parent_symbols_processed': resolution_status.get('parent_symbols_processed', resolved_holdings),
                'underlying_symbols_total': resolution_status.get('underlying_symbols_total', total_underlying),
                'underlying_symbols_processed': resolution_status.get('underlying_symbols_processed', 0),
                'total_remaining': tracker_remaining,
                'cached_hits': resolution_status.get('cached_hits', 0),
                'api_calls': resolution_status.get('api_calls', 0),
                'elapsed_time': resolution_status.get('elapsed_time', None)
            })
            
        except ImportError:
            # Resolution tracker not yet available, fall back to basic check
            try:
                from app.services.stock_info_service import get_progress_stats
                stats = get_progress_stats()
                
                with db_session() as session:
                    unresolved = session.query(Holding).filter(
                        Holding.info_fetched == False
                    ).count()
                    
                    etf_mf_unresolved = session.query(Holding).filter(
                        Holding.asset_type.in_(['etf', 'mutual_fund']),
                        Holding.underlying_parsed == False
                    ).count()
                
                is_resolving = (unresolved > 0) or (etf_mf_unresolved > 0)
                
                return jsonify({
                    'is_resolving': is_resolving,
                    'unresolved_count': unresolved,
                    'etf_mf_unresolved': etf_mf_unresolved,
                    'cached_symbols': stats.get('cached_symbols', 0),
                    'requests_this_hour': stats.get('requests_this_hour', 0),
                    'rate_limit': stats.get('rate_limit', 2000)
                })
            except Exception as e:
                return jsonify({
                    'is_resolving': False,
                    'error': str(e)
                }), 500
                
        except Exception as e:
            print(f"Error getting resolution progress: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return jsonify({
                'is_resolving': False,
                'error': str(e)
            }), 500
    
    @app.route('/api/cash-breakdown')
    def api_cash_breakdown():
        """API endpoint for cash vs investments breakdown"""
        try:
            data = get_cash_breakdown()
            return jsonify(data)
        except Exception as e:
            print(f"Error getting cash breakdown: {e}", file=sys.stderr)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/asset-breakdown')
    def api_asset_breakdown():
        """API endpoint for asset type breakdown"""
        try:
            data = get_asset_breakdown()
            return jsonify(data)
        except Exception as e:
            print(f"Error getting asset breakdown: {e}", file=sys.stderr)
            return jsonify({'error': str(e)}), 500


# Create application instance
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)