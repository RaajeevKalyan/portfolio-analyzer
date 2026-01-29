"""
Stock Info Service using yfinance 1.1.0

Replaces mstarpy with yfinance for reliable sector/country data.
Features:
- 2 second delay between requests
- Persistent cache to avoid re-fetching
- Rate limit: 2000 requests/hour (33/minute)
- Progress tracking for UI
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
    
    # Geography mappings
    US_COUNTRIES = {'United States', 'USA', 'US'}
    
    DEVELOPED_INTERNATIONAL = {
        'United Kingdom', 'Japan', 'Germany', 'France', 'Canada',
        'Australia', 'Switzerland', 'Netherlands', 'Sweden', 'Norway',
        'Denmark', 'Finland', 'Belgium', 'Austria', 'Ireland', 'Spain',
        'Italy', 'Portugal', 'Singapore', 'Hong Kong', 'New Zealand',
        'UK', 'GBR', 'CAN', 'AUS', 'JPN', 'DEU', 'FRA', 'CHE', 'NLD',
        'Korea, Republic of', 'South Korea'
    }
    
    EMERGING_MARKETS = {
        'China', 'India', 'Brazil', 'Russia', 'Taiwan',
        'Mexico', 'Indonesia', 'Turkey', 'Saudi Arabia', 'South Africa',
        'Thailand', 'Malaysia', 'Poland', 'Chile', 'Philippines', 'Egypt',
        'United Arab Emirates', 'Colombia', 'Peru', 'Czech Republic',
        'CHN', 'IND', 'BRA', 'RUS', 'KOR', 'TWN', 'MEX', 'IDN', 'TUR'
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
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock information from Yahoo Finance
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dict with sector, industry, country, geography or None if failed
        """
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
                return self._get_placeholder_data()
            
            # Extract relevant fields (stocks have these, funds may not)
            sector = info.get('sector', info.get('category', 'Unknown'))
            industry = info.get('industry', 'Unknown')
            country = info.get('country', 'Unknown')
            
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
            
            logger.info(f"✓ Info for {symbol}: {sector} / {country}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching info for {symbol}: {e}")
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
        
        if country in self.US_COUNTRIES or 'United States' in country:
            return 'US'
        elif country in self.DEVELOPED_INTERNATIONAL:
            return 'International Developed'
        elif country in self.EMERGING_MARKETS:
            return 'Emerging Markets'
        else:
            logger.debug(f"Unknown country: {country}, defaulting to International Developed")
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