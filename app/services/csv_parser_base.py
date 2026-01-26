"""
Base CSV Parser

Abstract base class for broker-specific CSV parsers.
Each broker has different CSV formats, so we need custom parsers.
"""
from abc import ABC, abstractmethod
import pandas as pd
from typing import List, Dict, Optional
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class CSVParserBase(ABC):
    """Abstract base class for CSV parsers"""
    
    def __init__(self):
        self.broker_name = None  # Set by subclass
        self.df = None  # Pandas DataFrame
        
    @abstractmethod
    def validate_csv(self, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate CSV format and structure
        
        Args:
            file_path: Path to CSV file
            
        Returns:
            tuple: (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    def parse_csv(self, file_path: str) -> Dict:
        """
        Parse CSV and extract portfolio data
        
        Args:
            file_path: Path to CSV file
            
        Returns:
            dict: {
                'account_number_last4': str,
                'total_value': Decimal,
                'holdings': List[Dict]
            }
        """
        pass
    
    @abstractmethod
    def extract_account_number(self, df: pd.DataFrame) -> Optional[str]:
        """
        Extract account number (last 4 digits) from CSV
        
        Args:
            df: Pandas DataFrame
            
        Returns:
            str: Last 4 digits of account number, or None
        """
        pass
    
    def clean_currency(self, value: str) -> Decimal:
        """
        Clean currency string and convert to Decimal
        
        Args:
            value: Currency string like '$1,234.56' or '($123.45)'
            
        Returns:
            Decimal: Cleaned numeric value
        """
        if pd.isna(value) or value == '':
            return Decimal('0.00')
        
        # Convert to string if not already
        value = str(value)
        
        # Handle negative values in parentheses: ($123.45) -> -123.45
        is_negative = value.strip().startswith('(') and value.strip().endswith(')')
        
        # Remove currency symbols, commas, parentheses, spaces
        cleaned = value.replace('$', '').replace(',', '').replace('(', '').replace(')', '').strip()
        
        try:
            result = Decimal(cleaned)
            return -result if is_negative else result
        except Exception as e:
            logger.warning(f"Could not parse currency value '{value}': {e}")
            return Decimal('0.00')
    
    def clean_quantity(self, value: str) -> Decimal:
        """
        Clean quantity string and convert to Decimal
        
        Args:
            value: Quantity string like '100' or '100.5'
            
        Returns:
            Decimal: Cleaned numeric value
        """
        if pd.isna(value) or value == '':
            return Decimal('0.00')
        
        # Remove commas
        cleaned = str(value).replace(',', '').strip()
        
        try:
            return Decimal(cleaned)
        except Exception as e:
            logger.warning(f"Could not parse quantity value '{value}': {e}")
            return Decimal('0.00')
    
    def detect_asset_type(self, symbol: str, description: str = '') -> str:
        """
        Detect asset type from symbol and description
        
        Args:
            symbol: Stock/fund symbol
            description: Asset description
            
        Returns:
            str: Asset type ('stock', 'etf', 'mutual_fund', 'bond', 'cash', 'other')
        """
        symbol_upper = symbol.upper() if symbol else ''
        desc_upper = description.upper() if description else ''
        
        # Cash equivalents
        if any(keyword in symbol_upper for keyword in ['CASH', 'MONEY MARKET', 'SWEEP']):
            return 'cash'
        if any(keyword in desc_upper for keyword in ['CASH', 'MONEY MARKET', 'SWEEP']):
            return 'cash'
        
        # Bonds
        if any(keyword in desc_upper for keyword in ['BOND', 'TREASURY', 'NOTE']):
            return 'bond'
        
        # Mutual Funds (usually have 5 characters and end with X)
        if len(symbol_upper) == 5 and symbol_upper.endswith('X'):
            return 'mutual_fund'
        
        # Check description for fund keywords
        if any(keyword in desc_upper for keyword in ['FUND', 'INDEX', 'MUTUAL']):
            # ETFs usually have 3-4 letter symbols
            if len(symbol_upper) <= 4:
                return 'etf'
            else:
                return 'mutual_fund'
        
        # Common ETF patterns
        if any(keyword in desc_upper for keyword in ['ETF', 'ISHARES', 'VANGUARD', 'SPDR']):
            return 'etf'
        
        # Default to stock
        return 'stock'
    
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize stock symbol (uppercase, trim)
        
        Args:
            symbol: Raw symbol
            
        Returns:
            str: Normalized symbol
        """
        if pd.isna(symbol) or symbol == '':
            return ''
        
        return str(symbol).strip().upper()
    
    def load_csv(self, file_path: str, **kwargs) -> pd.DataFrame:
        """
        Load CSV file into pandas DataFrame
        
        Args:
            file_path: Path to CSV file
            **kwargs: Additional arguments for pd.read_csv
            
        Returns:
            pd.DataFrame: Loaded data
        """
        try:
            # Default pandas read_csv options
            default_options = {
                'skipinitialspace': True,
                'encoding': 'utf-8',
                'on_bad_lines': 'skip'  # Skip malformed lines
            }
            default_options.update(kwargs)
            
            self.df = pd.read_csv(file_path, **default_options)
            
            # Strip whitespace from column names
            self.df.columns = self.df.columns.str.strip()
            
            logger.info(f"Loaded CSV with {len(self.df)} rows and {len(self.df.columns)} columns")
            logger.debug(f"Columns: {list(self.df.columns)}")
            
            return self.df
            
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            raise
    
    def get_required_columns(self) -> List[str]:
        """
        Get list of required columns for this broker
        Override in subclass if needed
        
        Returns:
            List[str]: Required column names
        """
        return []
    
    def validate_columns(self, df: pd.DataFrame, required_columns: List[str]) -> tuple[bool, Optional[str]]:
        """
        Validate that required columns exist
        
        Args:
            df: DataFrame to validate
            required_columns: List of required column names
            
        Returns:
            tuple: (is_valid, error_message)
        """
        missing_columns = []
        
        for col in required_columns:
            # Case-insensitive column matching
            if not any(col.lower() == existing.lower() for existing in df.columns):
                missing_columns.append(col)
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}"
        
        return True, None
    
    def find_column(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """
        Find column by trying multiple possible names (case-insensitive)
        
        Args:
            df: DataFrame
            possible_names: List of possible column names to try
            
        Returns:
            str: Actual column name if found, None otherwise
        """
        for possible in possible_names:
            for actual in df.columns:
                if possible.lower() == actual.lower():
                    return actual
        return None