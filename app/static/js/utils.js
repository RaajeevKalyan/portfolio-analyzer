/* =============================================================================
   utils.js - Utility Functions
   ============================================================================= */

/**
 * Theme Management
 */
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    
    // Update icon
    const toggleBtn = document.getElementById('themeToggle');
    if (toggleBtn) {
        const icon = toggleBtn.querySelector('i');
        if (icon) {
            icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
}

/**
 * Privacy Mode Management
 * Hides all dollar amounts on the page
 */
function initPrivacyMode() {
    const savedPrivacy = localStorage.getItem('privacyMode') === 'true';
    setPrivacyMode(savedPrivacy);
}

function setPrivacyMode(enabled) {
    document.documentElement.setAttribute('data-privacy', enabled ? 'true' : 'false');
    localStorage.setItem('privacyMode', enabled.toString());
    
    // Update icon
    const icon = document.getElementById('privacyIcon');
    if (icon) {
        icon.className = enabled ? 'fas fa-eye-slash' : 'fas fa-eye';
    }
    
    // Update button title
    const btn = document.getElementById('privacyToggle');
    if (btn) {
        btn.title = enabled ? 'Show Values (Privacy Mode On)' : 'Hide Values (Privacy Mode)';
    }
}

function togglePrivacyMode() {
    const currentPrivacy = document.documentElement.getAttribute('data-privacy') === 'true';
    setPrivacyMode(!currentPrivacy);
}

/**
 * Check if privacy mode is enabled
 */
function isPrivacyMode() {
    return document.documentElement.getAttribute('data-privacy') === 'true';
}

// Initialize theme and privacy on page load
document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    initPrivacyMode();
});

/**
 * Format a number with commas and optional decimal places
 */
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined || isNaN(num)) return '0';
    return parseFloat(num).toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Format a number as currency
 */
function formatCurrency(num) {
    if (num === null || num === undefined || isNaN(num)) return '$0.00';
    return '$' + formatNumber(num, 2);
}

/**
 * Format a number as percentage
 */
function formatPercent(num, decimals = 1) {
    if (num === null || num === undefined || isNaN(num)) return '0%';
    return formatNumber(num, decimals) + '%';
}

/**
 * Debounce function to limit how often a function can fire
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Get value from localStorage with default
 */
function getStoredValue(key, defaultValue) {
    try {
        const stored = localStorage.getItem(key);
        if (stored !== null) {
            return JSON.parse(stored);
        }
    } catch (e) {
        console.warn(`Error reading ${key} from localStorage:`, e);
    }
    return defaultValue;
}

/**
 * Set value in localStorage
 */
function setStoredValue(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.warn(`Error writing ${key} to localStorage:`, e);
    }
}

/**
 * Generate a unique ID
 */
function generateId() {
    return 'id-' + Math.random().toString(36).substr(2, 9);
}

/**
 * Check if element is in viewport
 */
function isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Parse URL query parameters
 */
function getQueryParams() {
    const params = {};
    const searchParams = new URLSearchParams(window.location.search);
    for (const [key, value] of searchParams) {
        params[key] = value;
    }
    return params;
}

/**
 * Add event listener with automatic cleanup on page unload
 */
function addManagedEventListener(element, event, handler, options) {
    element.addEventListener(event, handler, options);
    window.addEventListener('unload', () => {
        element.removeEventListener(event, handler, options);
    });
}

/**
 * Get page data from embedded JSON script tag
 * This allows server-rendered data to be accessed by external JS files
 */
function getPageData() {
    try {
        const dataElement = document.getElementById('page-data');
        if (dataElement) {
            return JSON.parse(dataElement.textContent);
        }
    } catch (e) {
        console.warn('Error parsing page data:', e);
    }
    return null;
}