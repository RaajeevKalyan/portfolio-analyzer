"""
Fidelity CSV Parser Service

Parses Fidelity portfolio export CSV files.

CSV Format:
- Header: Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,
          Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,
          Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type

IMPORTANT: The "Type" column in Fidelity CSVs is UNRELIABLE!
It shows "Cash" for regular stocks like ADBE, AMZN, etc.
We IGNORE the Type field and use Description + cache + API for classification.

Cash Detection (Description-based):
- "Held in money market" -> cash
- "Held in fcash" -> cash
- Known money market symbols (SPAXX, FDRXX, etc.) -> cash

Asset Type Resolution Priority:
1. Check stock_info_cache for known symbols
2. Check Description for cash phrases
3. Check known money market symbols
4. Use yfinance API
5. Fall back to heuristics
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
FIDELITY_CUSIP_MAP = {
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
    '315792879': 'FBALX',   # Fidelity Balanced Fund
    '315911206': 'FCNTX',   # Fidelity Contrafund
    '315792507': 'FBGRX',   # Fidelity Blue Chip Growth
    '315920719': 'FDGRX',   # Fidelity Growth Company
    '67080C105': 'VINIX',   # Vanguard Institutional Index Fund Inst
    '922908728': 'VIIIX',   # Vanguard Institutional Index Fund Inst Plus
    '87281G408': 'TRRDX',   # T. Rowe Price Retirement 2035 Fund
    '87281J402': 'TRRKX',   # T. Rowe Price Retirement 2045 Fund
    '87281G507': 'TRRCX',   # T. Rowe Price Retirement 2030 Fund
    '87281G705': 'TRRAX',   # T. Rowe Price Retirement 2025 Fund
    '87281J501': 'TRRLX',   # T. Rowe Price Retirement 2050 Fund
    '87281J600': 'TRRMX',   # T. Rowe Price Retirement 2055 Fund
    '87281G101': 'TRRGX',   # T. Rowe Price Retirement 2040 Fund
}

# Money market fund symbols - these ARE cash equivalents
MONEY_MARKET_SYMBOLS = {
    'SPAXX', 'FDRXX', 'FZFXX', 'SPRXX', 'FDLXX', 'FTEXX',
    'FRGXX', 'FCASH', 'CORE', 'FLGXX',
}

# Cash description phrases (ONLY way to reliably detect cash in Fidelity CSVs)
CASH_DESCRIPTION_PHRASES = [
    'held in money market',
    'held in fcash',
    'core position',
    'government money market',
]


class FidelityCSVParser:
    """Parser for Fidelity portfolio CSV exports"""
    
    def __init__(self):
        self.holdings = []
        self.cash_holdings = []
        self.accounts = {}
        self.export_date = None
        self.total_value = Decimal('0')
        self.total_cash = Decimal('0')
        self._stock_info_cache = None
    
    @property
    def stock_info_cache(self):
        """Lazy load stock info cache"""
        if self._stock_info_cache is None:
            try:
                from app.services.stock_info_service import StockInfoService
                service = StockInfoService()
                self._stock_info_cache = service.cache
                logger.info(f"Loaded stock info cache with {len(self._stock_info_cache)} symbols")
            except Exception as e:
                logger.warning(f"Could not load stock info cache: {e}")
                self._stock_info_cache = {}
        return self._stock_info_cache
    
    def validate_csv(self, file_path: str) -> Tuple[bool, str]:
        """Validate that this is a valid Fidelity CSV file"""
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            required_headers = ['Account Number', 'Account Name', 'Symbol', 'Description', 'Current Value']
            first_line = content.split('\n')[0]
            
            headers_found = sum(1 for h in required_headers if h in first_line)
            if headers_found < 3:
                return False, f"Missing Fidelity CSV headers"
            
            return True, ""
        except Exception as e:
            return False, f"Error validating CSV: {str(e)}"
    
    def parse_csv(self, file_path: str) -> Dict:
        """Parse a Fidelity CSV file from a file path"""
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        return self.parse(content)
    
    def parse(self, csv_content: str) -> Dict:
        """Parse Fidelity CSV content"""
        self.holdings = []
        self.cash_holdings = []
        self.accounts = {}
        self.export_date = None
        self.total_value = Decimal('0')
        self.total_cash = Decimal('0')
        
        lines = csv_content.strip().split('\n')
        
        logger.info("=" * 60)
        logger.info("FIDELITY CSV PARSER - Starting parse")
        logger.info("=" * 60)
        
        # Log first few lines for debugging
        for i, line in enumerate(lines[:3]):
            logger.info(f"  Line {i}: {line[:150]}...")
        
        # Extract export date
        self._parse_export_date(lines)
        
        # Filter out the date line at the end
        csv_lines = [l for l in lines if not l.strip().startswith('"Date downloaded')]
        csv_text = '\n'.join(csv_lines)
        
        reader = csv.DictReader(StringIO(csv_text))
        logger.info(f"CSV Headers: {reader.fieldnames}")
        
        row_count = 0
        for row in reader:
            row_count += 1
            self._parse_row(row)
        
        logger.info(f"Processed {row_count} rows")
        logger.info(f"Result: {len(self.holdings)} investments, {len(self.cash_holdings)} cash")
        logger.info(f"Total: ${self.total_value}, Cash: ${self.total_cash}")
        
        # Log holdings summary
        for h in self.holdings[:10]:
            logger.info(f"  -> {h['symbol']:8} {h['asset_type']:12} ${h['total_value']:>12,.2f}")
        if len(self.holdings) > 10:
            logger.info(f"  ... and {len(self.holdings) - 10} more")
        
        logger.info("=" * 60)
        
        return {
            'holdings': self.holdings + self._get_cash_as_holdings(),
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
        """Convert cash holdings to holding format"""
        return [{
            'symbol': c.get('symbol', 'CASH').rstrip('*'),
            'name': c.get('description', 'Cash'),
            'quantity': 1,
            'price': c['value'],
            'total_value': c['value'],
            'value': c['value'],
            'asset_type': 'cash',
            'account_number': c.get('account_number'),
            'account_name': c.get('account_name'),
            'broker': 'fidelity'
        } for c in self.cash_holdings]
    
    def _parse_export_date(self, lines: List[str]):
        """Extract export date from last line"""
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        for line in reversed(lines):
            line = line.strip().strip('"')
            if line.startswith('Date downloaded'):
                try:
                    match = re.search(r'(\w+)-(\d+)-(\d+)\s+at\s+(\d+):(\d+)\s*(a\.m|p\.m|am|pm)?', line, re.I)
                    if match:
                        month_str, day, year, hour, minute, ampm = match.groups()
                        month = month_map.get(month_str.lower()[:3], 1)
                        hour = int(hour)
                        minute = int(minute)
                        
                        if ampm and 'p' in ampm.lower() and hour != 12:
                            hour += 12
                        elif ampm and 'a' in ampm.lower() and hour == 12:
                            hour = 0
                        
                        self.export_date = datetime(int(year), month, int(day), hour, minute)
                        return
                except Exception as e:
                    logger.warning(f"Failed to parse date: {e}")
        
        self.export_date = datetime.now()
    
    def _parse_row(self, row: Dict):
        """Parse a single CSV row"""
        try:
            def safe_get(key):
                val = row.get(key) or row.get(f'\ufeff{key}')
                return str(val).strip() if val else ''
            
            account_number = safe_get('Account Number')
            account_name = safe_get('Account Name')
            symbol = safe_get('Symbol')
            description = safe_get('Description')
            quantity_str = safe_get('Quantity')
            price_str = safe_get('Last Price')
            value_str = safe_get('Current Value')
            cost_basis_str = safe_get('Cost Basis Total')
            # NOTE: We IGNORE the Type field - it's unreliable in Fidelity CSVs!
            
            # Skip empty rows
            if not account_number and not description and not symbol:
                return
            
            # Skip disclaimer/footer rows
            if len(account_number) > 20 or 'Fidelity' in account_number:
                return
            
            # Skip pending activity
            if 'pending' in (symbol or '').lower() or 'pending' in (description or '').lower():
                return
            
            # Track accounts
            if account_number and account_name:
                self.accounts[account_number] = account_name
            
            value = self._parse_currency(value_str)
            
            if value == 0 and not symbol:
                return
            
            # STEP 1: Check cache first - known symbols are NOT cash
            symbol_upper = symbol.upper().rstrip('*') if symbol else ''
            cached_info = self.stock_info_cache.get(symbol_upper, {})
            
            if cached_info and cached_info.get('asset_type'):
                # Symbol is in cache - it's a known security, NOT cash
                # Process as investment
                asset_type = cached_info['asset_type']
                logger.debug(f"{symbol_upper} -> {asset_type} (cache)")
                
                self._add_investment(
                    account_number, account_name, symbol, description,
                    quantity_str, price_str, value, cost_basis_str, asset_type
                )
                return
            
            # STEP 2: Check Description for cash phrases
            if self._is_cash_by_description(description):
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
                    logger.info(f"Cash (description): {symbol} '{description[:30]}' ${value}")
                return
            
            # STEP 3: Check known money market symbols
            if symbol_upper in MONEY_MARKET_SYMBOLS:
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
                    logger.info(f"Cash (money market): {symbol} ${value}")
                return
            
            # Skip if no symbol at this point
            if not symbol:
                return
            
            # STEP 4: Use yfinance API to resolve
            asset_type = self._resolve_asset_type_via_api(symbol_upper, description)
            
            self._add_investment(
                account_number, account_name, symbol, description,
                quantity_str, price_str, value, cost_basis_str, asset_type
            )
            
        except Exception as e:
            logger.error(f"Error parsing row: {e}")
    
    def _add_investment(self, account_number, account_name, symbol, description,
                        quantity_str, price_str, value, cost_basis_str, asset_type):
        """Add an investment holding"""
        quantity = self._parse_decimal(quantity_str)
        price = self._parse_currency(price_str)
        cost_basis = self._parse_currency(cost_basis_str)
        
        # Resolve CUSIP symbols
        original_symbol = symbol
        if self._is_cusip(symbol):
            resolved = self._resolve_cusip(symbol)
            if resolved:
                symbol = resolved
                logger.info(f"CUSIP {original_symbol} -> {symbol}")
        
        holding = {
            'account_number': account_number,
            'account_name': account_name,
            'symbol': symbol.upper(),
            'original_symbol': original_symbol if original_symbol != symbol else None,
            'name': description,
            'quantity': float(quantity),
            'price': float(price),
            'total_value': float(value),
            'value': float(value),
            'cost_basis': float(cost_basis) if cost_basis else None,
            'asset_type': asset_type,
            'broker': 'fidelity'
        }
        
        self.holdings.append(holding)
        self.total_value += value
        logger.debug(f"Investment: {symbol} -> {asset_type} ${value}")
    
    def _is_cash_by_description(self, description: str) -> bool:
        """
        Check if Description indicates a cash holding.
        This is the ONLY reliable way to detect cash in Fidelity CSVs.
        """
        if not description:
            return False
        
        desc_lower = description.lower()
        
        for phrase in CASH_DESCRIPTION_PHRASES:
            if phrase in desc_lower:
                return True
        
        return False
    
    def _resolve_asset_type_via_api(self, symbol: str, description: str) -> str:
        """
        Resolve asset type using yfinance API, then fall back to heuristics.
        """
        symbol_upper = symbol.upper()
        desc_lower = description.lower() if description else ''
        
        # Try yfinance API
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol_upper)
            info = ticker.info
            if info and info.get('quoteType'):
                qt = info['quoteType']
                if qt == 'ETF':
                    logger.info(f"{symbol_upper} -> etf (yfinance)")
                    return 'etf'
                elif qt == 'MUTUALFUND':
                    logger.info(f"{symbol_upper} -> mutual_fund (yfinance)")
                    return 'mutual_fund'
                elif qt == 'EQUITY':
                    logger.debug(f"{symbol_upper} -> stock (yfinance)")
                    return 'stock'
                elif qt == 'BOND':
                    return 'bond'
        except Exception as e:
            logger.debug(f"yfinance failed for {symbol_upper}: {e}")
        
        # Heuristics fallback
        known_etfs = {'VOO', 'VTI', 'SPY', 'QQQ', 'IVV', 'VEA', 'VWO', 'BND', 'AGG', 'VNQ'}
        if symbol_upper in known_etfs:
            return 'etf'
        
        if 'etf' in desc_lower:
            return 'etf'
        if 'fund' in desc_lower and 'exchange' not in desc_lower:
            return 'mutual_fund'
        
        if len(symbol_upper) == 5 and symbol_upper.endswith('X'):
            return 'mutual_fund'
        
        if len(symbol_upper) == 9 and symbol_upper[0].isdigit():
            return 'mutual_fund'
        
        return 'stock'
    
    def _is_cusip(self, symbol: str) -> bool:
        """Check if symbol looks like a CUSIP"""
        if not symbol:
            return False
        if len(symbol) == 9 and symbol[0].isdigit():
            return True
        if len(symbol) > 5 and any(c.isdigit() for c in symbol):
            return True
        return False
    
    def _resolve_cusip(self, cusip: str) -> Optional[str]:
        """Resolve a CUSIP to a ticker symbol"""
        return FIDELITY_CUSIP_MAP.get(cusip)
    
    def _parse_currency(self, value_str: str) -> Decimal:
        """Parse currency string"""
        if not value_str:
            return Decimal('0')
        try:
            cleaned = value_str.replace('$', '').replace(',', '').strip()
            if cleaned.startswith('(') and cleaned.endswith(')'):
                cleaned = '-' + cleaned[1:-1]
            if cleaned.startswith('+'):
                cleaned = cleaned[1:]
            return Decimal(cleaned) if cleaned else Decimal('0')
        except InvalidOperation:
            return Decimal('0')
    
    def _parse_decimal(self, value_str: str) -> Decimal:
        """Parse decimal string"""
        if not value_str:
            return Decimal('0')
        try:
            cleaned = value_str.replace(',', '').strip()
            return Decimal(cleaned) if cleaned else Decimal('0')
        except InvalidOperation:
            return Decimal('0')


def parse_fidelity_csv(csv_content: str) -> Dict:
    """Convenience function to parse Fidelity CSV content"""
    parser = FidelityCSVParser()
    return parser.parse(csv_content)