"""
Stock Info Service using yfinance 1.1.0

Replaces mstarpy with yfinance for reliable sector/country data.

CHANGELOG:
- Added: International ticker format support (Issue #3)
- Added: Ticker suffix handling for non-US exchanges (.T, .L, .DE, etc.)
- Added: Better logging for debugging data saves
- Added: More geography mappings for international stocks
- Improved: Error handling and fallback logic

Features:
- 2 second delay between requests
- Persistent cache to avoid re-fetching
- Rate limit: 2000 requests/hour (33/minute)
- Progress tracking for UI
- International ticker support
"""
import logging
import yfinance as yf
import time
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache file location
CACHE_FILE = Path('/app/data/stock_info_cache.json')

# Rate limiting constants
REQUESTS_PER_HOUR = 2000
MIN_DELAY_SECONDS = 2.0  # 2 seconds between requests


class StockInfoService:
    """Service to fetch stock information from Yahoo Finance via yfinance"""
    
    # Geography mappings - expanded for international support
    US_COUNTRIES = {'United States', 'USA', 'US', 'United States of America'}
    
    DEVELOPED_INTERNATIONAL = {
        # Europe
        'United Kingdom', 'UK', 'Great Britain', 'GBR',
        'Germany', 'DEU', 'Federal Republic of Germany',
        'France', 'FRA',
        'Switzerland', 'CHE',
        'Netherlands', 'NLD',
        'Sweden', 'SWE',
        'Norway', 'NOR',
        'Denmark', 'DNK',
        'Finland', 'FIN',
        'Belgium', 'BEL',
        'Austria', 'AUT',
        'Ireland', 'IRL',
        'Spain', 'ESP',
        'Italy', 'ITA',
        'Portugal', 'PRT',
        'Luxembourg', 'LUX',
        # Asia-Pacific Developed
        'Japan', 'JPN',
        'Australia', 'AUS',
        'Singapore', 'SGP',
        'Hong Kong', 'HKG',
        'New Zealand', 'NZL',
        'South Korea', 'Korea, Republic of', 'KOR',
        # North America (non-US)
        'Canada', 'CAN',
        # Israel
        'Israel', 'ISR',
    }
    
    EMERGING_MARKETS = {
        # Asia
        'China', 'CHN', "People's Republic of China",
        'India', 'IND',
        'Taiwan', 'TWN',
        'Indonesia', 'IDN',
        'Thailand', 'THA',
        'Malaysia', 'MYS',
        'Philippines', 'PHL',
        'Vietnam', 'VNM',
        # Latin America
        'Brazil', 'BRA',
        'Mexico', 'MEX',
        'Chile', 'CHL',
        'Colombia', 'COL',
        'Peru', 'PER',
        'Argentina', 'ARG',
        # Europe/Middle East/Africa
        'Russia', 'RUS', 'Russian Federation',
        'Turkey', 'TUR',
        'Poland', 'POL',
        'Czech Republic', 'CZE', 'Czechia',
        'Hungary', 'HUN',
        'South Africa', 'ZAF',
        'Saudi Arabia', 'SAU',
        'United Arab Emirates', 'ARE', 'UAE',
        'Qatar', 'QAT',
        'Egypt', 'EGY',
        'Kuwait', 'KWT',
    }
    
    # International ticker suffix to country mapping
    # Used to infer country when yfinance doesn't return it
    TICKER_SUFFIX_COUNTRY = {
        '.T': 'Japan',           # Tokyo
        '.L': 'United Kingdom',   # London
        '.DE': 'Germany',         # Deutsche Börse
        '.PA': 'France',          # Paris
        '.AS': 'Netherlands',     # Amsterdam
        '.SW': 'Switzerland',     # Swiss
        '.MI': 'Italy',           # Milan
        '.MC': 'Spain',           # Madrid
        '.HK': 'Hong Kong',       # Hong Kong
        '.SS': 'China',           # Shanghai
        '.SZ': 'China',           # Shenzhen
        '.TW': 'Taiwan',          # Taiwan
        '.KS': 'South Korea',     # Korea
        '.AX': 'Australia',       # Australia
        '.TO': 'Canada',          # Toronto
        '.SI': 'Singapore',       # Singapore
        '.NS': 'India',           # NSE India
        '.BO': 'India',           # BSE India
        '.SA': 'Brazil',          # São Paulo
        '.MX': 'Mexico',          # Mexico
        '.JK': 'Indonesia',       # Jakarta
        '.BK': 'Thailand',        # Bangkok
        '.KL': 'Malaysia',        # Kuala Lumpur
    }
    
    def __init__(self):
        self.cache = {}
        self.last_request_time = 0
        self.request_count = 0
        self.request_window_start = datetime.now()
        self._load_cache()
    
    def _load_cache(self):
        """Load persistent cache from disk"""
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, 'r') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached stock info entries")
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self.cache = {}
    
    def _save_cache(self):
        """Save cache to disk"""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.debug(f"Saved {len(self.cache)} entries to cache")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _check_rate_limit(self):
        """Check if we're hitting rate limits"""
        now = datetime.now()
        
        # Reset counter if an hour has passed
        if now - self.request_window_start > timedelta(hours=1):
            self.request_count = 0
            self.request_window_start = now
        
        # Check if we're approaching the limit
        if self.request_count >= REQUESTS_PER_HOUR - 10:  # 10 request buffer
            logger.warning(f"Approaching rate limit: {self.request_count}/{REQUESTS_PER_HOUR} requests in this hour")
            # Wait until next hour
            wait_time = (self.request_window_start + timedelta(hours=1) - now).total_seconds()
            if wait_time > 0:
                logger.warning(f"Rate limit reached. Waiting {wait_time:.0f} seconds...")
                time.sleep(wait_time)
                self.request_count = 0
                self.request_window_start = datetime.now()
    
    def _enforce_delay(self):
        """Enforce minimum 2 second delay between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < MIN_DELAY_SECONDS:
            sleep_time = MIN_DELAY_SECONDS - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _normalize_ticker(self, symbol: str) -> str:
        """
        Normalize ticker symbol for yfinance lookup
        
        Handles international ticker formats and common variations.
        
        Args:
            symbol: Raw ticker symbol
            
        Returns:
            Normalized ticker suitable for yfinance
        """
        if not symbol:
            return symbol
        
        symbol = symbol.strip().upper()
        
        # Already has a suffix, keep as-is
        if '.' in symbol:
            return symbol
        
        # Some international stocks need suffixes added
        # This is a heuristic - yfinance is usually smart enough to find them
        
        return symbol
    
    def _infer_country_from_ticker(self, symbol: str) -> Optional[str]:
        """
        Infer country from ticker suffix if present
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Country name or None
        """
        if not symbol or '.' not in symbol:
            return None
        
        for suffix, country in self.TICKER_SUFFIX_COUNTRY.items():
            if symbol.upper().endswith(suffix):
                return country
        
        return None
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock information from Yahoo Finance
        
        Handles both US and international tickers.
        
        Args:
            symbol: Stock ticker symbol (US or international)
            
        Returns:
            Dict with sector, industry, country, geography or None if failed
        """
        # Normalize symbol
        symbol = self._normalize_ticker(symbol)
        
        # Check cache first (in-memory and persistent)
        if symbol in self.cache:
            logger.debug(f"Using cached info for {symbol}")
            return self.cache[symbol]
        
        # Check rate limits
        self._check_rate_limit()
        
        # Enforce delay
        self._enforce_delay()
        
        try:
            logger.info(f"Fetching Yahoo Finance info for {symbol} ({self.request_count + 1} requests this hour)")
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Increment request counter
            self.request_count += 1
            
            if not info or len(info) == 0:
                logger.warning(f"No info returned for {symbol}")
                # Try to infer country from ticker suffix
                inferred_country = self._infer_country_from_ticker(symbol)
                if inferred_country:
                    result = {
                        'sector': 'Unknown',
                        'industry': 'Unknown',
                        'country': inferred_country,
                        'geography': self._map_country_to_geography(inferred_country)
                    }
                    self.cache[symbol] = result
                    self._save_cache()
                    logger.info(f"Inferred country for {symbol} from ticker: {inferred_country}")
                    return result
                return self._get_placeholder_data()
            
            # Extract relevant fields
            # For stocks: sector, industry, country are direct fields
            # For funds/ETFs: may have 'category' instead of 'sector'
            sector = info.get('sector')
            if not sector or sector == 'Unknown':
                sector = info.get('category', 'Unknown')
            
            industry = info.get('industry', 'Unknown')
            country = info.get('country', 'Unknown')
            
            # If country not found, try to infer from ticker suffix
            if country == 'Unknown' or not country:
                inferred_country = self._infer_country_from_ticker(symbol)
                if inferred_country:
                    country = inferred_country
                    logger.debug(f"Inferred country for {symbol} from ticker: {country}")
            
            # Clean up values
            sector = str(sector).strip() if sector and sector != 'Unknown' else 'Unknown'
            industry = str(industry).strip() if industry and industry != 'Unknown' else 'Unknown'
            country = str(country).strip() if country and country != 'Unknown' else 'Unknown'
            
            # Map to geography region
            geography = self._map_country_to_geography(country)
            
            result = {
                'sector': sector,
                'industry': industry,
                'country': country,
                'geography': geography
            }
            
            # Cache the result (both in-memory and persistent)
            self.cache[symbol] = result
            self._save_cache()
            
            logger.info(f"✓ Info for {symbol}: {sector} / {country} / {geography}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching info for {symbol}: {e}")
            
            # Try to infer country from ticker suffix as fallback
            inferred_country = self._infer_country_from_ticker(symbol)
            if inferred_country:
                result = {
                    'sector': 'Unknown',
                    'industry': 'Unknown',
                    'country': inferred_country,
                    'geography': self._map_country_to_geography(inferred_country)
                }
                self.cache[symbol] = result
                self._save_cache()
                logger.info(f"Fallback: inferred country for {symbol} from ticker: {inferred_country}")
                return result
            
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
            country: Country name
            
        Returns:
            'US', 'International Developed', 'Emerging Markets', or 'Unknown'
        """
        if not country or country == 'Unknown':
            return 'Unknown'
        
        # Normalize for comparison
        country_normalized = country.strip()
        
        # Check US
        if country_normalized in self.US_COUNTRIES or 'United States' in country_normalized:
            return 'US'
        
        # Check Developed International
        if country_normalized in self.DEVELOPED_INTERNATIONAL:
            return 'International Developed'
        
        # Check Emerging Markets
        if country_normalized in self.EMERGING_MARKETS:
            return 'Emerging Markets'
        
        # Default to International Developed for unknown countries
        # (Most stocks in global indices are from developed markets)
        logger.debug(f"Unknown country '{country}', defaulting to International Developed")
        return 'International Developed'
    
    def get_progress_stats(self) -> Dict:
        """
        Get current progress statistics for UI display
        
        Returns:
            Dict with request stats
        """
        now = datetime.now()
        time_in_window = (now - self.request_window_start).total_seconds()
        
        return {
            'cached_symbols': len(self.cache),
            'requests_this_hour': self.request_count,
            'rate_limit': REQUESTS_PER_HOUR,
            'time_in_window_seconds': time_in_window,
            'delay_between_requests': MIN_DELAY_SECONDS
        }
    
    def clear_cache(self):
        """Clear the cache (useful for debugging)"""
        self.cache = {}
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        logger.info("Cache cleared")
    
    def get_cached_symbols(self) -> list:
        """Get list of all cached symbols"""
        return list(self.cache.keys())


# Global instance to maintain cache and rate limiting across calls
_global_service = None

def get_stock_info(symbol: str) -> Optional[Dict]:
    """
    Convenience function to get stock info
    Uses global instance to maintain cache and rate limiting
    
    Returns:
        Dict with sector, industry, country, geography
    """
    global _global_service
    
    if _global_service is None:
        _global_service = StockInfoService()
    
    return _global_service.get_stock_info(symbol)


def get_progress_stats() -> Dict:
    """
    Get current progress statistics for UI display
    
    Returns:
        Dict with request stats
    """
    global _global_service
    
    if _global_service is None:
        _global_service = StockInfoService()
    
    return _global_service.get_progress_stats()


def clear_cache():
    """Clear the stock info cache"""
    global _global_service
    
    if _global_service is None:
        _global_service = StockInfoService()
    
    _global_service.clear_cache()