/* =============================================================================
   fund-analysis.js - Fund Expense and Peer Comparison
   ============================================================================= */

// Store chart instances
let comparisonChart = null;

// Cache key for sessionStorage
const FUND_ANALYSIS_CACHE_KEY = 'fundAnalysisData';
const FUND_ANALYSIS_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Get cached fund analysis data
 */
function getCachedFundAnalysis() {
    try {
        const cached = sessionStorage.getItem(FUND_ANALYSIS_CACHE_KEY);
        if (cached) {
            const { data, timestamp } = JSON.parse(cached);
            // Check if cache is still valid (5 minutes)
            if (Date.now() - timestamp < FUND_ANALYSIS_CACHE_TTL) {
                return data;
            }
        }
    } catch (e) {
        console.warn('Error reading fund analysis cache:', e);
    }
    return null;
}

/**
 * Save fund analysis data to cache
 */
function cacheFundAnalysis(data) {
    try {
        sessionStorage.setItem(FUND_ANALYSIS_CACHE_KEY, JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));
    } catch (e) {
        console.warn('Error caching fund analysis:', e);
    }
}

/**
 * Clear fund analysis cache
 */
function clearFundAnalysisCache() {
    try {
        sessionStorage.removeItem(FUND_ANALYSIS_CACHE_KEY);
    } catch (e) {
        console.warn('Error clearing fund analysis cache:', e);
    }
}

/**
 * Refresh fund analysis (clears cache and reloads)
 */
async function refreshFundAnalysis() {
    clearFundAnalysisCache();
    await runFundAnalysis();
}

/**
 * Load and display fund expense analysis
 * Shows placeholder on initial load - user must click to analyze
 */
async function loadFundAnalysis(forceRefresh = false) {
    const container = document.getElementById('fundAnalysisContainer');
    if (!container) return;
    
    // Check cache first (unless force refresh)
    if (!forceRefresh) {
        const cachedData = getCachedFundAnalysis();
        if (cachedData) {
            console.log('Using cached fund analysis data');
            renderFundAnalysis(container, cachedData);
            return;
        }
    }
    
    // Show placeholder state with analyze button (don't auto-run)
    container.innerHTML = `
        <div class="fund-analysis-header">
            <h2><i class="fas fa-coins"></i> Fund Expense Analysis</h2>
            <div class="expense-summary">
                <button class="btn-analyze" onclick="runFundAnalysis()" title="Analyze fund expenses">
                    <i class="fas fa-search-dollar"></i> Analyze
                </button>
                <div class="expense-stat">
                    <div class="expense-stat-label">Total Annual Fees</div>
                    <div class="expense-stat-value">—</div>
                </div>
                <div class="expense-stat">
                    <div class="expense-stat-label">Weighted Avg ER</div>
                    <div class="expense-stat-value">—</div>
                </div>
                <div class="expense-stat">
                    <div class="expense-stat-label">Funds Analyzed</div>
                    <div class="expense-stat-value">0</div>
                </div>
            </div>
        </div>
        <div class="fund-analysis-placeholder">
            <i class="fas fa-search-dollar"></i>
            <p>Click <strong>Analyze</strong> to examine fund expenses</p>
            <small>Fetches expense ratios, Morningstar ratings, and peer recommendations</small>
        </div>
    `;
}

/**
 * Actually run the fund analysis (fetches data from API)
 */
async function runFundAnalysis() {
    const container = document.getElementById('fundAnalysisContainer');
    if (!container) return;
    
    // Show loading state with visible disabled button
    container.innerHTML = `
        <div class="fund-analysis-header">
            <h2><i class="fas fa-coins"></i> Fund Expense Analysis</h2>
            <div class="expense-summary">
                <button class="btn-analyze analyzing" disabled title="Analyzing...">
                    <i class="fas fa-spinner fa-spin"></i> Analyzing...
                </button>
                <div class="expense-stat">
                    <div class="expense-stat-label">Total Annual Fees</div>
                    <div class="expense-stat-value">...</div>
                </div>
                <div class="expense-stat">
                    <div class="expense-stat-label">Weighted Avg ER</div>
                    <div class="expense-stat-value">...</div>
                </div>
                <div class="expense-stat">
                    <div class="expense-stat-label">Funds Analyzed</div>
                    <div class="expense-stat-value">...</div>
                </div>
            </div>
        </div>
        <div class="fund-analysis-loading">
            <i class="fas fa-spinner fa-spin"></i>
            <p>Analyzing fund expenses...</p>
            <small>Fetching expense ratios from Morningstar & Yahoo Finance</small>
        </div>
    `;
    
    try {
        const response = await fetch('/api/fund-analysis/expenses');
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to load fund analysis');
        }
        
        // Cache the result
        cacheFundAnalysis(data.data);
        
        renderFundAnalysis(container, data.data);
        
    } catch (error) {
        console.error('Error loading fund analysis:', error);
        container.innerHTML = `
            <div class="fund-analysis-header">
                <h2><i class="fas fa-coins"></i> Fund Expense Analysis</h2>
            </div>
            <div class="fund-analysis-empty">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading fund analysis</p>
                <small>${error.message}</small>
                <button class="btn-refresh" onclick="runFundAnalysis()" style="margin-top: 1rem;">
                    <i class="fas fa-sync-alt"></i> Retry
                </button>
            </div>
        `;
    }
}

/**
 * Render the fund analysis section
 */
function renderFundAnalysis(container, data) {
    const { top_funds, total_annual_expenses, total_fund_value, weighted_expense_ratio, peer_recommendations } = data;
    
    // Always show header and summary, even with no funds
    const hasFunds = top_funds && top_funds.length > 0;
    
    // Get cache timestamp - show actual time, not relative
    let analysisTimeStr = new Date().toLocaleTimeString();
    try {
        const cached = sessionStorage.getItem(FUND_ANALYSIS_CACHE_KEY);
        if (cached) {
            const { timestamp } = JSON.parse(cached);
            analysisTimeStr = new Date(timestamp).toLocaleTimeString();
        }
    } catch (e) {}
    
    container.innerHTML = `
        <div class="fund-analysis-header">
            <h2><i class="fas fa-coins"></i> Fund Expense Analysis</h2>
            <div class="expense-summary">
                <button class="btn-analyze" onclick="refreshFundAnalysis()" title="Refresh analysis">
                    <i class="fas fa-sync-alt"></i> Refresh
                </button>
                <div class="expense-stat">
                    <div class="expense-stat-label">Total Annual Fees</div>
                    <div class="expense-stat-value ${total_annual_expenses > 500 ? 'warning' : ''}">${formatCurrency(total_annual_expenses || 0)}</div>
                </div>
                <div class="expense-stat">
                    <div class="expense-stat-label">Weighted Avg ER</div>
                    <div class="expense-stat-value ${(weighted_expense_ratio || 0) > 0.5 ? 'warning' : ''}">${(weighted_expense_ratio || 0).toFixed(2)}%</div>
                </div>
                <div class="expense-stat">
                    <div class="expense-stat-label">Funds Analyzed</div>
                    <div class="expense-stat-value">${hasFunds ? top_funds.length : 0}</div>
                </div>
            </div>
        </div>
        <div class="analysis-timestamp">
            <i class="fas fa-clock"></i> Last analyzed: ${analysisTimeStr}
        </div>
        
        ${hasFunds ? `
        <div class="expense-table-container">
            <table class="expense-table">
                <thead>
                    <tr>
                        <th>Fund</th>
                        <th>Category</th>
                        <th>Rating</th>
                        <th>Expense Ratio</th>
                        <th>Value</th>
                        <th>Annual Fee</th>
                        <th>1Y Return</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${top_funds.map(fund => renderFundRow(fund)).join('')}
                </tbody>
            </table>
        </div>
        
        ${renderPeerRecommendations(peer_recommendations, top_funds)}
        
        <div class="comparison-chart-container" id="comparisonChartContainer" style="display: none;">
            <div class="comparison-chart-header">
                <span class="comparison-chart-title">
                    <i class="fas fa-chart-line"></i>
                    <span id="comparisonChartTitle">Performance Comparison</span>
                </span>
                <div class="chart-legend" id="chartLegend"></div>
            </div>
            <div class="comparison-chart">
                <canvas id="comparisonChart"></canvas>
            </div>
        </div>
        ` : `
        <div class="fund-analysis-empty">
            <i class="fas fa-chart-pie"></i>
            <p>No ETFs or Mutual Funds in portfolio</p>
            <small>Upload holdings containing funds to see expense analysis</small>
        </div>
        `}
    `;
}

/**
 * Render a single fund row in the expense table
 */
function renderFundRow(fund) {
    const expenseClass = getExpenseClass(fund.expense_ratio_pct);
    const returnClass = fund.return_m12 >= 0 ? 'positive' : 'negative';
    
    return `
        <tr>
            <td>
                <div class="fund-symbol">${fund.symbol}</div>
                <div class="fund-name" title="${fund.name}">${fund.name}</div>
            </td>
            <td>
                <span class="fund-category">${fund.category || 'Unknown'}</span>
            </td>
            <td>
                ${renderMedalistBadge(fund.medalist_rating)}
                ${renderStarRating(fund.star_rating)}
            </td>
            <td class="expense-ratio ${expenseClass}">
                ${fund.expense_ratio_pct.toFixed(2)}%
            </td>
            <td>
                ${formatCurrency(fund.portfolio_value)}
            </td>
            <td class="annual-expense">
                ${formatCurrency(fund.annual_expense)}
            </td>
            <td class="return-value ${returnClass}">
                ${fund.return_m12 >= 0 ? '+' : ''}${fund.return_m12.toFixed(1)}%
            </td>
            <td>
                <button class="btn-compare" onclick="compareFund('${fund.symbol}')" title="Compare with peers">
                    <i class="fas fa-balance-scale"></i>
                </button>
            </td>
        </tr>
    `;
}

/**
 * Get expense ratio CSS class based on value
 */
function getExpenseClass(expenseRatioPct) {
    if (expenseRatioPct <= 0.1) return 'low';
    if (expenseRatioPct <= 0.5) return 'medium';
    return 'high';
}

/**
 * Render medalist rating badge
 */
function renderMedalistBadge(rating) {
    if (!rating || rating === 'Unknown') {
        return '<span class="medalist-badge unknown"><i class="fas fa-question"></i> N/A</span>';
    }
    
    const ratingLower = rating.toLowerCase();
    const icons = {
        'gold': 'fa-medal',
        'silver': 'fa-medal',
        'bronze': 'fa-medal',
        'neutral': 'fa-minus-circle',
        'negative': 'fa-thumbs-down'
    };
    
    return `
        <span class="medalist-badge ${ratingLower}">
            <i class="fas ${icons[ratingLower] || 'fa-question'}"></i>
            ${rating}
        </span>
    `;
}

/**
 * Render star rating
 */
function renderStarRating(stars) {
    let html = '<div class="star-rating">';
    for (let i = 1; i <= 5; i++) {
        html += `<i class="fas fa-star ${i <= stars ? 'filled' : ''}"></i>`;
    }
    html += '</div>';
    return html;
}

/**
 * Render peer recommendations section
 */
function renderPeerRecommendations(recommendations, topFunds) {
    if (!recommendations || Object.keys(recommendations).length === 0) {
        return '';
    }
    
    // Build a map of category -> funds in that category
    const categoryFunds = {};
    if (topFunds) {
        topFunds.forEach(fund => {
            if (fund.category && fund.category !== 'Unknown') {
                if (!categoryFunds[fund.category]) {
                    categoryFunds[fund.category] = [];
                }
                categoryFunds[fund.category].push(fund.symbol);
            }
        });
    }
    
    let html = `
        <div class="peer-recommendations">
            <h3><i class="fas fa-lightbulb"></i> Lower-Cost Alternatives by Category</h3>
            <p class="peer-recommendations-desc">Gold/Silver rated funds in the same categories as your holdings with potentially lower expense ratios.</p>
    `;
    
    for (const [category, peers] of Object.entries(recommendations)) {
        if (peers.length === 0) continue;
        
        // Get the funds you own in this category
        const ownedInCategory = categoryFunds[category] || [];
        const ownedText = ownedInCategory.length > 0 
            ? `Alternatives for: <strong>${ownedInCategory.join(', ')}</strong>`
            : '';
        
        html += `
            <div class="peer-category">
                <div class="peer-category-header">
                    <div>
                        <span class="peer-category-name"><i class="fas fa-folder"></i> ${category}</span>
                        ${ownedText ? `<div class="peer-category-owned">${ownedText}</div>` : ''}
                    </div>
                    <span class="peer-category-count">${peers.length} alternative${peers.length > 1 ? 's' : ''}</span>
                </div>
                <div class="peer-cards">
                    ${peers.map(peer => renderPeerCard(peer)).join('')}
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    return html;
}

/**
 * Render a peer fund card
 */
function renderPeerCard(peer) {
    const expenseClass = getExpenseClass(peer.expense_ratio * 100);
    const returnClass = peer.return_m12 >= 0 ? 'positive' : 'negative';
    
    return `
        <div class="peer-card">
            <div class="peer-card-header">
                <div>
                    <div class="peer-card-symbol">${peer.symbol}</div>
                    <div class="peer-card-name">${peer.name}</div>
                </div>
                ${renderMedalistBadge(peer.medalist_rating)}
            </div>
            <div class="peer-card-stats">
                <div class="peer-stat">
                    <div class="peer-stat-label">Expense</div>
                    <div class="peer-stat-value ${expenseClass}">${(peer.expense_ratio * 100).toFixed(2)}%</div>
                </div>
                <div class="peer-stat">
                    <div class="peer-stat-label">1Y Return</div>
                    <div class="peer-stat-value ${returnClass}">${peer.return_m12 >= 0 ? '+' : ''}${peer.return_m12.toFixed(1)}%</div>
                </div>
            </div>
        </div>
    `;
}

/**
 * Compare a fund with its peers
 */
async function compareFund(symbol) {
    const chartContainer = document.getElementById('comparisonChartContainer');
    const chartTitle = document.getElementById('comparisonChartTitle');
    const legendContainer = document.getElementById('chartLegend');
    
    if (!chartContainer) return;
    
    chartContainer.style.display = 'block';
    chartTitle.textContent = `Loading ${symbol} comparison...`;
    legendContainer.innerHTML = '';
    
    try {
        const response = await fetch(`/api/fund-analysis/compare/${symbol}?days=365`);
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to load comparison');
        }
        
        renderComparisonChart(data.data);
        
    } catch (error) {
        console.error('Error comparing fund:', error);
        chartTitle.textContent = `Error loading comparison for ${symbol}`;
    }
}

/**
 * Render performance comparison chart
 */
function renderComparisonChart(data) {
    const ctx = document.getElementById('comparisonChart');
    const chartTitle = document.getElementById('comparisonChartTitle');
    const legendContainer = document.getElementById('chartLegend');
    
    if (!ctx) return;
    
    // Check if we have peer data
    const hasPeers = data.peers && data.peers.length > 0 && data.peers.some(p => p.nav_history && p.nav_history.length > 0);
    
    if (hasPeers) {
        chartTitle.textContent = `${data.fund.symbol} vs Category Peers`;
    } else {
        chartTitle.textContent = `${data.fund.symbol} Performance (No comparable peers found in ${data.category || 'category'})`;
    }
    
    // Destroy existing chart
    if (comparisonChart) {
        comparisonChart.destroy();
    }
    
    // Prepare datasets
    const datasets = [];
    const colors = ['#667eea', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
    
    // Fund NAV data
    if (data.fund.nav_history && data.fund.nav_history.length > 0) {
        const fundData = normalizeNavData(data.fund.nav_history);
        datasets.push({
            label: data.fund.symbol,
            data: fundData.values,
            borderColor: colors[0],
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.1
        });
    }
    
    // Peer NAV data (only if peers exist)
    if (hasPeers) {
        data.peers.forEach((peer, idx) => {
            if (peer.nav_history && peer.nav_history.length > 0) {
                const peerData = normalizeNavData(peer.nav_history);
                datasets.push({
                    label: peer.symbol,
                    data: peerData.values,
                    borderColor: colors[(idx + 1) % colors.length],
                    backgroundColor: 'transparent',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    borderDash: [5, 5],
                    tension: 0.1
                });
            }
        });
    }
    
    if (datasets.length === 0) {
        chartTitle.textContent = `No performance history available for ${data.fund.symbol}`;
        legendContainer.innerHTML = '';
        return;
    }
    
    // Get labels from first dataset
    const labels = data.fund.nav_history.map(d => d.date);
    
    // Render legend
    legendContainer.innerHTML = datasets.map((ds, i) => `
        <div class="legend-item">
            <div class="legend-color" style="background: ${ds.borderColor}"></div>
            <span>${ds.label}${i === 0 ? ' (Your Fund)' : ' (Peer)'}</span>
        </div>
    `).join('');
    
    // Create chart
    comparisonChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y.toFixed(2)}%`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: { display: false },
                    ticks: {
                        maxTicksLimit: 6,
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Growth (%)',
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                    },
                    ticks: {
                        callback: value => value.toFixed(0) + '%',
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                    },
                    grid: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--border-light')
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });
}

/**
 * Normalize NAV data to percentage growth from start
 */
function normalizeNavData(navHistory) {
    if (!navHistory || navHistory.length === 0) {
        return { dates: [], values: [] };
    }
    
    const startNav = navHistory[0].total_return || navHistory[0].nav || 100;
    
    return {
        dates: navHistory.map(d => d.date),
        values: navHistory.map(d => {
            const currentNav = d.total_return || d.nav || startNav;
            return ((currentNav - startNav) / startNav) * 100;
        })
    };
}

/**
 * Format currency
 */
function formatCurrency(value) {
    return '$' + value.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load fund analysis if container exists
    if (document.getElementById('fundAnalysisContainer')) {
        loadFundAnalysis();
    }
});