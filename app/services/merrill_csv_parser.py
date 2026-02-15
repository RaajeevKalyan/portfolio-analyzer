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
        3. Data section starting with column headers
        4. Data rows
        5. Footer with totals (skip)
        
        IMPORTANT: We now KEEP cash rows instead of filtering them out.
        
        Returns:
            pd.DataFrame: Extracted data or None
        """
        try:
            # Read entire file as text
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Find the header row (starts with "Symbol")
            header_idx = None
            data_start_idx = None
            
            for i, line in enumerate(lines):
                # Look for the column header line
                if 'Symbol' in line and 'Description' in line and 'Quantity' in line:
                    header_idx = i
                    data_start_idx = i + 1
                    break
            
            if header_idx is None:
                logger.error("Could not find data section with Symbol/Description/Quantity columns")
                return None
            
            # Find where data ends (look for footer markers like "Total" at start of line)
            data_end_idx = len(lines)
            for i in range(data_start_idx, len(lines)):
                line_content = lines[i].strip().strip('"').strip()
                
                # Stop at footer markers that indicate end of holdings data
                # Be more specific: only stop if line STARTS with these markers
                if line_content.startswith('Total') or line_content.startswith('Balances'):
                    data_end_idx = i
                    break
                    
                # Stop at empty lines after data
                if line_content == '' or line_content == ',':
                    # Check if this is truly the end (no more data after)
                    has_more_data = False
                    for j in range(i+1, min(i+5, len(lines))):
                        if lines[j].strip() and 'Symbol' not in lines[j] and '"Total"' not in lines[j]:
                            has_more_data = True
                            break
                    if not has_more_data:
                        data_end_idx = i
                        break
            
            # Extract header and data lines
            header_line = lines[header_idx]
            data_lines = lines[data_start_idx:data_end_idx]
            
            # Filter out empty lines and lines that are just commas
            # BUT keep cash-related lines
            data_lines = [line for line in data_lines if line.strip() and line.strip() != ',' and line.strip() != '""']
            
            # Combine into CSV content
            csv_content = header_line + ''.join(data_lines)
            
            logger.debug(f"Extracted CSV content:\n{csv_content[:500]}")
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                tmp.write(csv_content)
                tmp_path = tmp.name
            
            # Load as DataFrame
            df = pd.read_csv(tmp_path, skipinitialspace=True, on_bad_lines='skip')
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            # Strip whitespace from column names
            df.columns = df.columns.str.strip()
            
            # Remove any empty rows
            df = df.dropna(how='all')
            
            # Filter out ONLY true footer rows (Total, Pending transactions, etc.)
            # IMPORTANT: We NO LONGER filter out Cash/Money rows
            if 'Symbol' in df.columns:
                df = df[df['Symbol'].notna()]
                # Only filter out summary/footer rows, NOT cash holdings
                df = df[~df['Symbol'].str.contains('^Total$|^Pending|^Balances$', case=False, na=False, regex=True)]
            
            logger.info(f"Extracted Merrill data section: {len(df)} rows, {len(df.columns)} columns")
            logger.debug(f"Columns: {list(df.columns)}")
            
            if len(df) > 0:
                logger.debug(f"First row: {df.iloc[0].to_dict()}")
            
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
                'cash_holdings': List[Dict],  # NEW: Separate list for cash
                'total_cash': Decimal  # NEW: Total cash value
            }
        """
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
            'total_investments': total_value - total_cash
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
        
        # Extract description for cash detection
        description = ''
        if columns.get('description') and not pd.isna(row[columns['description']]):
            description = str(row[columns['description']]).strip()
        
        # Check if this is a cash holding BEFORE rejecting empty symbols
        is_cash = self._is_cash_holding(symbol, description)
        
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
            symbol: The symbol (may be empty for cash)
            description: The description field
            
        Returns:
            bool: True if this is a cash holding
        """
        symbol_upper = symbol.upper() if symbol else ''
        desc_upper = description.upper() if description else ''
        
        # Cash keywords
        cash_keywords = [
            'CASH', 'MONEY MARKET', 'SWEEP', 'SETTLEMENT', 'CORE',
            'FDIC', 'BANK DEPOSIT', 'CASH BALANCE', 'AVAILABLE CASH',
            'UNINVESTED', 'PENDING'
        ]
        
        for keyword in cash_keywords:
            if keyword in symbol_upper or keyword in desc_upper:
                return True
        
        return False
    
    def get_required_columns(self) -> List[str]:
        """Get list of possible required columns"""
        return [
            'Symbol (or Ticker)',
            'Quantity (or Shares)',
            'Value (or Market Value)'
        ]