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
        
        Handles:
        - Share class symbols: BRK.B → BRK-B (US convention)
        - International suffixes: Keep as-is (.T, .L, .DE)
        - Common ticker variations
        
        Args:
            symbol: Raw ticker symbol
            
        Returns:
            Normalized ticker suitable for yfinance
        """
        if not symbol:
            return symbol
        
        symbol = symbol.strip().upper()
        
        # Check if this is an international suffix (exchange code)
        # International suffixes are typically 1-3 chars after the dot
        if '.' in symbol:
            parts = symbol.split('.')
            if len(parts) == 2:
                base, suffix = parts
                
                # Check if this is a known international exchange suffix
                suffix_with_dot = f'.{suffix}'
                if suffix_with_dot in self.TICKER_SUFFIX_COUNTRY:
                    # International ticker - keep the dot
                    return symbol
                
                # Check if suffix is a single letter (likely share class: A, B, C)
                # US share classes use dashes in Yahoo Finance
                if len(suffix) == 1 and suffix.isalpha():
                    normalized = f"{base}-{suffix}"
                    logger.debug(f"Normalized share class ticker: {symbol} → {normalized}")
                    return normalized
                
                # Other suffixes with single letters might also be share classes
                # Check common patterns like PR, WS, UN
                if suffix in ['PR', 'WS', 'UN', 'W', 'U']:
                    # These are common warrant/unit suffixes
                    normalized = f"{base}-{suffix}"
                    logger.debug(f"Normalized special suffix: {symbol} → {normalized}")
                    return normalized
        
        return symbol
    
    def _get_ticker_variants(self, symbol: str) -> list:
        """
        Generate ticker variants to try for symbols that might fail
        
        Args:
            symbol: Original ticker symbol
            
        Returns:
            List of ticker variants to try in order
        """
        variants = [symbol]  # Always try original first
        
        # If symbol has a dash, also try with dot
        if '-' in symbol:
            dot_version = symbol.replace('-', '.')
            variants.append(dot_version)
        
        # If symbol has a dot (and wasn't already converted), try dash
        if '.' in symbol:
            dash_version = symbol.replace('.', '-')
            if dash_version not in variants:
                variants.append(dash_version)
        
        # For share class tickers, also try without suffix
        if '-' in symbol or '.' in symbol:
            base = symbol.split('-')[0].split('.')[0]
            if base not in variants:
                variants.append(base)
        
        return variants
    
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
    
    def _is_cache_complete(self, data: Dict) -> bool:
        """
        Check if cached data has real information (not just Unknown placeholders)
        
        Returns True if at least sector OR country is known
        """
        if not data:
            return False
        
        sector = data.get('sector', 'Unknown')
        country = data.get('country', 'Unknown')
        
        # Cache is complete if we have at least one real value
        has_sector = sector and sector != 'Unknown' and sector != 'N/A'
        has_country = country and country != 'Unknown' and country != 'N/A'
        
        return has_sector or has_country
    
    def get_stock_info(self, symbol: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Fetch stock information from Yahoo Finance
        
        Handles both US and international tickers.
        Tries multiple ticker variants for share class symbols.
        
        Args:
            symbol: Stock ticker symbol (US or international)
            force_refresh: If True, ignore cache and fetch fresh data
            
        Returns:
            Dict with sector, industry, country, geography or None if failed
        """
        original_symbol = symbol.strip().upper() if symbol else symbol
        
        # Normalize symbol
        normalized = self._normalize_ticker(symbol)
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            # Check both original and normalized in cache
            for cache_key in [original_symbol, normalized]:
                if cache_key in self.cache:
                    cached = self.cache[cache_key]
                    if self._is_cache_complete(cached):
                        logger.debug(f"Using cached info for {cache_key}")
                        return cached
                    else:
                        logger.debug(f"Cache entry for {cache_key} is incomplete, will retry")
        
        # Get all ticker variants to try
        variants = self._get_ticker_variants(normalized)
        if original_symbol not in variants:
            variants.insert(0, original_symbol)
        
        logger.debug(f"Will try ticker variants: {variants}")
        
        # Check rate limits
        self._check_rate_limit()
        
        # Enforce delay
        self._enforce_delay()
        
        # Try each variant until one works
        last_error = None
        for variant in variants:
            try:
                logger.info(f"Fetching Yahoo Finance info for {variant} ({self.request_count + 1} requests this hour)")
                
                ticker = yf.Ticker(variant)
                info = ticker.info
                
                # Increment request counter
                self.request_count += 1
                
                if not info or len(info) == 0:
                    logger.warning(f"No info returned for {variant}")
                    continue
                
                # Check if we got meaningful data (not just empty/error response)
                # yfinance sometimes returns a dict with just 'trailingPegRatio' for invalid tickers
                if 'sector' not in info and 'country' not in info and 'industry' not in info:
                    if 'longName' not in info and 'shortName' not in info:
                        logger.warning(f"Incomplete response for {variant}, trying next variant")
                        continue
                
                # Extract relevant fields
                sector = info.get('sector')
                if not sector or sector == 'Unknown':
                    sector = info.get('category', 'Unknown')
                
                industry = info.get('industry', 'Unknown')
                country = info.get('country', 'Unknown')
                
                # If country not found, try to infer from ticker suffix
                if country == 'Unknown' or not country:
                    inferred_country = self._infer_country_from_ticker(original_symbol)
                    if inferred_country:
                        country = inferred_country
                        logger.debug(f"Inferred country for {original_symbol} from ticker: {country}")
                
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
                
                # Only cache if we got at least some real data
                if self._is_cache_complete(result):
                    # Cache under original symbol (for future lookups)
                    self.cache[original_symbol] = result
                    if normalized != original_symbol:
                        self.cache[normalized] = result
                    self._save_cache()
                    
                    logger.info(f"✓ Info for {original_symbol}: {sector} / {country} / {geography}")
                    return result
                else:
                    logger.warning(f"Got incomplete data for {variant}: sector={sector}, country={country}")
                    continue
                
            except Exception as e:
                last_error = e
                logger.warning(f"Error fetching {variant}: {e}")
                continue
        
        # All variants failed
        logger.error(f"All ticker variants failed for {original_symbol}: {last_error}")
        
        # Try to infer country from ticker suffix as fallback
        inferred_country = self._infer_country_from_ticker(original_symbol)
        if inferred_country:
            result = {
                'sector': 'Unknown',
                'industry': 'Unknown',
                'country': inferred_country,
                'geography': self._map_country_to_geography(inferred_country)
            }
            self.cache[original_symbol] = result
            self._save_cache()
            logger.info(f"Fallback: inferred country for {original_symbol} from ticker: {inferred_country}")
            return result
        
        # Return placeholder and cache it (so we don't keep retrying)
        placeholder = self._get_placeholder_data()
        self.cache[original_symbol] = placeholder
        self._save_cache()
        
        return placeholder
    
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
