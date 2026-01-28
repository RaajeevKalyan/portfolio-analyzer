"""
Stock Info Service using mstarpy - Replaces yfinance

Save this as: app/services/stock_info_service.py
"""
import logging
import mstarpy
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class StockInfoService:
    """Service to fetch stock/ETF information from Morningstar via mstarpy"""
    
    # Geography mappings
    US_COUNTRIES = {'United States', 'USA', 'US'}
    
    DEVELOPED_INTERNATIONAL = {
        'United Kingdom', 'Japan', 'Germany', 'France', 'Canada',
        'Australia', 'Switzerland', 'Netherlands', 'Sweden', 'Norway',
        'Denmark', 'Finland', 'Belgium', 'Austria', 'Ireland', 'Spain',
        'Italy', 'Portugal', 'Singapore', 'Hong Kong', 'New Zealand',
        'UK', 'GBR'
    }
    
    EMERGING_MARKETS = {
        'China', 'India', 'Brazil', 'Russia', 'South Korea', 'Taiwan',
        'Mexico', 'Indonesia', 'Turkey', 'Saudi Arabia', 'South Africa',
        'Thailand', 'Malaysia', 'Poland', 'Chile', 'Philippines', 'Egypt',
        'United Arab Emirates', 'Colombia', 'Peru', 'Czech Republic',
        'CHN', 'IND', 'BRA', 'RUS', 'KOR', 'TWN'
    }
    
    def __init__(self):
        self.cache = {}
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock information from Morningstar via mstarpy
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dict with sector, industry, country, geography or None if failed
        """
        # Check cache first
        if symbol in self.cache:
            logger.debug(f"Using cached info for {symbol}")
            return self.cache[symbol]
        
        try:
            logger.info(f"Fetching Morningstar info for {symbol}")
            
            # Search for the stock using mstarpy
            # Use search_stock which returns detailed info including sector
            stocks = mstarpy.search_stock(term=symbol, pageSize=5)
            
            if stocks is None or stocks.empty:
                logger.warning(f"No Morningstar data found for {symbol}")
                return self._get_placeholder_data()
            
            # Find exact match (symbol should match)
            exact_match = stocks[stocks['Ticker'] == symbol.upper()]
            
            if exact_match.empty:
                # Try partial match
                logger.debug(f"No exact match, using first result for {symbol}")
                stock_data = stocks.iloc[0]
            else:
                stock_data = exact_match.iloc[0]
            
            # Extract fields from mstarpy data
            sector = stock_data.get('SectorName', 'Unknown')
            industry = stock_data.get('IndustryName', 'Unknown')
            country = stock_data.get('domicile', stock_data.get('CountryId', 'Unknown'))
            
            # Clean up sector/industry names
            if sector and sector != 'Unknown':
                sector = str(sector).strip()
            else:
                sector = 'Unknown'
            
            if industry and industry != 'Unknown':
                industry = str(industry).strip()
            else:
                industry = 'Unknown'
            
            if country and country != 'Unknown':
                country = str(country).strip()
            else:
                country = 'Unknown'
            
            # Map to geography region
            geography = self._map_country_to_geography(country)
            
            result = {
                'sector': sector,
                'industry': industry,
                'country': country,
                'geography': geography
            }
            
            # Cache the result
            self.cache[symbol] = result
            
            logger.info(f"✓ Info for {symbol}: {sector} / {country}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching Morningstar info for {symbol}: {e}")
            # Return placeholder instead of None to avoid blocking
            return self._get_placeholder_data()
    
    def _get_placeholder_data(self) -> Dict:
        """Return placeholder data when fetch fails"""
        return {
            'sector': 'Unknown',
            'industry': 'Unknown',
            'country': 'Unknown',
            'geography': 'Unknown'
        }
    
    def _map_country_to_geography(self, country: str) -> str:
        """
        Map country to geographic region
        
        Args:
            country: Country name or code
            
        Returns:
            'US', 'International Developed', 'Emerging Markets', or 'Unknown'
        """
        if not country or country == 'Unknown':
            return 'Unknown'
        
        if country in self.US_COUNTRIES:
            return 'US'
        elif country in self.DEVELOPED_INTERNATIONAL:
            return 'International Developed'
        elif country in self.EMERGING_MARKETS:
            return 'Emerging Markets'
        else:
            # Log unknown countries for future mapping
            logger.debug(f"Unknown country: {country}, defaulting to International Developed")
            return 'International Developed'
    
    def batch_fetch_info(self, symbols: list, delay: float = 0.2) -> Dict[str, Dict]:
        """
        Fetch info for multiple symbols
        
        Args:
            symbols: List of ticker symbols
            delay: Small delay between requests (mstarpy is more lenient than yfinance)
            
        Returns:
            Dict mapping symbol to info dict
        """
        results = {}
        
        logger.info(f"Batch fetching info for {len(symbols)} symbols...")
        
        for i, symbol in enumerate(symbols):
            logger.info(f"Fetching {i+1}/{len(symbols)}: {symbol}")
            
            info = self.get_stock_info(symbol)
            if info:
                results[symbol] = info
            
            # Small delay to be respectful to Morningstar's API
            if i < len(symbols) - 1:
                time.sleep(delay)
        
        logger.info(f"Batch fetch complete: {len(results)}/{len(symbols)} successful")
        
        return results


# Global instance to maintain cache across calls
_global_service = None

def get_stock_info(symbol: str) -> Optional[Dict]:
    """
    Convenience function to get stock info from Morningstar
    Uses global instance to maintain cache
    
    Returns:
        Dict with sector, industry, country, geography
    """
    global _global_service
    
    if _global_service is None:
        _global_service = StockInfoService()
    
    return _global_service.get_stock_info(symbol)