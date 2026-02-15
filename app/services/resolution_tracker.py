"""
Resolution Tracker Service

Tracks the status of background holdings resolution jobs.
Provides real-time progress information for the UI.

CHANGELOG:
- New file: Created to track background job status
- Provides: Current symbol being processed, progress percentage, timing info
"""
import logging
import threading
from datetime import datetime
from typing import Dict, Optional
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Status file for persistence across requests
STATUS_FILE = Path('/app/data/resolution_status.json')

# Thread-safe lock for status updates
_status_lock = threading.Lock()

# In-memory status (faster than file reads)
_current_status = {
    'is_running': False,
    'snapshot_id': None,
    'current_step': None,  # 'etf_resolution', 'parent_info', 'underlying_info'
    'current_symbol': None,
    'symbols_processed': 0,
    'symbols_total': 0,
    'started_at': None,
    'last_update': None,
    'errors': []
}


def _load_status() -> Dict:
    """Load status from file if exists"""
    global _current_status
    try:
        if STATUS_FILE.exists():
            with open(STATUS_FILE, 'r') as f:
                _current_status = json.load(f)
    except Exception as e:
        logger.error(f"Error loading resolution status: {e}")
    return _current_status


def _save_status():
    """Save status to file"""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATUS_FILE, 'w') as f:
            json.dump(_current_status, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving resolution status: {e}")


def start_resolution(snapshot_id: int, total_symbols: int = 0):
    """
    Mark resolution as started
    
    Args:
        snapshot_id: The snapshot being processed
        total_symbols: Total number of symbols to process
    """
    global _current_status
    with _status_lock:
        _current_status = {
            'is_running': True,
            'snapshot_id': snapshot_id,
            'current_step': 'initializing',
            'current_symbol': None,
            'symbols_processed': 0,
            'symbols_total': total_symbols,
            'started_at': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat(),
            'errors': []
        }
        _save_status()
        logger.info(f"Resolution started for snapshot {snapshot_id} with {total_symbols} symbols")


def update_progress(step: str, symbol: Optional[str] = None, processed: Optional[int] = None, 
                   total: Optional[int] = None, message: Optional[str] = None):
    """
    Update resolution progress
    
    Args:
        step: Current step ('etf_resolution', 'parent_info', 'underlying_info')
        symbol: Current symbol being processed
        processed: Number of symbols processed so far
        total: Total symbols to process (if changed)
        message: Optional status message
    """
    global _current_status
    with _status_lock:
        _current_status['current_step'] = step
        _current_status['last_update'] = datetime.now().isoformat()
        
        if symbol:
            _current_status['current_symbol'] = symbol
        if processed is not None:
            _current_status['symbols_processed'] = processed
        if total is not None:
            _current_status['symbols_total'] = total
        
        _save_status()
        
        if symbol:
            logger.debug(f"Resolution progress: {step} - {symbol} ({processed}/{total})")


def log_error(symbol: str, error: str):
    """
    Log an error during resolution
    
    Args:
        symbol: Symbol that had the error
        error: Error message
    """
    global _current_status
    with _status_lock:
        _current_status['errors'].append({
            'symbol': symbol,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        # Keep only last 50 errors
        _current_status['errors'] = _current_status['errors'][-50:]
        _save_status()
        logger.warning(f"Resolution error for {symbol}: {error}")


def complete_resolution(success: bool = True, message: Optional[str] = None):
    """
    Mark resolution as complete
    
    Args:
        success: Whether resolution completed successfully
        message: Optional completion message
    """
    global _current_status
    with _status_lock:
        _current_status['is_running'] = False
        _current_status['current_step'] = 'complete' if success else 'failed'
        _current_status['current_symbol'] = None
        _current_status['completed_at'] = datetime.now().isoformat()
        _current_status['last_update'] = datetime.now().isoformat()
        if message:
            _current_status['completion_message'] = message
        _save_status()
        
        duration = "unknown"
        if _current_status.get('started_at'):
            try:
                started = datetime.fromisoformat(_current_status['started_at'])
                duration = str(datetime.now() - started)
            except:
                pass
        
        status = "successfully" if success else "with errors"
        logger.info(f"Resolution completed {status} in {duration}. Processed {_current_status['symbols_processed']} symbols.")


def get_resolution_status() -> Dict:
    """
    Get current resolution status
    
    Returns:
        Dict with current status information
    """
    global _current_status
    with _status_lock:
        # Calculate progress percentage
        total = _current_status.get('symbols_total', 0)
        processed = _current_status.get('symbols_processed', 0)
        progress_pct = (processed / total * 100) if total > 0 else 0
        
        # Calculate elapsed time
        elapsed = None
        if _current_status.get('started_at') and _current_status.get('is_running'):
            try:
                started = datetime.fromisoformat(_current_status['started_at'])
                elapsed = str(datetime.now() - started).split('.')[0]  # Remove microseconds
            except:
                pass
        
        return {
            **_current_status,
            'progress_percentage': round(progress_pct, 1),
            'elapsed_time': elapsed,
            'error_count': len(_current_status.get('errors', []))
        }


def is_resolution_running() -> bool:
    """Check if resolution is currently running"""
    global _current_status
    with _status_lock:
        return _current_status.get('is_running', False)


def get_current_symbol() -> Optional[str]:
    """Get the symbol currently being processed"""
    global _current_status
    with _status_lock:
        return _current_status.get('current_symbol')


# Load status on module import
_load_status()