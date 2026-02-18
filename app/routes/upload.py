"""
CSV Upload Routes - FIXED VERSION with Sector/Country Resolution

Handles file uploads from broker CSV exports and resolves:
1. ETF/MF underlying holdings
2. Sector/country for parent holdings
3. Sector/country for underlying holdings
"""
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding
from app.services.merrill_csv_parser import MerrillCSVParser
from datetime import datetime
from decimal import Decimal
import os
import logging
import threading

logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'csv'}

# Broker parser mapping
PARSERS = {
    'merrill': MerrillCSVParser,
    # Add more as we implement them:
    # 'fidelity': FidelityCSVParser,
    # 'webull': WebullCSVParser,
    # etc.
}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@upload_bp.route('/upload', methods=['POST'])
def upload_csv():
    """
    Handle CSV file upload
    
    Expected form data:
    - file: CSV file
    - broker: Broker name ('merrill', 'fidelity', etc.)
    
    Returns:
        JSON: {
            'success': bool,
            'message': str,
            'data': {
                'broker_name': str,
                'total_value': float,
                'total_positions': int,
                'snapshot_id': int
            }
        }
    """
    # DIAGNOSTIC LOGGING
    logger.info("="*80)
    logger.info("UPLOAD ENDPOINT CALLED!")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request files: {list(request.files.keys())}")
    logger.info(f"Request form: {dict(request.form)}")
    logger.info("="*80)
    
    try:
        # Validate request
        if 'file' not in request.files:
            logger.error("No file in request.files")
            return jsonify({
                'success': False,
                'message': 'No file provided'
            }), 400
        
        if 'broker' not in request.form:
            logger.error("No broker in request.form")
            return jsonify({
                'success': False,
                'message': 'Broker name not specified'
            }), 400
        
        file = request.files['file']
        broker_name = request.form['broker'].lower()
        
        logger.info(f"File: {file.filename}, Broker: {broker_name}")
        
        # Validate file
        if file.filename == '':
            logger.error("Empty filename")
            return jsonify({
                'success': False,
                'message': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            logger.error(f"File extension not allowed: {file.filename}")
            return jsonify({
                'success': False,
                'message': 'Invalid file type. Only CSV files are allowed.'
            }), 400
        
        # Validate broker
        if broker_name not in PARSERS:
            logger.error(f"Unsupported broker: {broker_name}")
            logger.error(f"Available parsers: {list(PARSERS.keys())}")
            return jsonify({
                'success': False,
                'message': f'Unsupported broker: {broker_name}. Supported: {", ".join(PARSERS.keys())}'
            }), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        upload_folder = os.getenv('UPLOAD_FOLDER', '/app/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, f"{broker_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}")
        file.save(file_path)
        
        logger.info(f"File saved to: {file_path}")
        
        # Parse CSV
        parser_class = PARSERS[broker_name]
        logger.info(f"Using parser: {parser_class.__name__}")
        parser = parser_class()
        
        # Validate CSV format
        logger.info("Validating CSV format...")
        is_valid, error_message = parser.validate_csv(file_path)
        logger.info(f"Validation result: {is_valid}, Error: {error_message}")
        
        if not is_valid:
            os.remove(file_path)  # Clean up
            return jsonify({
                'success': False,
                'message': f'Invalid CSV format: {error_message}'
            }), 400
        
        # Parse CSV data
        try:
            logger.info("Parsing CSV data...")
            parsed_data = parser.parse_csv(file_path)
            logger.info(f"Parse complete! Holdings: {len(parsed_data.get('holdings', []))}")
            logger.info(f"Total value: ${parsed_data.get('total_value', 0)}")
            
            # Print first holding as sample
            if parsed_data.get('holdings'):
                first = parsed_data['holdings'][0]
                logger.info(f"Sample holding: {first['symbol']} - {first['quantity']} @ ${first['price']}")
            
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}", exc_info=True)
            os.remove(file_path)  # Clean up
            return jsonify({
                'success': False,
                'message': f'Error parsing CSV: {str(e)}'
            }), 400
        
        # Store in database
        logger.info("Storing data in database...")
        try:
            snapshot_id = store_portfolio_data(
                broker_name=broker_name,
                parsed_data=parsed_data,
                csv_filename=filename
            )
            logger.info(f"Data stored! Snapshot ID: {snapshot_id}")
        except Exception as e:
            logger.error(f"Error storing data: {e}", exc_info=True)
            raise
        
        # CRITICAL: Resolve holdings in background thread
        logger.info(f"Starting background resolution for snapshot {snapshot_id}...")
        threading.Thread(
            target=resolve_holdings_background,
            args=(snapshot_id,),
            daemon=True
        ).start()
        
        logger.info(f"Successfully processed {broker_name} CSV: {len(parsed_data['holdings'])} holdings, ${parsed_data['total_value']}")
        logger.info("="*80)
        
        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {len(parsed_data["holdings"])} positions',
            'data': {
                'broker_name': broker_name,
                'total_value': float(parsed_data['total_value']),
                'total_positions': len(parsed_data['holdings']),
                'snapshot_id': snapshot_id,
                'account_last4': parsed_data.get('account_number_last4')
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500


def resolve_holdings_background(snapshot_id: int):
    """
    Background task to resolve ALL holdings data:
    1. ETF/MF underlying holdings (via mstarpy)
    2. Sector/country for parent holdings (via yfinance)
    3. Sector/country for underlying holdings (via yfinance)
    
    Runs in a separate thread to avoid blocking the upload response.
    """
    try:
        logger.info("="*80)
        logger.info(f"BACKGROUND RESOLUTION STARTED for snapshot {snapshot_id}")
        logger.info("="*80)
        
        # Import here to avoid circular imports
        from app.services.holdings_resolver import resolve_snapshot_holdings
        
        # This will:
        # 1. Resolve ETF/MF underlying holdings
        # 2. Fetch sector/country for all parent holdings
        # 3. Fetch sector/country for all underlying holdings
        resolved_count = resolve_snapshot_holdings(snapshot_id)
        
        logger.info("="*80)
        logger.info(f"BACKGROUND RESOLUTION COMPLETE for snapshot {snapshot_id}")
        logger.info(f"Resolved {resolved_count} ETF/MF holdings")
        logger.info("="*80)
        
    except Exception as e:
        logger.error("="*80)
        logger.error(f"ERROR in background resolution for snapshot {snapshot_id}")
        logger.error(str(e))
        logger.exception(e)
        logger.error("="*80)


def store_portfolio_data(broker_name: str, parsed_data: dict, csv_filename: str) -> int:
    """
    Store parsed portfolio data in database
    
    Args:
        broker_name: Broker identifier
        parsed_data: Parsed CSV data from parser
        csv_filename: Original CSV filename
        
    Returns:
        int: Created PortfolioSnapshot ID
    """
    from datetime import datetime as dt
    
    with db_session() as session:
        # Get or create broker account
        account_last4 = parsed_data.get('account_number_last4')
        
        broker_account = session.query(BrokerAccount).filter_by(
            broker_name=broker_name,
            account_number_last4=account_last4
        ).first()
        
        if not broker_account:
            # Create new broker account
            broker_account = BrokerAccount(
                broker_name=broker_name,
                account_number_last4=account_last4,
                account_nickname=f"{broker_name.title()} Account",
                is_active=True
            )
            session.add(broker_account)
            session.flush()  # Get ID
            logger.info(f"Created new broker account: {broker_name} (***{account_last4})")
        
        # Update last upload timestamp
        broker_account.last_uploaded_at = datetime.utcnow()
        broker_account.last_csv_filename = csv_filename
        
        # Determine snapshot date - prefer export_timestamp from CSV, fall back to upload time
        snapshot_date = datetime.utcnow()
        export_timestamp = parsed_data.get('export_timestamp')
        if export_timestamp:
            try:
                # Parse ISO format timestamp
                snapshot_date = dt.fromisoformat(export_timestamp)
                logger.info(f"Using export timestamp from CSV: {snapshot_date}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse export_timestamp '{export_timestamp}': {e}")
        
        # Create portfolio snapshot
        snapshot = PortfolioSnapshot(
            broker_account_id=broker_account.id,
            snapshot_date=snapshot_date,
            total_value=parsed_data['total_value'],
            total_positions=len(parsed_data['holdings']),
            upload_source='csv_upload',
            csv_filename=csv_filename
        )
        session.add(snapshot)
        session.flush()  # Get ID
        
        logger.info(f"Created snapshot {snapshot.id} for {broker_name}: ${snapshot.total_value}, {snapshot.total_positions} positions")
        
        # Create holdings
        for holding_data in parsed_data['holdings']:
            holding = Holding(
                portfolio_snapshot_id=snapshot.id,
                symbol=holding_data['symbol'],
                name=holding_data['name'],
                quantity=holding_data['quantity'],
                price=holding_data['price'],
                total_value=holding_data['total_value'],
                asset_type=holding_data['asset_type'],
                account_type=holding_data.get('account_type'),
                underlying_parsed=False,  # Will be parsed by background task
                info_fetched=False  # Will be fetched by background task
            )
            session.add(holding)
        
        logger.info(f"Created {len(parsed_data['holdings'])} holdings for snapshot {snapshot.id}")
        
        # Commit to database
        session.commit()
        
        # Return snapshot ID
        return snapshot.id


@upload_bp.route('/api/broker/<broker_name>/snapshots', methods=['GET'])
def get_broker_snapshots(broker_name):
    """
    Get recent snapshots for a broker (for history tab)
    Returns last 6 snapshots with dates and values - REAL DATA ONLY
    """
    try:
        with db_session() as session:
            broker = session.query(BrokerAccount).filter_by(
                broker_name=broker_name.lower()
            ).first()
            
            if not broker:
                return jsonify({'success': True, 'snapshots': []})
            
            snapshots = session.query(PortfolioSnapshot)\
                .filter(PortfolioSnapshot.broker_account_id == broker.id)\
                .order_by(PortfolioSnapshot.snapshot_date.desc())\
                .limit(6)\
                .all()
            
            return jsonify({
                'success': True,
                'snapshots': [{
                    'id': s.id,
                    'date': s.snapshot_date.strftime('%b %d, %Y %H:%M'),
                    'total_value': float(s.total_value),
                    'positions': s.total_positions,
                    'filename': s.csv_filename
                } for s in snapshots]
            })
            
    except Exception as e:
        logger.error(f"Error getting snapshots: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@upload_bp.route('/api/broker/<broker_name>/history', methods=['GET'])
def get_broker_history(broker_name):
    """
    Get value history for a broker (for chart)
    Returns all snapshots for chart plotting - REAL DATA ONLY
    """
    try:
        with db_session() as session:
            broker = session.query(BrokerAccount).filter_by(
                broker_name=broker_name.lower()
            ).first()
            
            if not broker:
                return jsonify({'success': True, 'history': []})
            
            snapshots = session.query(PortfolioSnapshot)\
                .filter(PortfolioSnapshot.broker_account_id == broker.id)\
                .order_by(PortfolioSnapshot.snapshot_date.asc())\
                .all()
            
            return jsonify({
                'success': True,
                'history': [{
                    'date': s.snapshot_date.strftime('%b %d'),
                    'value': float(s.total_value)
                } for s in snapshots]
            })
            
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500