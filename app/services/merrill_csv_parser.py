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
        1. Account summary in single quotes (skip)
        2. Data section in double quotes (extract this)
        3. Footer info (skip)
        
        Returns:
            pd.DataFrame: Extracted data or None
        """
        try:
            # Read entire file as text
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Method 1: Find data section between "" markers (on separate lines)
            # Look for a line with just "", then content, then another line with just ""
            lines = content.split('\n')
            start_idx = None
            end_idx = None
            
            for i, line in enumerate(lines):
                stripped = line.strip().strip('"').strip()
                if stripped == '' and start_idx is None:
                    # Found first "" marker
                    start_idx = i + 1
                elif stripped == '' and start_idx is not None and i > start_idx + 1:
                    # Found closing "" marker
                    end_idx = i
                    break
            
            if start_idx is not None and end_idx is not None:
                # Extract data section
                data_lines = lines[start_idx:end_idx]
                data_section = '\n'.join(data_lines)
                
                # Save to temporary file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                    tmp.write(data_section)
                    tmp_path = tmp.name
                
                # Load as DataFrame
                df = pd.read_csv(tmp_path, skipinitialspace=True, on_bad_lines='skip')
                
                # Clean up temp file
                os.unlink(tmp_path)
                
                # Strip whitespace from column names
                df.columns = df.columns.str.strip()
                
                # Remove any empty rows
                df = df.dropna(how='all')
                
                logger.info(f"Extracted Merrill data section: {len(df)} rows, {len(df.columns)} columns")
                logger.debug(f"Columns: {list(df.columns)}")
                
                self.df = df
                return df
            
            # Method 2: Try regex approach with modified pattern
            logger.info("Line-by-line approach failed, trying regex...")
            pattern = r'""\s*\n(.*?)\n\s*""'
            matches = re.findall(pattern, content, re.DOTALL)
            
            if matches:
                # Usually the data section is the largest match
                data_section = max(matches, key=len)
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                    tmp.write(data_section)
                    tmp_path = tmp.name
                
                df = pd.read_csv(tmp_path, skipinitialspace=True, on_bad_lines='skip')
                os.unlink(tmp_path)
                
                df.columns = df.columns.str.strip()
                df = df.dropna(how='all')
                
                logger.info(f"Extracted Merrill data section (regex): {len(df)} rows, {len(df.columns)} columns")
                logger.debug(f"Columns: {list(df.columns)}")
                
                self.df = df
                return df
            
            # Method 3: If no quotes found, try loading directly
            logger.info("No quoted sections found, trying direct CSV load...")
            df = pd.read_csv(file_path, skipinitialspace=True, on_bad_lines='skip')
            df.columns = df.columns.str.strip()
            df = df.dropna(how='all')
            
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
                'holdings': List[Dict]
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
        total_value = Decimal('0.00')
        
        for idx, row in df.iterrows():
            try:
                holding = self._parse_row(row, columns)
                if holding and holding['total_value'] > 0:
                    holdings.append(holding)
                    total_value += holding['total_value']
            except Exception as e:
                logger.warning(f"Error parsing row {idx}: {e}")
                continue
        
        logger.info(f"Parsed {len(holdings)} holdings, total value: ${total_value}")
        
        return {
            'account_number_last4': account_number,
            'total_value': total_value,
            'holdings': holdings
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
        symbol = self.normalize_symbol(row[columns['symbol']])
        if not symbol or symbol == '' or symbol == 'N/A':
            return None
        
        # Extract quantity
        quantity_str = str(row[columns['quantity']])
        quantity_match = re.search(r'[\d,.]+', quantity_str)
        if quantity_match:
            quantity = self.clean_quantity(quantity_match.group(0))
        else:
            quantity = self.clean_quantity(quantity_str)
        
        if quantity == 0:
            return None
        
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
        
        # If price column exists, try to use it
        if columns.get('price') and not pd.isna(row[columns['price']]):
            price_str = str(row[columns['price']])
            price_match = re.search(r'[\d,.]+', price_str)
            if price_match:
                price_from_col = self.clean_currency(price_match.group(0))
                if price_from_col > 0:
                    price = price_from_col
                    total_value = price * quantity
        
        # Extract description
        description = ''
        if columns.get('description') and not pd.isna(row[columns['description']]):
            description = str(row[columns['description']]).strip()
        
        # Detect asset type
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
    
    def get_required_columns(self) -> List[str]:
        """Get list of possible required columns"""
        return [
            'Symbol (or Ticker)',
            'Quantity (or Shares)',
            'Value (or Market Value)'
        ]