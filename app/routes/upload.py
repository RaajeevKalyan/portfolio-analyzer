"""
CSV Upload Routes - Updated with Holdings Resolution

Handles file uploads from broker CSV exports and resolves ETF/MF holdings.
"""
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding
from app.services.merrill_csv_parser import MerrillCSVParser
from app.services.holdings_resolver import resolve_snapshot_holdings
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
    print("="*80)
    print("UPLOAD ENDPOINT CALLED!")
    print(f"Request method: {request.method}")
    print(f"Request files: {list(request.files.keys())}")
    print(f"Request form: {dict(request.form)}")
    print("="*80)
    
    try:
        # Validate request
        if 'file' not in request.files:
            print("ERROR: No file in request.files")
            return jsonify({
                'success': False,
                'message': 'No file provided'
            }), 400
        
        if 'broker' not in request.form:
            print("ERROR: No broker in request.form")
            return jsonify({
                'success': False,
                'message': 'Broker name not specified'
            }), 400
        
        file = request.files['file']
        broker_name = request.form['broker'].lower()
        
        print(f"File: {file.filename}, Broker: {broker_name}")
        
        # Validate file
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({
                'success': False,
                'message': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            print(f"ERROR: File extension not allowed: {file.filename}")
            return jsonify({
                'success': False,
                'message': 'Invalid file type. Only CSV files are allowed.'
            }), 400
        
        # Validate broker
        if broker_name not in PARSERS:
            print(f"ERROR: Unsupported broker: {broker_name}")
            print(f"Available parsers: {list(PARSERS.keys())}")
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
        
        print(f"File saved to: {file_path}")
        logger.info(f"Uploaded file saved: {file_path}")
        
        # Parse CSV
        parser_class = PARSERS[broker_name]
        print(f"Using parser: {parser_class.__name__}")
        parser = parser_class()
        print("Parser instantiated successfully")
        
        # Validate CSV format
        print("Validating CSV format...")
        is_valid, error_message = parser.validate_csv(file_path)
        print(f"Validation result: {is_valid}, Error: {error_message}")
        
        if not is_valid:
            os.remove(file_path)  # Clean up
            return jsonify({
                'success': False,
                'message': f'Invalid CSV format: {error_message}'
            }), 400
        
        # Parse CSV data
        try:
            print("Parsing CSV data...")
            parsed_data = parser.parse_csv(file_path)
            print(f"Parse complete! Holdings: {len(parsed_data.get('holdings', []))}")
            print(f"Total value: ${parsed_data.get('total_value', 0)}")
            print(f"Account: ***{parsed_data.get('account_number_last4', 'None')}")
            
            # Print first holding as sample
            if parsed_data.get('holdings'):
                first = parsed_data['holdings'][0]
                print(f"Sample holding: {first['symbol']} - {first['quantity']} @ ${first['price']}")
            
        except Exception as e:
            print(f"ERROR during parsing: {e}")
            logger.error(f"Error parsing CSV: {e}", exc_info=True)
            os.remove(file_path)  # Clean up
            return jsonify({
                'success': False,
                'message': f'Error parsing CSV: {str(e)}'
            }), 400
        
        # Store in database
        print("Storing data in database...")
        try:
            snapshot_id = store_portfolio_data(
                broker_name=broker_name,
                parsed_data=parsed_data,
                csv_filename=filename
            )
            print(f"Data stored! Snapshot ID: {snapshot_id}")
        except Exception as e:
            print(f"ERROR storing data: {e}")
            logger.error(f"Error storing data: {e}", exc_info=True)
            raise
        
        # Resolve ETF/MF holdings in background thread
        print("Starting background holdings resolution...")
        threading.Thread(
            target=resolve_holdings_background,
            args=(snapshot_id,),
            daemon=True
        ).start()
        
        # Clean up uploaded file (optional - keep for debugging)
        # os.remove(file_path)
        
        logger.info(f"Successfully processed {broker_name} CSV: {len(parsed_data['holdings'])} holdings, ${parsed_data['total_value']}")
        
        print(f"SUCCESS! Returning response...")
        print("="*80)
        
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
        print(f"EXCEPTION in upload_csv: {e}")
        logger.error(f"Upload error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500


def resolve_holdings_background(snapshot_id: int):
    """
    Background task to resolve ETF/MF holdings
    
    Runs in a separate thread to avoid blocking the upload response
    """
    try:
        logger.info(f"Background task started: resolving holdings for snapshot {snapshot_id}")
        resolved_count = resolve_snapshot_holdings(snapshot_id)
        logger.info(f"Background task complete: resolved {resolved_count} holdings for snapshot {snapshot_id}")
    except Exception as e:
        logger.error(f"Error in background holdings resolution for snapshot {snapshot_id}: {e}")
        logger.exception(e)


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
        
        # Create portfolio snapshot
        snapshot = PortfolioSnapshot(
            broker_account_id=broker_account.id,
            snapshot_date=datetime.utcnow(),
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
                underlying_parsed=False  # Will be parsed by background task
            )
            session.add(holding)
        
        logger.info(f"Created {len(parsed_data['holdings'])} holdings for snapshot {snapshot.id}")
        
        # Return snapshot ID
        return snapshot.id