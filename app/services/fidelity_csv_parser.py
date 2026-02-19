"""
Fidelity CSV Parser Service

Parses Fidelity portfolio export CSV files.

CSV Format:
- Header: Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,
          Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,
          Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
- Multiple accounts in same file (different Account Number per row)
- Cash holdings: Description contains "Held in money market" or "held in fcash"
- Pending activity: Description = "Pending activity" (skip these)
- 401K funds: Symbol like "31617E745" (CUSIP format) - need to resolve via Fidelity fund lookup
- Last line: "Date downloaded Feb-18-2026 at 7:04 p.m ET"
"""
import csv
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, InvalidOperation
from io import StringIO

logger = logging.getLogger(__name__)

# Known Fidelity fund CUSIP to symbol mappings
# These are common Fidelity funds that appear in 401k accounts
FIDELITY_CUSIP_MAP = {
    # Fidelity Index Funds
    '31617E745': 'FXAIX',   # Fidelity 500 Index Fund
    '31617E703': 'FSKAX',   # Fidelity Total Market Index Fund
    '31617E679': 'FTIHX',   # Fidelity Total International Index Fund
    '31617E760': 'FXNAX',   # Fidelity US Bond Index Fund
    '316146109': 'FLCSX',   # Fidelity Large Cap Stock
    '316146208': 'FLCOX',   # Fidelity Large Cap Core Enhanced Index
    '316390772': 'FMIJX',   # Fidelity Mid Cap Index
    '316390699': 'FSSNX',   # Fidelity Small Cap Index
    '31635V638': 'FXIFX',   # Fidelity International Index
    '31635V679': 'FSPSX',   # Fidelity International Discovery
    # Fidelity Active Funds
    '315792879': 'FBALX',   # Fidelity Balanced Fund
    '315911206': 'FCNTX',   # Fidelity Contrafund
    '315792507': 'FBGRX',   # Fidelity Blue Chip Growth
    '315920719': 'FDGRX',   # Fidelity Growth Company
    # Vanguard Institutional (common in 401k)
    '67080C105': 'VINIX',   # Vanguard Institutional Index Fund Inst
    '922908728': 'VIIIX',   # Vanguard Institutional Index Fund Inst Plus
    # T. Rowe Price Target Date Funds
    '87281G408': 'TRRDX',   # T. Rowe Price Retirement 2035 Fund
    '87281J402': 'TRRKX',   # T. Rowe Price Retirement 2045 Fund
    '87281G507': 'TRRCX',   # T. Rowe Price Retirement 2030 Fund
    '87281G705': 'TRRAX',   # T. Rowe Price Retirement 2025 Fund
    '87281J501': 'TRRLX',   # T. Rowe Price Retirement 2050 Fund
    '87281J600': 'TRRMX',   # T. Rowe Price Retirement 2055 Fund
    '87281G101': 'TRRGX',   # T. Rowe Price Retirement 2040 Fund
    # Add more mappings as needed
}


class FidelityCSVParser:
    """Parser for Fidelity portfolio CSV exports"""
    
    def __init__(self):
        self.holdings = []
        self.cash_holdings = []
        self.accounts = {}  # account_number -> account_name
        self.export_date = None
        self.total_value = Decimal('0')
        self.total_cash = Decimal('0')
    
    def validate_csv(self, file_path: str) -> Tuple[bool, str]:
        """
        Validate that this is a valid Fidelity CSV file
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
                content = f.read()
            
            # Check for Fidelity CSV headers
            required_headers = ['Account Number', 'Account Name', 'Symbol', 'Description', 'Current Value']
            first_line = content.split('\n')[0]
            
            # Check if required headers are present
            headers_found = sum(1 for h in required_headers if h in first_line)
            if headers_found < 3:
                return False, f"Missing Fidelity CSV headers. Expected: {required_headers}"
            
            return True, ""
            
        except Exception as e:
            return False, f"Error validating CSV: {str(e)}"
    
    def parse_csv(self, file_path: str) -> Dict:
        """
        Parse a Fidelity CSV file from a file path
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            Dict with parsed holdings, cash, accounts, and metadata
        """
        with open(file_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
            content = f.read()
        return self.parse(content)
    
    def parse(self, csv_content: str) -> Dict:
        """
        Parse Fidelity CSV content
        
        Args:
            csv_content: Raw CSV file content as string
            
        Returns:
            Dict with parsed holdings, cash, accounts, and metadata
        """
        self.holdings = []
        self.cash_holdings = []
        self.accounts = {}
        self.export_date = None
        self.total_value = Decimal('0')
        self.total_cash = Decimal('0')
        
        lines = csv_content.strip().split('\n')
        
        # Extract export date from last line
        self._parse_export_date(lines)
        
        # Parse CSV content
        # Filter out the date line at the end
        csv_lines = [l for l in lines if not l.strip().startswith('"Date downloaded')]
        csv_text = '\n'.join(csv_lines)
        
        reader = csv.DictReader(StringIO(csv_text))
        
        for row in reader:
            self._parse_row(row)
        
        return {
            'holdings': self.holdings + self._get_cash_as_holdings(),  # Include cash in holdings
            'cash_holdings': self.cash_holdings,
            'accounts': self.accounts,
            'total_value': float(self.total_value),
            'total_cash': float(self.total_cash),
            'total_investments': float(self.total_value - self.total_cash),
            'export_date': self.export_date,
            'export_timestamp': self.export_date.isoformat() if self.export_date else None,
            'broker': 'fidelity'
        }
    
    def _get_cash_as_holdings(self) -> List[Dict]:
        """Convert cash holdings to holding format for storage"""
        cash_as_holdings = []
        for cash in self.cash_holdings:
            cash_as_holdings.append({
                'symbol': cash.get('symbol', 'CASH').rstrip('*'),
                'name': cash.get('description', 'Cash'),
                'quantity': 1,
                'price': cash['value'],
                'total_value': cash['value'],
                'value': cash['value'],
                'asset_type': 'cash',
                'account_number': cash.get('account_number'),
                'account_name': cash.get('account_name'),
                'broker': 'fidelity'
            })
        return cash_as_holdings
    
    def _parse_export_date(self, lines: List[str]):
        """Extract export date from last line like 'Date downloaded Feb-18-2026 at 7:04 p.m ET'"""
        for line in reversed(lines):
            line = line.strip().strip('"')
            if line.startswith('Date downloaded'):
                try:
                    # Extract: "Date downloaded Feb-18-2026 at 7:04 p.m ET"
                    match = re.search(r'Date downloaded\s+(\w+)-(\d+)-(\d+)\s+at\s+(\d+):(\d+)\s*(a\.m\.|p\.m\.?|AM|PM)', line, re.IGNORECASE)
                    if match:
                        month_str, day, year, hour, minute, ampm = match.groups()
                        
                        # Parse month
                        month_map = {
                            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                        }
                        month = month_map.get(month_str.lower()[:3], 1)
                        
                        # Parse time
                        hour = int(hour)
                        minute = int(minute)
                        if 'p' in ampm.lower() and hour != 12:
                            hour += 12
                        elif 'a' in ampm.lower() and hour == 12:
                            hour = 0
                        
                        self.export_date = datetime(int(year), month, int(day), hour, minute)
                        logger.info(f"Parsed Fidelity export date: {self.export_date}")
                        return
                except Exception as e:
                    logger.warning(f"Failed to parse Fidelity date: {line}, error: {e}")
        
        # Default to now if parsing fails
        self.export_date = datetime.now()
    
    def _parse_row(self, row: Dict):
        """Parse a single CSV row"""
        try:
            # Safely get values, handling None and BOM characters
            def safe_get(key):
                # Try with and without BOM prefix
                val = row.get(key) or row.get(f'\ufeff{key}')
                if val is None:
                    return ''
                return str(val).strip()
            
            account_number = safe_get('Account Number')
            account_name = safe_get('Account Name')
            symbol = safe_get('Symbol')
            description = safe_get('Description')
            quantity_str = safe_get('Quantity')
            price_str = safe_get('Last Price')
            value_str = safe_get('Current Value')
            cost_basis_str = safe_get('Cost Basis Total')
            holding_type = safe_get('Type')
            
            # Skip empty rows
            if not account_number and not description and not symbol:
                return
            
            # Skip disclaimer/footer rows (they have long text in account_number field)
            if len(account_number) > 20 or 'Fidelity' in account_number or 'provided' in account_number.lower():
                logger.debug(f"Skipping disclaimer row")
                return
            
            # Skip pending activity (check both symbol and description)
            if (description and 'pending activity' in description.lower()) or \
               (symbol and 'pending' in symbol.lower()):
                logger.debug(f"Skipping pending activity: {symbol} / {description}")
                return
            
            # Track accounts
            if account_number and account_name:
                self.accounts[account_number] = account_name
            
            # Parse value first
            value = self._parse_currency(value_str)
            
            # Skip rows with no value and no symbol
            if value == 0 and not symbol:
                return
            
            # Check if this is a cash holding (check Type field too)
            if self._is_cash_holding(description, symbol, holding_type):
                if value != 0:
                    self.cash_holdings.append({
                        'account_number': account_number,
                        'account_name': account_name,
                        'description': description,
                        'symbol': symbol,
                        'value': float(value)
                    })
                    self.total_cash += value
                    self.total_value += value
                    logger.info(f"Detected cash holding: {symbol} / {description} = ${value}")
                return
            
            # Skip if no symbol and not cash
            if not symbol:
                return
            
            # Parse quantity and price
            quantity = self._parse_decimal(quantity_str)
            price = self._parse_currency(price_str)
            cost_basis = self._parse_currency(cost_basis_str)
            
            # Resolve CUSIP symbols (401k funds)
            original_symbol = symbol
            if self._is_cusip(symbol):
                resolved = self._resolve_cusip(symbol)
                if resolved:
                    symbol = resolved
                    logger.info(f"Resolved CUSIP {original_symbol} -> {symbol}")
                else:
                    logger.warning(f"Unknown CUSIP: {original_symbol} ({description})")
            
            # Determine asset type
            asset_type = self._determine_asset_type(symbol, description, holding_type)
            
            # Create holding record (matching format expected by upload route)
            holding = {
                'account_number': account_number,
                'account_name': account_name,
                'symbol': symbol.upper(),
                'original_symbol': original_symbol if original_symbol != symbol else None,
                'name': description,
                'quantity': float(quantity),
                'price': float(price),
                'total_value': float(value),  # upload route expects 'total_value'
                'value': float(value),  # keep for compatibility
                'cost_basis': float(cost_basis) if cost_basis else None,
                'asset_type': asset_type,
                'broker': 'fidelity'
            }
            
            self.holdings.append(holding)
            self.total_value += value
            
        except Exception as e:
            logger.error(f"Error parsing Fidelity row: {row}, error: {e}")
    
    def _is_cash_holding(self, description: str, symbol: str, holding_type: str = '') -> bool:
        """
        Check if this row represents a cash holding.
        
        Cash indicators in Fidelity:
        - Type field = 'Cash'
        - Symbol is a money market fund (SPAXX, FDRXX, etc.)
        - Description contains 'HELD IN MONEY MARKET' or 'HELD IN FCASH'
        """
        desc_lower = description.lower() if description else ''
        symbol_clean = symbol.upper().rstrip('*') if symbol else ''  # Remove trailing asterisks
        type_lower = holding_type.lower().strip() if holding_type else ''
        
        # Type field = 'Cash' is definitive
        if type_lower == 'cash':
            return True
        
        # Check for money market fund symbols (these ARE cash equivalents)
        money_market_symbols = {
            'SPAXX',   # Fidelity Government Money Market
            'FDRXX',   # Fidelity Money Market
            'FZFXX',   # Fidelity Treasury Money Market
            'SPRXX',   # Fidelity Money Market Premium
            'FDLXX',   # Fidelity Treasury Only Money Market
            'FTEXX',   # Fidelity Treasury Money Market
            'FRGXX',   # Fidelity Government Cash Reserves
            'FCASH',   # Fidelity Cash
            'CORE',    # Core position
            'FLGXX',   # Fidelity Government Money Market
        }
        
        if symbol_clean in money_market_symbols:
            return True
        
        # Check description for explicit cash indicators
        # Be strict - only match exact cash-related phrases
        cash_desc_phrases = [
            'held in money market',
            'held in fcash',
            'core position',
        ]
        
        for phrase in cash_desc_phrases:
            if phrase in desc_lower:
                return True
        
        return False
    
    def _is_cusip(self, symbol: str) -> bool:
        """Check if symbol looks like a CUSIP (9 alphanumeric characters)"""
        if not symbol:
            return False
        # CUSIP: 9 characters, alphanumeric, often ends with digit
        # Stock symbols: typically 1-5 letters
        if len(symbol) == 9 and symbol[0].isdigit():
            return True
        if len(symbol) > 5 and any(c.isdigit() for c in symbol):
            return True
        return False
    
    def _resolve_cusip(self, cusip: str) -> Optional[str]:
        """
        Resolve a CUSIP to a ticker symbol
        
        For Fidelity 401k funds, we maintain a mapping of known CUSIPs.
        Unknown CUSIPs are returned as-is for manual resolution.
        """
        # Check our known mapping
        if cusip in FIDELITY_CUSIP_MAP:
            return FIDELITY_CUSIP_MAP[cusip]
        
        # TODO: Could add API lookup here (e.g., OpenFIGI, SEC EDGAR)
        return None
    
    def _determine_asset_type(self, symbol: str, description: str, holding_type: str) -> str:
        """Determine the asset type based on available information"""
        desc_lower = description.lower()
        type_lower = holding_type.lower() if holding_type else ''
        
        # Check holding type field
        if 'etf' in type_lower:
            return 'etf'
        if 'mutual fund' in type_lower or 'mf' in type_lower:
            return 'mutual_fund'
        if 'stock' in type_lower or 'equity' in type_lower:
            return 'stock'
        if 'bond' in type_lower:
            return 'bond'
        
        # Check description
        if 'etf' in desc_lower:
            return 'etf'
        if 'fund' in desc_lower or 'index' in desc_lower:
            return 'mutual_fund'
        
        # Check symbol patterns
        # Fidelity funds often start with F
        if symbol.startswith('F') and len(symbol) == 5:
            return 'mutual_fund'
        
        # Default based on symbol length
        if len(symbol) <= 4:
            return 'stock'
        
        return 'unknown'
    
    def _parse_currency(self, value_str: str) -> Decimal:
        """Parse a currency string like '$1,234.56' or '-$125.67'"""
        if not value_str:
            return Decimal('0')
        
        try:
            # Remove currency symbols and commas
            cleaned = value_str.replace('$', '').replace(',', '').strip()
            
            # Handle negative values
            if cleaned.startswith('(') and cleaned.endswith(')'):
                cleaned = '-' + cleaned[1:-1]
            
            return Decimal(cleaned) if cleaned else Decimal('0')
        except InvalidOperation:
            return Decimal('0')
    
    def _parse_decimal(self, value_str: str) -> Decimal:
        """Parse a decimal number string"""
        if not value_str:
            return Decimal('0')
        
        try:
            cleaned = value_str.replace(',', '').strip()
            return Decimal(cleaned) if cleaned else Decimal('0')
        except InvalidOperation:
            return Decimal('0')


def parse_fidelity_csv(csv_content: str) -> Dict:
    """
    Convenience function to parse Fidelity CSV content
    
    Args:
        csv_content: Raw CSV file content
        
    Returns:
        Dict with parsed data
    """
    parser = FidelityCSVParser()
    return parser.parse(csv_content)