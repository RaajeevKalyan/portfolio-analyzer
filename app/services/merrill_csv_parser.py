"""
Merrill Lynch CSV Parser

Parses CSV files exported from Merrill Lynch.

Expected CSV format (common columns):
- Symbol / Security / Ticker
- Description / Security Description
- Quantity / Shares
- Price / Last Price / Market Price
- Value / Market Value / Total Value
- Account (optional)

Note: Merrill Lynch CSV formats can vary. This parser handles common variations.

CHANGELOG:
- Fixed: Cash holdings are now properly parsed instead of being filtered out
- Fixed: Cash rows without symbols are now handled correctly
"""
from app.services.csv_parser_base import CSVParserBase
import pandas as pd
from typing import Dict, Optional, List
from decimal import Decimal
import logging
import re
import tempfile
import os

logger = logging.getLogger(__name__)


class MerrillCSVParser(CSVParserBase):
    """Parser for Merrill Lynch CSV files"""
    
    def __init__(self):
        super().__init__()
        self.broker_name = 'merrill'
    
    def validate_csv(self, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate Merrill Lynch CSV format
        
        Merrill CSVs have a complex format with quoted sections.
        The actual data is in a section between double quotes.
        
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            # Preprocess CSV to extract data section
            df = self._preprocess_merrill_csv(file_path)
            
            if df is None or len(df) == 0:
                return False, "CSV file is empty or has no valid data section"
            
            # Check for required columns (flexible matching)
            symbol_col = self.find_column(df, ['Symbol', 'Ticker', 'Security'])
            quantity_col = self.find_column(df, ['Quantity', 'Shares', 'Qty'])
            value_col = self.find_column(df, ['Value', 'Market Value', 'Total Value', 'Current Value'])
            
            if not symbol_col:
                return False, "Could not find Symbol/Ticker column"
            
            if not quantity_col:
                return False, "Could not find Quantity/Shares column"
            
            if not value_col:
                return False, "Could not find Value/Market Value column"
            
            logger.info(f"Merrill CSV validation passed: {len(df)} rows")
            return True, None
            
        except Exception as e:
            logger.error(f"Merrill CSV validation failed: {e}")
            return False, str(e)
    
    def _preprocess_merrill_csv(self, file_path: str) -> Optional[pd.DataFrame]:
        """
        Preprocess Merrill Lynch CSV to extract the data section
        
        Merrill CSVs have this structure:
        1. Account summary (skip)
        2. Empty line with ""
        3. Data section starting with column headers (Symbol, Description, ...)
        4. Data rows (holdings)
        5. "Balances" row (marker, but cash data follows!)
        6. "Money accounts" row (THIS IS THE CASH - we want this!)
        7. "Cash balance" row
        8. "Pending activity" row
        9. "Total" row (footer - stop here)
        
        Returns:
            pd.DataFrame: Extracted data or None
        """
        try:
            # Read entire file as text
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Log first 30 lines for debugging
            logger.debug("First 30 lines of file:")
            for i, line in enumerate(lines[:30]):
                logger.debug(f"  [{i}]: {line.rstrip()[:100]}")
            
            # Find the header row (starts with "Symbol")
            header_idx = None
            data_start_idx = None
            
            for i, line in enumerate(lines):
                # Look for the column header line - must have Symbol AND Description AND Quantity
                if 'Symbol' in line and 'Description' in line and 'Quantity' in line:
                    header_idx = i
                    data_start_idx = i + 1
                    logger.info(f"Found header at line {i}: {line.rstrip()[:80]}")
                    break
            
            if header_idx is None:
                logger.error("Could not find data section with Symbol/Description/Quantity columns")
                return None
            
            # Find where data ends - ONLY stop at "Total" row, not "Balances"
            # "Balances" is just a section marker, cash data follows it
            data_end_idx = len(lines)
            for i in range(data_start_idx, len(lines)):
                line_stripped = lines[i].strip().strip('"').strip()
                
                # ONLY stop at "Total" row - this is the true footer
                if line_stripped.startswith('Total'):
                    data_end_idx = i
                    logger.info(f"Found 'Total' footer at line {i}, stopping here")
                    break
            
            # Extract header and data lines
            header_line = lines[header_idx]
            data_lines = lines[data_start_idx:data_end_idx]
            
            logger.info(f"Extracting lines {data_start_idx} to {data_end_idx} ({len(data_lines)} lines)")
            
            # Filter out:
            # - Empty lines
            # - Lines that are just commas
            # - "Balances" marker row (no useful data)
            # - "Cash balance" row (usually $0.00)
            # - "Pending activity" row (usually $0.00)
            # BUT KEEP "Money accounts" row - this has the actual cash!
            filtered_lines = []
            for line in data_lines:
                line_stripped = line.strip()
                
                # Skip empty lines
                if not line_stripped or line_stripped == ',' or line_stripped == '""':
                    continue
                
                # Skip the "Balances" marker row (it's just a section header with no data)
                if line_stripped.startswith('"Balances"'):
                    logger.debug(f"Skipping Balances marker row")
                    continue
                
                # Skip "Cash balance" if it's $0.00
                if 'Cash balance' in line and '$0.00' in line:
                    logger.debug(f"Skipping Cash balance row (zero value)")
                    continue
                
                # Skip "Pending activity" if it's $0.00
                if 'Pending activity' in line and '$0.00' in line:
                    logger.debug(f"Skipping Pending activity row (zero value)")
                    continue
                
                # Log if this is a Money accounts row
                if 'Money accounts' in line:
                    logger.info(f"Including Money accounts row: {line.rstrip()[:80]}")
                
                filtered_lines.append(line)
            
            logger.info(f"After filtering: {len(filtered_lines)} data lines")
            
            # Combine into CSV content
            csv_content = header_line + ''.join(filtered_lines)
            
            logger.debug(f"CSV content (last 500 chars):\n{csv_content[-500:]}")
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                tmp.write(csv_content)
                tmp_path = tmp.name
            
            # Load as DataFrame
            df = pd.read_csv(tmp_path, skipinitialspace=True, on_bad_lines='warn')
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            # Strip whitespace from column names
            df.columns = df.columns.str.strip()
            
            # Remove any empty rows
            df = df.dropna(how='all')
            
            # Log what we got
            if 'Symbol' in df.columns:
                logger.info(f"Symbols in parsed DataFrame: {list(df['Symbol'].values)}")
            
            logger.info(f"Extracted Merrill data section: {len(df)} rows, {len(df.columns)} columns")
            
            if len(df) > 0:
                logger.debug(f"First row: {df.iloc[0].to_dict()}")
                logger.debug(f"Last row: {df.iloc[-1].to_dict()}")
            
            self.df = df
            return df
            
        except Exception as e:
            logger.error(f"Error preprocessing Merrill CSV: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None    


    def extract_account_number(self, df: pd.DataFrame) -> Optional[str]:
        """
        Extract account number from Merrill Lynch CSV
        
        Args:
            df: Pandas DataFrame (required by base class signature)
            
        Returns:
            str: Last 4 digits of account number, or None
        """
        # Method 1: Try to extract from the DataFrame if it has an account column
        if df is not None:
            account_col = self.find_column(df, ['Account', 'Account Number', 'Acct'])
            if account_col and not df[account_col].isna().all():
                account = df[account_col].dropna().iloc[0] if len(df[account_col].dropna()) > 0 else None
                if account:
                    alnum = re.sub(r'[^A-Z0-9]', '', str(account).upper())
                    if len(alnum) >= 4:
                        return alnum[-4:]
        
        return None
    
    def extract_export_timestamp(self, file_path: str) -> Optional[str]:
        """
        Extract the export timestamp from Merrill Lynch CSV header
        
        The CSV typically starts with a line like:
        Exported on: 01/25/2026 11:51 AM ET  Selected account(s):...
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            str: ISO format timestamp string, or None if not found
        """
        try:
            from datetime import datetime
            
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read first few lines to find the export timestamp
                for _ in range(10):  # Check first 10 lines
                    line = f.readline()
                    if not line:
                        break
                    
                    # Look for "Exported on:" pattern
                    if 'Exported on:' in line or 'exported on:' in line.lower():
                        # Extract the date/time portion
                        # Pattern: "Exported on: 01/25/2026 11:51 AM ET"
                        match = re.search(r'Exported on:\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)', line, re.IGNORECASE)
                        if match:
                            date_str = match.group(1).strip()
                            # Try to parse with various formats
                            for fmt in ['%m/%d/%Y %I:%M %p', '%m/%d/%Y %H:%M', '%m/%d/%Y']:
                                try:
                                    dt = datetime.strptime(date_str, fmt)
                                    logger.info(f"Extracted export timestamp: {dt.isoformat()}")
                                    return dt.isoformat()
                                except ValueError:
                                    continue
                        
                        # Try simpler date extraction
                        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
                        if date_match:
                            try:
                                dt = datetime.strptime(date_match.group(1), '%m/%d/%Y')
                                logger.info(f"Extracted export date: {dt.isoformat()}")
                                return dt.isoformat()
                            except ValueError:
                                pass
            
            logger.warning("Could not extract export timestamp from CSV")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting export timestamp: {e}")
            return None
    
    def parse_csv(self, file_path: str) -> Dict:
        """
        Parse Merrill Lynch CSV file
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            dict: {
                'account_number_last4': str,
                'total_value': Decimal,
                'holdings': List[Dict],
                'cash_holdings': List[Dict],
                'total_cash': Decimal,
                'export_timestamp': str (ISO format) or None
            }
        """
        # Extract export timestamp BEFORE preprocessing (needs raw file)
        export_timestamp = self.extract_export_timestamp(file_path)
        
        # Preprocess and load CSV
        df = self._preprocess_merrill_csv(file_path)
        
        if df is None:
            raise ValueError("Could not extract data from Merrill Lynch CSV")
        
        # Extract account number
        account_number = self.extract_account_number(df)
        
        # Find column mappings
        columns = self._map_columns(df)
        
        if not columns:
            raise ValueError("Could not map required columns in Merrill Lynch CSV")
        
        # Parse holdings
        holdings = []
        cash_holdings = []
        total_value = Decimal('0.00')
        total_cash = Decimal('0.00')
        
        for idx, row in df.iterrows():
            try:
                holding = self._parse_row(row, columns)
                if holding and holding['total_value'] > 0:
                    if holding['asset_type'] == 'cash':
                        cash_holdings.append(holding)
                        total_cash += holding['total_value']
                    else:
                        holdings.append(holding)
                    total_value += holding['total_value']
            except Exception as e:
                logger.warning(f"Error parsing row {idx}: {e}")
                continue
        
        logger.info(f"Parsed {len(holdings)} investment holdings and {len(cash_holdings)} cash holdings")
        logger.info(f"Total value: ${total_value}, Cash: ${total_cash}")
        
        # Combine all holdings for storage (but mark cash separately)
        all_holdings = holdings + cash_holdings
        
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
        """
        Map CSV columns to standard field names
        
        Returns:
            dict: Mapping of standard names to actual column names
        """
        mapping = {}
        
        mapping['symbol'] = self.find_column(df, [
            'Symbol', 'Ticker', 'Security', 'Security Symbol'
        ])
        
        mapping['description'] = self.find_column(df, [
            'Description', 'Security Description', 'Name', 'Security Name'
        ])
        
        mapping['quantity'] = self.find_column(df, [
            'Quantity', 'Shares', 'Qty', 'Units'
        ])
        
        mapping['price'] = self.find_column(df, [
            'Price', 'Last Price', 'Market Price', 'Current Price', 'Unit Price'
        ])
        
        mapping['value'] = self.find_column(df, [
            'Value', 'Market Value', 'Total Value', 'Current Value', 'Amount'
        ])
        
        mapping['account_type'] = self.find_column(df, [
            'Account Type', 'Type', 'Acct Type'
        ])
        
        required = ['symbol', 'quantity', 'value']
        if not all(mapping.get(field) for field in required):
            logger.error(f"Missing required columns. Mapped: {mapping}")
            return None
        
        logger.info(f"Column mapping: {mapping}")
        return mapping
    
    def _parse_row(self, row: pd.Series, columns: Dict[str, str]) -> Optional[Dict]:
        """
        Parse a single row into a holding
        
        Args:
            row: DataFrame row
            columns: Column mapping
            
        Returns:
            dict: Holding data or None if invalid
        """
        # Extract symbol
        symbol_raw = row[columns['symbol']]
        symbol = self.normalize_symbol(symbol_raw)
        
        # SKIP special footer rows (Total, Balances, etc.)
        symbol_upper = symbol.upper() if symbol else ''
        skip_symbols = {'TOTAL', 'BALANCES', 'CASH BALANCE', 'PENDING ACTIVITY', 'PENDING'}
        if symbol_upper in skip_symbols:
            logger.debug(f"Skipping footer row: {symbol_upper}")
            return None
        
        # Extract description for cash detection
        description = ''
        if columns.get('description') and not pd.isna(row[columns['description']]):
            description = str(row[columns['description']]).strip()
        
        # Check if this is a cash holding BEFORE rejecting empty symbols
        is_cash = self._is_cash_holding(symbol, description)
        
        # Debug logging for potential cash rows
        if is_cash or (symbol and 'MONEY' in str(symbol).upper()):
            logger.info(f"Potential cash row detected:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Description: {description}")
            logger.info(f"  is_cash: {is_cash}")
            logger.info(f"  Full row: {row.to_dict()}")
        
        # Special handling for "Money accounts" rows in Merrill CSVs
        # These have a different column structure - "Money accounts" is in the Symbol field
        if symbol and 'MONEY ACCOUNT' in symbol.upper():
            logger.info(f"Processing Money accounts row...")
            # The value is typically in a different position for these rows
            # Try to find a dollar value in the row
            found_value = None
            for col_name, value in row.items():
                if pd.notna(value):
                    val_str = str(value).strip()
                    # Look for a dollar amount that's not $0.00
                    if val_str.startswith('$') and val_str != '$0.00':
                        val_cleaned = val_str.replace('$', '').replace(',', '').strip()
                        try:
                            val_amount = Decimal(val_cleaned)
                            if val_amount > 0:
                                found_value = val_amount
                                logger.info(f"  Found cash value in column '{col_name}': ${val_amount}")
                                break
                        except Exception as e:
                            logger.debug(f"  Could not parse '{val_str}' as decimal: {e}")
                            continue
            
            if found_value:
                result = {
                    'symbol': 'CASH',
                    'name': description or 'Cash / Money Market',
                    'quantity': Decimal('1.00'),
                    'price': found_value,
                    'total_value': found_value,
                    'asset_type': 'cash',
                    'account_type': None
                }
                logger.info(f"  ✓ Created cash holding: ${found_value}")
                return result
            else:
                logger.warning(f"  ✗ Could not find valid cash value in Money accounts row")
                return None
        
        if not symbol or symbol == '' or symbol == 'N/A':
            if is_cash:
                # Generate a synthetic symbol for cash
                symbol = 'CASH'
            else:
                return None
        
        # Extract quantity
        quantity_str = str(row[columns['quantity']])
        quantity_match = re.search(r'[\d,.]+', quantity_str)
        if quantity_match:
            quantity = self.clean_quantity(quantity_match.group(0))
        else:
            quantity = self.clean_quantity(quantity_str)
        
        # For cash, quantity might be 0 or 1 - that's okay
        if quantity == 0 and not is_cash:
            return None
        
        # For cash with 0 quantity, set to 1
        if quantity == 0 and is_cash:
            quantity = Decimal('1.00')
        
        # Extract total value
        value_str = str(row[columns['value']])
        value_cleaned = value_str.replace('$', '').replace(' ', '').strip()
        
        # Fix Merrill number format
        if ',' in value_cleaned and '.' in value_cleaned:
            parts = value_cleaned.split('.')
            if len(parts) == 2:
                integer_part = parts[0].replace(',', '')
                value_cleaned = f"{integer_part}.{parts[1]}"
        
        total_value = self.clean_currency(value_cleaned)
        
        # For cash with $0 in value column, try to find the real value elsewhere
        if total_value == 0 and is_cash:
            for col_name, value in row.items():
                if pd.notna(value) and col_name != columns['value']:
                    val_str = str(value).strip()
                    if val_str.startswith('$') and val_str != '$0.00':
                        val_cleaned = val_str.replace('$', '').replace(',', '').strip()
                        try:
                            val_amount = Decimal(val_cleaned)
                            if val_amount > 0:
                                total_value = val_amount
                                logger.info(f"Found alternate cash value: ${total_value}")
                                break
                        except:
                            continue
        
        if total_value == 0:
            return None
        
        # Calculate price
        price = total_value / quantity if quantity != 0 else Decimal('0.00')
        
        # For cash, price equals value (1 unit)
        if is_cash:
            price = total_value
            quantity = Decimal('1.00')
        
        # If price column exists, try to use it (but not for cash)
        if not is_cash and columns.get('price') and not pd.isna(row[columns['price']]):
            price_str = str(row[columns['price']])
            price_match = re.search(r'[\d,.]+', price_str)
            if price_match:
                price_from_col = self.clean_currency(price_match.group(0))
                if price_from_col > 0:
                    price = price_from_col
                    total_value = price * quantity
        
        # Detect asset type
        if is_cash:
            asset_type = 'cash'
        else:
            asset_type = self.detect_asset_type(symbol, description)
        
        # Extract account type
        account_type = None
        if columns.get('account_type') and not pd.isna(row[columns['account_type']]):
            account_type_raw = str(row[columns['account_type']]).strip().lower()
            if 'ira' in account_type_raw:
                account_type = 'ira'
            elif 'roth' in account_type_raw:
                account_type = 'roth'
            elif '401k' in account_type_raw or '401(k)' in account_type_raw:
                account_type = '401k'
            elif 'taxable' in account_type_raw or 'individual' in account_type_raw:
                account_type = 'taxable'
        
        return {
            'symbol': symbol,
            'name': description or symbol,
            'quantity': quantity,
            'price': price,
            'total_value': total_value,
            'asset_type': asset_type,
            'account_type': account_type
        }
    
    def _is_cash_holding(self, symbol: str, description: str) -> bool:
        """
        Determine if a row represents a cash holding
        
        Args:
            symbol: The symbol (may be empty for cash, or contain cash identifiers like "Money accounts")
            description: The description field
            
        Returns:
            bool: True if this is a cash holding
        """
        symbol_upper = symbol.upper() if symbol else ''
        desc_upper = description.upper() if description else ''
        
        # Combined text for keyword search
        combined = f"{symbol_upper} {desc_upper}"
        
        # Cash keywords - expanded to catch Merrill's various formats
        cash_keywords = [
            'CASH', 'MONEY MARKET', 'SWEEP', 'SETTLEMENT', 'CORE',
            'FDIC', 'BANK DEPOSIT', 'CASH BALANCE', 'AVAILABLE CASH',
            'UNINVESTED', 'PENDING', 'MONEY ACCOUNTS', 'BANK OF AMERICA',
            'RASP', 'SAVINGS', 'CHECKING', 'DEPOSIT', 'MONEY ACCOUNT'
        ]
        
        for keyword in cash_keywords:
            if keyword in combined:
                return True
        
        return False
    
    def detect_asset_type(self, symbol: str, description: str) -> str:
        """
        Determine the asset type using the shared AssetTypeResolver.
        
        This uses the same logic as cache generation:
        1. Check stock_info_cache
        2. Fetch from yfinance quoteType
        3. Fall back to heuristics
        """
        try:
            from app.services.asset_type_resolver import resolve_asset_type
            return resolve_asset_type(
                symbol=symbol,
                description=description,
                csv_type_field='',  # Merrill doesn't have a type field
                use_cache=True,
                use_yfinance=True
            )
        except ImportError:
            # Fallback if resolver not available
            logger.warning(f"AssetTypeResolver not available, using fallback for {symbol}")
            return self._detect_asset_type_fallback(symbol, description)
    
    def _detect_asset_type_fallback(self, symbol: str, description: str) -> str:
        """Fallback asset type determination if resolver not available"""
        symbol_upper = symbol.upper() if symbol else ''
        desc_lower = description.lower() if description else ''
        
        # Check description
        if 'etf' in desc_lower or 'exchange traded' in desc_lower:
            return 'etf'
        if 'fund' in desc_lower:
            return 'mutual_fund'
        if 'bond' in desc_lower or 'treasury' in desc_lower:
            return 'bond'
        
        # Symbol patterns
        common_etfs = {'VOO', 'VTI', 'SPY', 'QQQ', 'IVV', 'VEA', 'VWO', 'BND', 'AGG'}
        if symbol_upper in common_etfs:
            return 'etf'
        
        if len(symbol_upper) == 5 and symbol_upper.endswith('X'):
            return 'mutual_fund'
        
        return 'stock'
    
    def get_required_columns(self) -> List[str]:
        """Get list of possible required columns"""
        return [
            'Symbol (or Ticker)',
            'Quantity (or Shares)',
            'Value (or Market Value)'
        ]