/* =============================================================================
   top-holdings.js - Aggregated Stock Holdings
   ============================================================================= */

// Cache
const TOP_HOLDINGS_CACHE_KEY = 'topHoldingsData';
const TOP_HOLDINGS_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Get cached top holdings data
 */
function getCachedTopHoldings() {
    try {
        const cached = sessionStorage.getItem(TOP_HOLDINGS_CACHE_KEY);
        if (cached) {
            const { data, timestamp } = JSON.parse(cached);
            if (Date.now() - timestamp < TOP_HOLDINGS_CACHE_TTL) {
                return data;
            }
        }
    } catch (e) {
        console.warn('Error reading top holdings cache:', e);
    }
    return null;
}

/**
 * Cache top holdings data
 */
function cacheTopHoldings(data) {
    try {
        sessionStorage.setItem(TOP_HOLDINGS_CACHE_KEY, JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));
    } catch (e) {
        console.warn('Error caching top holdings:', e);
    }
}

/**
 * Clear top holdings cache
 */
function clearTopHoldingsCache() {
    try {
        sessionStorage.removeItem(TOP_HOLDINGS_CACHE_KEY);
    } catch (e) {
        console.warn('Error clearing top holdings cache:', e);
    }
}

/**
 * Load top holdings - shows placeholder initially
 */
async function loadTopHoldings(forceRefresh = false) {
    const container = document.getElementById('topHoldingsContainer');
    if (!container) return;
    
    // Check cache
    if (!forceRefresh) {
        const cached = getCachedTopHoldings();
        if (cached) {
            renderTopHoldings(container, cached);
            return;
        }
    }
    
    // Show placeholder
    container.innerHTML = `
        <div class="top-holdings-header">
            <h2><i class="fas fa-layer-group"></i> Top Stock Holdings</h2>
            <div class="top-holdings-header-actions">
                <button class="btn-analyze" onclick="runTopHoldings()" title="Calculate top holdings">
                    <i class="fas fa-calculator"></i> Analyze
                </button>
            </div>
        </div>
        <div class="top-holdings-placeholder">
            <i class="fas fa-chart-bar"></i>
            <p>Click <strong>Analyze</strong> to calculate top holdings</p>
            <small>Aggregates direct holdings + stocks held through ETFs/MFs</small>
        </div>
    `;
}

/**
 * Run top holdings calculation
 */
async function runTopHoldings() {
    const container = document.getElementById('topHoldingsContainer');
    if (!container) return;
    
    // Show loading
    container.innerHTML = `
        <div class="top-holdings-header">
            <h2><i class="fas fa-layer-group"></i> Top Stock Holdings</h2>
            <div class="top-holdings-header-actions">
                <button class="btn-refresh-round" disabled>
                    <i class="fas fa-spinner fa-spin"></i>
                </button>
            </div>
        </div>
        <div class="top-holdings-loading">
            <i class="fas fa-spinner fa-spin"></i>
            <p>Calculating top holdings...</p>
            <small>Aggregating direct and indirect stock exposure</small>
        </div>
    `;
    
    try {
        const response = await fetch('/api/top-holdings');
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error || 'Failed to load top holdings');
        }
        
        cacheTopHoldings(result.data);
        renderTopHoldings(container, result.data);
        
    } catch (error) {
        console.error('Error loading top holdings:', error);
        container.innerHTML = `
            <div class="top-holdings-header">
                <h2><i class="fas fa-layer-group"></i> Top Stock Holdings</h2>
            </div>
            <div class="top-holdings-empty">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading top holdings</p>
                <small>${error.message}</small>
                <button class="btn-refresh" onclick="runTopHoldings()" style="margin-top: 1rem;">
                    <i class="fas fa-sync-alt"></i> Retry
                </button>
            </div>
        `;
    }
}

/**
 * Render top holdings UI
 */
function renderTopHoldings(container, data) {
    const { top_holdings, total_stock_value, total_direct_value, total_indirect_value, total_unique_stocks } = data;
    
    // Get cache timestamp for display - show actual time, not relative
    let analysisTimeStr = new Date().toLocaleTimeString();
    try {
        const cached = sessionStorage.getItem(TOP_HOLDINGS_CACHE_KEY);
        if (cached) {
            const { timestamp } = JSON.parse(cached);
            analysisTimeStr = new Date(timestamp).toLocaleTimeString();
        }
    } catch (e) {}
    
    if (!top_holdings || top_holdings.length === 0) {
        container.innerHTML = `
            <div class="top-holdings-header">
                <h2><i class="fas fa-layer-group"></i> Top Stock Holdings</h2>
            </div>
            <div class="top-holdings-empty">
                <i class="fas fa-chart-bar"></i>
                <p>No stock holdings found</p>
                <small>Upload portfolio data to see top holdings</small>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div class="top-holdings-header">
            <h2><i class="fas fa-layer-group"></i> Top Stock Holdings</h2>
            <div class="top-holdings-header-actions">
                <button class="btn-analyze" onclick="clearTopHoldingsCache(); runTopHoldings();" title="Refresh">
                    <i class="fas fa-sync-alt"></i> Refresh
                </button>
            </div>
        </div>
        <div class="analysis-timestamp">
            <i class="fas fa-clock"></i> Last analyzed: ${analysisTimeStr}
        </div>
        
        <div class="top-holdings-summary">
            <div class="top-holdings-stat">
                <div class="top-holdings-stat-label">Total Stock Exposure</div>
                <div class="top-holdings-stat-value">${formatCurrency(total_stock_value)}</div>
            </div>
            <div class="top-holdings-stat">
                <div class="top-holdings-stat-label">Direct Holdings</div>
                <div class="top-holdings-stat-value value-direct">${formatCurrency(total_direct_value)}</div>
            </div>
            <div class="top-holdings-stat">
                <div class="top-holdings-stat-label">Via Funds</div>
                <div class="top-holdings-stat-value value-indirect">${formatCurrency(total_indirect_value)}</div>
            </div>
            <div class="top-holdings-stat">
                <div class="top-holdings-stat-label">Unique Stocks</div>
                <div class="top-holdings-stat-value highlight">${total_unique_stocks}</div>
            </div>
        </div>
        
        <table class="top-holdings-table">
            <thead>
                <tr>
                    <th style="width: 40px;">#</th>
                    <th>Stock</th>
                    <th>Sector</th>
                    <th>Qty</th>
                    <th>Total Value</th>
                    <th>Direct</th>
                    <th>Via Funds</th>
                    <th>Source</th>
                </tr>
            </thead>
            <tbody>
                ${top_holdings.map((holding, index) => renderTopHoldingRow(holding, index)).join('')}
            </tbody>
        </table>
    `;
}

/**
 * Render a single top holding row
 */
function renderTopHoldingRow(holding, index) {
    const rank = index + 1;
    const rankClass = rank <= 3 ? 'top-3' : '';
    
    // Determine source type
    let sourceType = 'direct';
    let sourceLabel = 'Direct only';
    if (holding.direct_value > 0 && holding.indirect_value > 0) {
        sourceType = 'both';
        sourceLabel = 'Direct + Funds';
    } else if (holding.indirect_value > 0) {
        sourceType = 'indirect';
        sourceLabel = 'Funds only';
    }
    
    // Build fund sources tooltip
    let fundSourcesHtml = '';
    if (holding.indirect_sources && holding.indirect_sources.length > 0) {
        fundSourcesHtml = `
            <div class="fund-sources">
                <span class="fund-sources-count">${holding.num_funds} fund${holding.num_funds > 1 ? 's' : ''}</span>
                <div class="fund-sources-tooltip">
                    ${holding.indirect_sources.map(src => `
                        <div class="fund-source-item">
                            <span class="fund-source-name" title="${src.fund_name}">${src.fund}</span>
                            <span class="fund-source-value">${formatCurrency(src.value)}</span>
                        </div>
                    `).join('')}
                    ${holding.num_funds > 5 ? `<div class="fund-source-item"><span class="fund-source-name">+ ${holding.num_funds - 5} more</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    // Format direct holdings info - show shares if available
    let directHtml = '<span class="value-detail">—</span>';
    if (holding.direct_value > 0) {
        const sharesText = holding.direct_shares > 0 
            ? `<span class="shares-count">${formatNumber(holding.direct_shares, 2)} shares</span>` 
            : '';
        directHtml = `
            <div class="direct-breakdown">
                <span class="value-direct">${formatCurrency(holding.direct_value)}</span>
                ${sharesText}
            </div>
        `;
    }
    
    // Format indirect holdings info - show fund count
    let indirectHtml = '<span class="value-detail">—</span>';
    if (holding.indirect_value > 0) {
        indirectHtml = `
            <div class="indirect-breakdown">
                <span class="value-indirect">${formatCurrency(holding.indirect_value)}</span>
                ${fundSourcesHtml}
            </div>
        `;
    }
    
    return `
        <tr>
            <td><span class="rank-badge ${rankClass}">${rank}</span></td>
            <td>
                <div class="stock-info">
                    <span class="stock-symbol">${holding.symbol}</span>
                    <span class="stock-name" title="${holding.name}">${holding.name}</span>
                </div>
            </td>
            <td>
                ${holding.sector ? `<span class="sector-badge">${holding.sector}</span>` : '<span class="sector-badge">—</span>'}
            </td>
            <td>
                <span class="quantity-value">${holding.total_shares ? formatNumber(holding.total_shares, 2) : '—'}</span>
            </td>
            <td>
                <div class="value-breakdown">
                    <span class="value-total">${formatCurrency(holding.total_value)}</span>
                </div>
            </td>
            <td>${directHtml}</td>
            <td>${indirectHtml}</td>
            <td>
                <span class="source-badge ${sourceType}">${sourceLabel}</span>
            </td>
        </tr>
    `;
}