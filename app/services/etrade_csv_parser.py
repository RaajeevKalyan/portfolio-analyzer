"""
E-Trade CSV Parser Service

Parses E-Trade portfolio export CSV files.

CSV Format (PortfolioDownload.csv):
- Account Summary section at top
- "View Summary - All Positions" header
- Data header: Symbol,Last Price $,Change $,Change %,Quantity,Price Paid $,Day's Gain $,Total Gain $,Total Gain %,Value $
- Holdings data rows
- CASH row (special format - value in last column only)
- TOTAL row
- "Generated at" timestamp footer

Key Features:
- Options are listed with full description (e.g., "ARBE May 15 '26 $1.50 Call")
- Short positions have NEGATIVE quantities
- Cash row has empty fields except Symbol and Value
- Account number embedded in format "Brokerage -XXXX"

IMPORTANT LESSONS (from Fidelity/Merrill parser bugs):
1. Don't trust any "Type" field if present - use asset_type_resolver
2. Handle options properly (Call/Put in symbol name)
3. Handle negative quantities (short positions)
4. Skip TOTAL rows explicitly
5. Handle BOM encoding
6. Properly extract cash from special CASH row format
"""
from app.services.csv_parser_base import CSVParserBase
import pandas as pd
from typing import Dict, Optional, List
from decimal import Decimal
import logging
import re
import tempfile
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class ETradeCSVParser(CSVParserBase):
    """Parser for E-Trade CSV files"""
    
    def __init__(self):
        super().__init__()
        self.broker_name = 'etrade'
    
    def validate_csv(self, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate E-Trade CSV format
        
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            df = self._preprocess_etrade_csv(file_path)
            
            if df is None or len(df) == 0:
                return False, "CSV file is empty or has no valid position data section"
            
            # Check for required columns
            symbol_col = self.find_column(df, ['Symbol'])
            quantity_col = self.find_column(df, ['Quantity'])
            value_col = self.find_column(df, ['Value $', 'Value'])
            
            if not symbol_col:
                return False, "Could not find Symbol column"
            
            if not quantity_col:
                return False, "Could not find Quantity column"
            
            if not value_col:
                return False, "Could not find Value column"
            
            logger.info(f"E-Trade CSV validation passed: {len(df)} rows")
            return True, None
            
        except Exception as e:
            logger.error(f"E-Trade CSV validation failed: {e}")
            return False, str(e)
    
    def _preprocess_etrade_csv(self, file_path: str) -> Optional[pd.DataFrame]:
        """
        Preprocess E-Trade CSV to extract the actual positions section
        
        E-Trade CSVs have:
        1. Account Summary section
        2. "View Summary - All Positions" section
        3. Filter info
        4. Header: Symbol,Last Price $,Change $,Change %,Quantity,Price Paid $,Day's Gain $,Total Gain $,Total Gain %,Value $
        5. Data rows
        6. CASH row (special - only has Symbol and Value filled)
        7. TOTAL row
        8. Generated at timestamp
        """
        try:
            # Handle BOM encoding
            encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
            lines = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        lines = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            
            if lines is None:
                logger.error("Could not read E-Trade CSV with any encoding")
                return None
            
            # Find the header line
            header_idx = None
            data_start_idx = None
            
            for i, line in enumerate(lines):
                # Look for the data header line
                if line.startswith('Symbol,Last Price') or line.startswith('"Symbol","Last Price'):
                    header_idx = i
                    data_start_idx = i + 1
                    logger.info(f"Found E-Trade data header at line {i}")
                    break
            
            if header_idx is None:
                logger.error("Could not find positions data section in E-Trade CSV")
                return None
            
            # Find where data ends (TOTAL row or Generated at)
            data_end_idx = len(lines)
            for i in range(data_start_idx, len(lines)):
                line_stripped = lines[i].strip().strip('"').strip()
                # Skip TOTAL row but include it for exclusion
                if line_stripped.startswith('TOTAL'):
                    data_end_idx = i
                    logger.info(f"Found TOTAL row at line {i}, excluding")
                    break
                elif line_stripped.startswith('Generated at') or line_stripped == '':
                    # Check if it's just empty lines at end
                    if line_stripped.startswith('Generated at'):
                        data_end_idx = i
                        break
            
            header_line = lines[header_idx]
            data_lines = lines[data_start_idx:data_end_idx]
            
            # Filter out empty lines but keep CASH row
            filtered_lines = []
            for line in data_lines:
                line_stripped = line.strip()
                # Skip completely empty lines or just commas
                if not line_stripped or all(c in ',"\' ' for c in line_stripped):
                    continue
                filtered_lines.append(line)
            
            logger.info(f"E-Trade CSV: {len(filtered_lines)} data rows after filtering")
            
            csv_content = header_line + ''.join(filtered_lines)
            
            # Write to temp file and parse
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                tmp.write(csv_content)
                tmp_path = tmp.name
            
            df = pd.read_csv(tmp_path, skipinitialspace=True, on_bad_lines='warn')
            os.unlink(tmp_path)
            
            # Clean column names
            df.columns = df.columns.str.strip()
            df = df.dropna(how='all')
            
            self.df = df
            logger.info(f"E-Trade CSV preprocessed: {len(df)} rows, columns: {list(df.columns)}")
            return df
            
        except Exception as e:
            logger.error(f"Error preprocessing E-Trade CSV: {e}", exc_info=True)
            return None

    def extract_export_timestamp(self, file_path: str) -> Optional[str]:
        """Extract the export timestamp from E-Trade CSV footer"""
        try:
            encodings = ['utf-8-sig', 'utf-8', 'latin-1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                return None
                
            # Look for "Generated at Feb 20 2026 10:10 AM ET"
            match = re.search(
                r'Generated at\s+(\w{3}\s+\d{1,2}\s+\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)',
                content, 
                re.IGNORECASE
            )
            if match:
                date_str = match.group(1).strip()
                logger.info(f"Found E-Trade timestamp: {date_str}")
                try:
                    # Try with AM/PM
                    dt = datetime.strptime(date_str, '%b %d %Y %I:%M %p')
                    return dt.isoformat()
                except ValueError:
                    try:
                        # Try without AM/PM
                        dt = datetime.strptime(date_str, '%b %d %Y %H:%M')
                        return dt.isoformat()
                    except ValueError:
                        logger.warning(f"Could not parse E-Trade timestamp: {date_str}")
                        
        except Exception as e:
            logger.error(f"Error extracting E-Trade export timestamp: {e}")
        return None
    
    def extract_account_number(self, file_path: str) -> Optional[str]:
        """Extract account number from E-Trade Account Summary section"""
        try:
            encodings = ['utf-8-sig', 'utf-8', 'latin-1']
            lines = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        lines = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            
            if not lines:
                return None
            
            # Look for account info - format is "Brokerage -XXXX,..."
            for i, line in enumerate(lines):
                if line.startswith('Account,Net Account Value'):
                    # Next line contains account data
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line:
                            parts = next_line.split(',')
                            if parts:
                                # Account format: "Brokerage -3412"
                                acc_val = parts[0].strip().strip('"')
                                # Extract just alphanumeric characters
                                alnum = re.sub(r'[^A-Z0-9]', '', acc_val.upper())
                                if len(alnum) >= 4:
                                    account_last4 = alnum[-4:]
                                    logger.info(f"Extracted E-Trade account last4: {account_last4}")
                                    return account_last4
                                    
        except Exception as e:
            logger.error(f"Error extracting E-Trade account number: {e}")
        return None
    
    def parse_csv(self, file_path: str) -> Dict:
        """Parse E-Trade CSV file"""
        logger.info(f"Parsing E-Trade CSV: {file_path}")
        
        export_timestamp = self.extract_export_timestamp(file_path)
        account_number = self.extract_account_number(file_path)
        
        logger.info(f"E-Trade export timestamp: {export_timestamp}")
        logger.info(f"E-Trade account last4: {account_number}")
        
        df = self._preprocess_etrade_csv(file_path)
        if df is None:
            raise ValueError("Could not extract data from E-Trade CSV")
        
        columns = self._map_columns(df)
        if not columns:
            raise ValueError("Could not map required columns in E-Trade CSV")
        
        logger.info(f"E-Trade column mapping: {columns}")
        
        holdings = []
        cash_holdings = []
        total_value = Decimal('0.00')
        total_cash = Decimal('0.00')
        skipped_rows = []
        
        for idx, row in df.iterrows():
            try:
                holding = self._parse_row(row, columns, idx)
                
                if holding is None:
                    continue
                
                if holding.get('skip_reason'):
                    skipped_rows.append(f"Row {idx}: {holding['skip_reason']}")
                    continue
                
                if holding['total_value'] == 0:
                    skipped_rows.append(f"Row {idx}: Zero value")
                    continue
                
                if holding['asset_type'] == 'cash':
                    cash_holdings.append(holding)
                    total_cash += holding['total_value']
                else:
                    holdings.append(holding)
                
                total_value += holding['total_value']
                
            except Exception as e:
                logger.warning(f"Error parsing E-Trade row {idx}: {e}")
                skipped_rows.append(f"Row {idx}: {str(e)}")
                continue
        
        if skipped_rows:
            logger.info(f"E-Trade skipped rows: {skipped_rows[:5]}...")
        
        all_holdings = holdings + cash_holdings
        
        logger.info(f"E-Trade parsed: {len(holdings)} investments, {len(cash_holdings)} cash positions")
        logger.info(f"E-Trade totals: ${total_value} total, ${total_cash} cash")
        
        return {
            'account_number_last4': account_number,
            'total_value': total_value,
            'holdings': all_holdings,
            'cash_holdings': cash_holdings,
            'total_cash': total_cash,
            'investment_holdings': holdings,
            'total_investments': total_value - total_cash,
            'export_timestamp': export_timestamp
        }
    
    def _map_columns(self, df: pd.DataFrame) -> Optional[Dict[str, str]]:
        """Map DataFrame columns to expected fields"""
        mapping = {}
        
        mapping['symbol'] = self.find_column(df, ['Symbol'])
        mapping['quantity'] = self.find_column(df, ['Quantity'])
        mapping['price'] = self.find_column(df, ['Last Price $', 'Last Price'])
        mapping['value'] = self.find_column(df, ['Value $', 'Value'])
        
        # Optional columns
        mapping['price_paid'] = self.find_column(df, ['Price Paid $', 'Price Paid', 'Cost Basis'])
        
        required = ['symbol', 'value']
        if not all(mapping.get(field) for field in required):
            logger.error(f"Missing required columns. Found: {mapping}")
            return None
            
        return mapping
    
    def _parse_row(self, row: pd.Series, columns: Dict[str, str], row_idx: int) -> Optional[Dict]:
        """Parse a single row from E-Trade CSV"""
        
        # Get symbol
        symbol_raw = str(row[columns['symbol']]).strip()
        
        # Skip empty symbols
        if not symbol_raw or symbol_raw.lower() == 'nan':
            return {'skip_reason': 'Empty symbol'}
        
        # Skip TOTAL row
        if symbol_raw.upper() == 'TOTAL':
            return {'skip_reason': 'TOTAL row'}
        
        # Check if this is the CASH row
        is_cash = symbol_raw.upper() == 'CASH'
        
        # Check if this is an OPTIONS position
        is_option = self._is_option(symbol_raw)
        
        # Get value first (needed for all types)
        value_str = str(row[columns['value']])
        total_value = self._safe_decimal(value_str)
        
        if is_cash:
            # Cash row - special handling
            return {
                'symbol': 'CASH',
                'name': 'Cash',
                'quantity': Decimal('1.00'),
                'price': total_value,
                'total_value': total_value,
                'asset_type': 'cash',
                'account_type': None
            }
        
        if is_option:
            # Options position - use a UNIQUE symbol to prevent aggregation with underlying
            # Format: UNDERLYING_OPTIONTYPE (e.g., ARBE_CALL, TSLA_CALL)
            underlying = self._extract_option_underlying(symbol_raw)
            option_type = 'CALL' if 'call' in symbol_raw.lower() else 'PUT'
            
            # Create unique symbol for this specific option contract
            # Include expiry info to differentiate multiple options on same underlying
            symbol = self._create_option_symbol(symbol_raw, underlying)
            description = symbol_raw  # Keep full option description
            asset_type = 'option'
            
            logger.info(f"E-Trade option: '{symbol_raw}' -> symbol='{symbol}', underlying='{underlying}'")
        else:
            # Regular stock/ETF/MF
            symbol = self.normalize_symbol(symbol_raw)
            description = symbol_raw
            asset_type = self._detect_asset_type_safe(symbol, description)
        
        if not symbol:
            return {'skip_reason': f'Could not normalize symbol: {symbol_raw}'}
        
        # Get quantity - can be negative for short positions
        qty_str = str(row[columns['quantity']]) if columns.get('quantity') else '0'
        quantity = self._safe_decimal(qty_str)
        
        # Get price
        if columns.get('price') and pd.notna(row.get(columns['price'])):
            price_str = str(row[columns['price']])
            price = self._safe_decimal(price_str)
        else:
            # Calculate from value/quantity
            price = abs(total_value / quantity) if quantity != 0 else Decimal('0.00')
        
        # Handle short positions (negative quantity but positive value representation)
        # Note: E-Trade shows sold options with negative quantity
        if quantity < 0:
            logger.debug(f"E-Trade short position detected: {symbol_raw}, qty={quantity}")
        
        return {
            'symbol': symbol,
            'name': description,
            'quantity': quantity,
            'price': price,
            'total_value': total_value,
            'asset_type': asset_type,
            'account_type': None
        }
    
    def _is_option(self, symbol_raw: str) -> bool:
        """Detect if a symbol is an options contract"""
        # E-Trade options format: "ARBE May 15 '26 $1.50 Call" or "TSLA Jan 21 '28 $450 Call"
        option_patterns = [
            r'\b(Call|Put)\b',  # Contains Call or Put
            r"'\d{2}\s+\$",     # Contains '26 $ pattern (year and strike)
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d',  # Month + day pattern
        ]
        
        for pattern in option_patterns:
            if re.search(pattern, symbol_raw, re.IGNORECASE):
                return True
        return False
    
    def _extract_option_underlying(self, option_symbol: str) -> str:
        """Extract the underlying ticker from an options symbol"""
        # "ARBE May 15 '26 $1.50 Call" -> "ARBE"
        # "TSLA Jan 21 '28 $450 Call" -> "TSLA"
        parts = option_symbol.split()
        if parts:
            # First part is usually the underlying ticker
            underlying = parts[0].upper()
            # Validate it looks like a ticker (alphanumeric, reasonable length)
            if re.match(r'^[A-Z]{1,5}$', underlying):
                return underlying
        
        # Fallback: normalize the whole thing
        return self.normalize_symbol(option_symbol)
    
    def _create_option_symbol(self, option_description: str, underlying: str) -> str:
        """
        Create a unique symbol for an options contract.
        
        This ensures options don't get aggregated with the underlying stock.
        
        Examples:
            "ARBE May 15 '26 $1.50 Call" -> "ARBE_C260515_1.50"
            "TSLA Jan 21 '28 $450 Call" -> "TSLA_C280121_450"
            "CRWV Jan 15 '27 $140 Call" -> "CRWV_C270115_140"
        """
        try:
            # Determine option type
            is_call = 'call' in option_description.lower()
            option_type = 'C' if is_call else 'P'
            
            # Extract expiry date - look for patterns like "May 15 '26" or "Jan 21 '28"
            expiry_match = re.search(
                r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+[\'"]?(\d{2})',
                option_description,
                re.IGNORECASE
            )
            
            if expiry_match:
                month_str = expiry_match.group(1)
                day = expiry_match.group(2).zfill(2)
                year = expiry_match.group(3)
                
                # Convert month to number
                months = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                          'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                          'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
                month = months.get(month_str.lower(), '01')
                
                expiry = f"{year}{month}{day}"
            else:
                expiry = "XXXXXX"
            
            # Extract strike price - look for $XXX or $X.XX
            strike_match = re.search(r'\$(\d+(?:\.\d+)?)', option_description)
            strike = strike_match.group(1) if strike_match else "0"
            
            # Create unique symbol
            unique_symbol = f"{underlying}_{option_type}{expiry}_{strike}"
            
            return unique_symbol
            
        except Exception as e:
            logger.warning(f"Could not create option symbol from '{option_description}': {e}")
            # Fallback: use underlying + hash of description
            return f"{underlying}_OPT_{hash(option_description) % 10000}"
    
    def _safe_decimal(self, value_str: str) -> Decimal:
        """Safely convert string to Decimal, handling various formats"""
        if not value_str or value_str.lower() == 'nan' or value_str.strip() == '':
            return Decimal('0.00')
        
        try:
            # Remove currency symbols, commas, spaces
            cleaned = re.sub(r'[$,\s]', '', str(value_str))
            
            # Handle parentheses for negative numbers: (100) -> -100
            if cleaned.startswith('(') and cleaned.endswith(')'):
                cleaned = '-' + cleaned[1:-1]
            
            if not cleaned or cleaned == '-':
                return Decimal('0.00')
            
            return Decimal(cleaned)
            
        except Exception:
            return Decimal('0.00')
    
    def _detect_asset_type_safe(self, symbol: str, description: str) -> str:
        """Safely detect asset type using the resolver"""
        try:
            from app.services.asset_type_resolver import resolve_asset_type
            return resolve_asset_type(
                symbol=symbol,
                description=description,
                csv_type_field='',  # E-Trade doesn't have a type field
                use_cache=True,
                use_yfinance=True
            )
        except ImportError:
            logger.warning("asset_type_resolver not available, defaulting to stock")
            return 'stock'
        except Exception as e:
            logger.warning(f"Error detecting asset type for {symbol}: {e}")
            return 'stock'

    def get_required_columns(self) -> List[str]:
        """Return list of required column names"""
        return ['Symbol', 'Quantity', 'Value $']