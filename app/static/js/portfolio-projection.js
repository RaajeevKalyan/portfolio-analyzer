/* =============================================================================
   portfolio-projection.js - Future Value Projections and Risk Metrics
   ============================================================================= */

// Store chart instance
let projectionChart = null;

// Cache key
const PROJECTION_CACHE_KEY = 'portfolioProjectionData';
const PROJECTION_CACHE_TTL = 30 * 60 * 1000; // 30 minutes
const PROJECTION_YEARS_KEY = 'projectionLookbackYears';

/**
 * Get the configured lookback years (default 5)
 */
function getProjectionYears() {
    try {
        const years = localStorage.getItem(PROJECTION_YEARS_KEY);
        if (years && [3, 5, 10].includes(parseInt(years))) {
            return parseInt(years);
        }
    } catch (e) {}
    return 5; // Default
}

/**
 * Set the lookback years and refresh projections
 */
function setProjectionYears(years) {
    try {
        localStorage.setItem(PROJECTION_YEARS_KEY, years.toString());
        // Clear cache since we're changing parameters
        sessionStorage.removeItem(PROJECTION_CACHE_KEY);
        // Re-run projections
        runProjections();
    } catch (e) {
        console.error('Error setting projection years:', e);
    }
}

/**
 * Get cached projection data
 */
function getCachedProjection() {
    try {
        const cached = sessionStorage.getItem(PROJECTION_CACHE_KEY);
        if (cached) {
            const { data, timestamp } = JSON.parse(cached);
            if (Date.now() - timestamp < PROJECTION_CACHE_TTL) {
                return data;
            }
        }
    } catch (e) {
        console.warn('Error reading projection cache:', e);
    }
    return null;
}

/**
 * Cache projection data
 */
function cacheProjection(data) {
    try {
        sessionStorage.setItem(PROJECTION_CACHE_KEY, JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));
    } catch (e) {
        console.warn('Error caching projection:', e);
    }
}

/**
 * Load portfolio projections and risk metrics
 * This runs independently and doesn't block other page elements
 */
async function loadProjections(forceRefresh = false) {
    const container = document.getElementById('projectionContainer');
    if (!container) return;
    
    // Check cache
    if (!forceRefresh) {
        const cached = getCachedProjection();
        if (cached) {
            renderProjections(container, cached);
            return;
        }
    }
    
    // Show "ready to analyze" state
    container.innerHTML = `
        <div class="projection-header">
            <h2><i class="fas fa-chart-line"></i> Portfolio Projections</h2>
            <div class="projection-header-actions">
                <button class="btn-info-round" onclick="showProjectionInfo()" title="How projections are calculated">
                    <i class="fas fa-info"></i>
                </button>
                <button class="btn-refresh-round" onclick="runProjections()" title="Calculate projections">
                    <i class="fas fa-play"></i>
                </button>
            </div>
        </div>
        <div class="projection-summary">
            <div class="projection-stat">
                <div class="projection-stat-label">Current Value</div>
                <div class="projection-stat-value">—</div>
            </div>
            <div class="projection-stat">
                <div class="projection-stat-label">5-Year Projection</div>
                <div class="projection-stat-value">—</div>
            </div>
            <div class="projection-stat">
                <div class="projection-stat-label">10-Year Projection</div>
                <div class="projection-stat-value">—</div>
            </div>
        </div>
        <div class="projection-placeholder">
            <i class="fas fa-calculator"></i>
            <p>Click <i class="fas fa-play"></i> to calculate projections</p>
            <small>Analyzes historical returns and volatility of your holdings</small>
        </div>
    `;
    
    // Auto-run if forceRefresh
    if (forceRefresh) {
        await runProjections();
    }
}

/**
 * Actually run the projection calculations
 */
async function runProjections() {
    const container = document.getElementById('projectionContainer');
    if (!container) return;
    
    const lookbackYears = getProjectionYears();
    
    // Show loading
    container.innerHTML = `
        <div class="projection-header">
            <h2><i class="fas fa-chart-line"></i> Portfolio Projections</h2>
            <div class="projection-header-actions">
                <div class="years-selector">
                    <label>Lookback:</label>
                    <span class="years-loading">${lookbackYears} years</span>
                </div>
                <button class="btn-info-round" onclick="showProjectionInfo()" title="How projections are calculated">
                    <i class="fas fa-info"></i>
                </button>
                <button class="btn-refresh-round" disabled title="Calculating...">
                    <i class="fas fa-spinner fa-spin"></i>
                </button>
            </div>
        </div>
        <div class="projection-loading">
            <i class="fas fa-spinner fa-spin"></i>
            <p>Calculating projections and risk metrics...</p>
            <small>Fetching ${lookbackYears}-year historical data for your holdings</small>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/portfolio/projections?lookback_years=${lookbackYears}`);
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error || 'Failed to load projections');
        }
        
        cacheProjection(result.data);
        renderProjections(container, result.data);
        
    } catch (error) {
        console.error('Error loading projections:', error);
        container.innerHTML = `
            <div class="projection-header">
                <h2><i class="fas fa-chart-line"></i> Portfolio Projections</h2>
            </div>
            <div class="projection-loading">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading projections</p>
                <small>${error.message}</small>
                <button class="btn-refresh" onclick="runProjections()" style="margin-top: 1rem;">
                    <i class="fas fa-sync-alt"></i> Retry
                </button>
            </div>
        `;
    }
}

/**
 * Render projections UI
 */
function renderProjections(container, data) {
    const { current_value, projections, risk_metrics, assumptions } = data;
    const selectedYears = getProjectionYears();
    
    if (!current_value || current_value === 0) {
        container.innerHTML = `
            <div class="projection-loading">
                <i class="fas fa-chart-line"></i>
                <p>No portfolio data available</p>
                <small>Upload holdings to see projections</small>
            </div>
        `;
        return;
    }
    
    // Get 5-year and 10-year projections
    const proj5 = projections.find(p => p.year === 5) || {};
    const proj10 = projections.find(p => p.year === 10) || {};
    
    container.innerHTML = `
        <div class="projection-header">
            <h2><i class="fas fa-chart-line"></i> Portfolio Projections</h2>
            <div class="projection-header-actions">
                <div class="years-selector">
                    <label for="lookbackYears">Lookback:</label>
                    <select id="lookbackYears" onchange="setProjectionYears(this.value)">
                        <option value="3" ${selectedYears === 3 ? 'selected' : ''}>3 years</option>
                        <option value="5" ${selectedYears === 5 ? 'selected' : ''}>5 years</option>
                        <option value="10" ${selectedYears === 10 ? 'selected' : ''}>10 years</option>
                    </select>
                </div>
                <button class="btn-info-round" onclick="showProjectionInfo()" title="How projections are calculated">
                    <i class="fas fa-info"></i>
                </button>
                <button class="btn-refresh-round" onclick="runProjections()" title="Refresh projections">
                    <i class="fas fa-sync-alt"></i>
                </button>
            </div>
        </div>
        
        <div class="projection-summary">
            <div class="projection-stat">
                <div class="projection-stat-label">Current Value</div>
                <div class="projection-stat-value">${formatCurrency(current_value)}</div>
            </div>
            <div class="projection-stat">
                <div class="projection-stat-label">5-Year Projection</div>
                <div class="projection-stat-value positive">${formatCurrency(proj5.base_case || 0)}</div>
                <div class="projection-stat-subtext">Range: ${formatCurrency(proj5.worst_case || 0)} - ${formatCurrency(proj5.best_case || 0)}</div>
            </div>
            <div class="projection-stat">
                <div class="projection-stat-label">10-Year Projection</div>
                <div class="projection-stat-value positive">${formatCurrency(proj10.base_case || 0)}</div>
                <div class="projection-stat-subtext">Range: ${formatCurrency(proj10.worst_case || 0)} - ${formatCurrency(proj10.best_case || 0)}</div>
            </div>
        </div>
        
        <div class="projection-chart-container">
            <div class="projection-chart">
                <canvas id="projectionChart"></canvas>
            </div>
            <div class="projection-legend">
                <div class="projection-legend-item">
                    <div class="projection-legend-color base"></div>
                    <span>Expected (Real Return)</span>
                </div>
                <div class="projection-legend-item">
                    <div class="projection-legend-color best"></div>
                    <span>Best Case (+1σ)</span>
                </div>
                <div class="projection-legend-item">
                    <div class="projection-legend-color worst"></div>
                    <span>Worst Case (-1σ)</span>
                </div>
                <div class="projection-legend-item">
                    <div class="projection-legend-color very-worst"></div>
                    <span>Very Worst (-2σ)</span>
                </div>
            </div>
        </div>
        
        ${renderRiskMetrics(risk_metrics)}
        
        <div class="assumptions-note">
            <strong>Assumptions:</strong> 
            Historical return: ${assumptions.historical_return || 8}% | 
            Volatility: ${assumptions.volatility || 15}% | 
            Inflation: ${assumptions.inflation_rate || 3}% | 
            Projections show real (inflation-adjusted) values.
        </div>
    `;
    
    // Render chart
    renderProjectionChart(projections, current_value);
}

/**
 * Render projection chart
 */
function renderProjectionChart(projections, currentValue) {
    const ctx = document.getElementById('projectionChart');
    if (!ctx) return;
    
    // Destroy existing chart
    if (projectionChart) {
        projectionChart.destroy();
    }
    
    const years = ['Now', ...projections.map(p => `Year ${p.year}`)];
    const baseCase = [currentValue, ...projections.map(p => p.base_case)];
    const bestCase = [currentValue, ...projections.map(p => p.best_case)];
    const worstCase = [currentValue, ...projections.map(p => p.worst_case)];
    const veryWorstCase = [currentValue, ...projections.map(p => p.very_worst_case)];
    
    projectionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: years,
            datasets: [
                {
                    label: 'Best Case',
                    data: bestCase,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: '+1',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.3
                },
                {
                    label: 'Expected',
                    data: baseCase,
                    borderColor: '#667eea',
                    backgroundColor: 'transparent',
                    borderWidth: 2.5,
                    pointRadius: 3,
                    pointBackgroundColor: '#667eea',
                    tension: 0.3
                },
                {
                    label: 'Worst Case',
                    data: worstCase,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    fill: '-1',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.3
                },
                {
                    label: 'Very Worst',
                    data: veryWorstCase,
                    borderColor: '#ef4444',
                    backgroundColor: 'transparent',
                    borderWidth: 1,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    tension: 0.3
                }
            ]
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
                            return `${context.dataset.label}: ${formatCurrency(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                    }
                },
                y: {
                    ticks: {
                        callback: value => formatCurrencyShort(value),
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
 * Render risk metrics section
 */
function renderRiskMetrics(risk_metrics) {
    if (!risk_metrics || !risk_metrics.fund_metrics || risk_metrics.fund_metrics.length === 0) {
        return '';
    }
    
    const { fund_metrics, portfolio_beta, portfolio_sharpe, portfolio_volatility, portfolio_return } = risk_metrics;
    
    // Determine risk levels for coloring
    const betaRisk = portfolio_beta > 1.2 ? 'high' : portfolio_beta < 0.8 ? 'low' : 'medium';
    const sharpeRisk = portfolio_sharpe >= 1 ? 'good' : portfolio_sharpe >= 0.5 ? 'medium' : 'poor';
    const volRisk = portfolio_volatility > 25 ? 'high' : portfolio_volatility < 15 ? 'low' : 'medium';
    
    return `
        <div class="risk-metrics-section">
            <div class="risk-metrics-header">
                <h3><i class="fas fa-tachometer-alt"></i> Fund Risk Metrics</h3>
                <div class="risk-metrics-header-actions">
                    <button class="btn-info-round" onclick="showRiskMetricsInfo()" title="Understanding risk metrics">
                        <i class="fas fa-info"></i>
                    </button>
                </div>
            </div>
            
            <div class="risk-summary-boxes">
                <div class="risk-summary-box">
                    <div class="risk-summary-label">Portfolio Beta (β)</div>
                    <div class="risk-summary-value ${betaRisk === 'high' ? 'warning' : betaRisk === 'low' ? 'good' : ''}">${portfolio_beta.toFixed(2)}</div>
                    <div class="risk-summary-desc">${betaRisk === 'high' ? 'High market sensitivity' : betaRisk === 'low' ? 'Defensive' : 'Market-aligned'}</div>
                </div>
                <div class="risk-summary-box">
                    <div class="risk-summary-label">Sharpe Ratio</div>
                    <div class="risk-summary-value ${sharpeRisk === 'good' ? 'good' : sharpeRisk === 'poor' ? 'warning' : ''}">${portfolio_sharpe.toFixed(2)}</div>
                    <div class="risk-summary-desc">${sharpeRisk === 'good' ? 'Excellent risk-adjusted' : sharpeRisk === 'poor' ? 'Below average' : 'Acceptable'}</div>
                </div>
                <div class="risk-summary-box">
                    <div class="risk-summary-label">Volatility</div>
                    <div class="risk-summary-value ${volRisk === 'high' ? 'warning' : volRisk === 'low' ? 'good' : ''}">${portfolio_volatility.toFixed(1)}%</div>
                    <div class="risk-summary-desc">${volRisk === 'high' ? 'High fluctuation' : volRisk === 'low' ? 'Stable' : 'Moderate swings'}</div>
                </div>
            </div>
            
            <table class="risk-metrics-table">
                <thead>
                    <tr>
                        <th>Fund</th>
                        <th>Beta (β)</th>
                        <th>Sharpe</th>
                        <th>Volatility</th>
                        <th>Ann. Return</th>
                        <th>Alpha</th>
                    </tr>
                </thead>
                <tbody>
                    ${fund_metrics.map(fund => renderRiskRow(fund)).join('')}
                </tbody>
            </table>
        </div>
    `;
}

/**
 * Render a single risk metrics row
 */
function renderRiskRow(fund) {
    const betaClass = fund.beta < 0.8 ? 'good' : fund.beta > 1.2 ? 'warning' : 'neutral';
    const sharpeClass = fund.sharpe_ratio >= 1 ? 'good' : fund.sharpe_ratio >= 0.5 ? 'neutral' : 'bad';
    const volClass = fund.volatility_pct < 15 ? 'low' : fund.volatility_pct < 25 ? 'medium' : 'high';
    const returnClass = fund.annual_return_pct >= 0 ? 'good' : 'bad';
    const alphaClass = fund.alpha_pct >= 0 ? 'good' : 'bad';
    
    return `
        <tr>
            <td>
                <span class="risk-symbol">${fund.symbol}</span>
            </td>
            <td class="risk-value ${betaClass}">
                ${fund.beta.toFixed(2)}
                ${renderBetaBar(fund.beta)}
            </td>
            <td class="risk-value ${sharpeClass}">
                ${fund.sharpe_ratio.toFixed(2)}
            </td>
            <td>
                <span class="volatility-badge ${volClass}">${fund.volatility_pct.toFixed(1)}%</span>
            </td>
            <td class="risk-value ${returnClass}">
                ${fund.annual_return_pct >= 0 ? '+' : ''}${fund.annual_return_pct.toFixed(1)}%
            </td>
            <td class="risk-value ${alphaClass}">
                ${fund.alpha_pct >= 0 ? '+' : ''}${fund.alpha_pct.toFixed(2)}%
            </td>
        </tr>
    `;
}

/**
 * Render beta bar indicator
 */
function renderBetaBar(beta) {
    const width = Math.min(100, (beta / 2) * 100);
    const colorClass = beta < 0.8 ? 'low' : beta > 1.2 ? 'high' : 'medium';
    
    return `
        <div class="beta-indicator">
            <div class="beta-bar">
                <div class="beta-bar-fill ${colorClass}" style="width: ${width}%"></div>
            </div>
        </div>
    `;
}

/**
 * Format currency (short version for chart axis)
 */
function formatCurrencyShort(value) {
    if (value >= 1000000) {
        return '$' + (value / 1000000).toFixed(1) + 'M';
    } else if (value >= 1000) {
        return '$' + (value / 1000).toFixed(0) + 'K';
    }
    return '$' + value.toFixed(0);
}

/**
 * Format currency (full version)
 */
function formatCurrency(value) {
    return '$' + value.toLocaleString('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('projectionContainer')) {
        loadProjections();
    }
});

/**
 * Show projection methodology info panel
 */
function showProjectionInfo() {
    const panel = document.getElementById('infoPanel');
    const overlay = document.getElementById('infoPanelOverlay');
    const title = document.getElementById('infoPanelTitle');
    const content = document.getElementById('infoPanelContent');
    
    title.innerHTML = '<i class="fas fa-chart-line"></i> How Projections Are Calculated';
    content.innerHTML = `
        <div class="info-section">
            <h4>Methodology</h4>
            <p>Portfolio projections are based on <strong>historical performance</strong> of your actual holdings, adjusted for inflation to show <strong>real (inflation-adjusted) values</strong>.</p>
        </div>
        
        <div class="info-section">
            <h4>The Lines Explained</h4>
            <ul class="info-list">
                <li><span class="info-color" style="background: #667eea;"></span><strong>Expected (Blue):</strong> Based on your portfolio's historical annual return minus 3% inflation.</li>
                <li><span class="info-color" style="background: #10b981;"></span><strong>Best Case (+1σ):</strong> If returns are one standard deviation above average each year.</li>
                <li><span class="info-color" style="background: #f59e0b;"></span><strong>Worst Case (-1σ):</strong> If returns are one standard deviation below average.</li>
                <li><span class="info-color" style="background: #ef4444;"></span><strong>Very Worst (-2σ):</strong> A severe downturn scenario (statistically ~2.5% chance).</li>
            </ul>
        </div>
        
        <div class="info-section">
            <h4>Formulas Used</h4>
            <div class="info-formula-block">
                <p><strong>Real Return Rate:</strong></p>
                <code>Real Return = Historical Return − Inflation Rate</code>
                <p class="info-formula-example">Example: 12% historical − 3% inflation = 9% real return</p>
            </div>
            <div class="info-formula-block">
                <p><strong>Expected Value (Year N):</strong></p>
                <code>FV = Current Value × (1 + Real Return)^N</code>
                <p class="info-formula-example">$70,000 × (1.09)^10 = $165,746</p>
            </div>
            <div class="info-formula-block">
                <p><strong>Best/Worst Case Adjustment:</strong></p>
                <code>Adjusted Return = Real Return ± (Volatility × √Years / Years)</code>
                <p class="info-formula-example">±1σ creates the confidence band that widens over time</p>
            </div>
        </div>
        
        <div class="info-section">
            <h4>Your Portfolio's Inputs</h4>
            <p>These values are calculated from your holdings' historical performance:</p>
            <ul class="info-list">
                <li><strong>Historical Return:</strong> Compound annual growth rate (CAGR) over the selected lookback period</li>
                <li><strong>Lookback Period:</strong> Currently set to <strong>${getProjectionYears()} years</strong> (configurable: 3, 5, or 10 years)</li>
                <li><strong>Volatility (σ):</strong> Annualized standard deviation of monthly returns</li>
                <li><strong>Inflation Assumption:</strong> 3% per year (historical average)</li>
            </ul>
            <p class="info-note"><i class="fas fa-cog"></i> You can change the lookback period using the dropdown next to the Projections header.</p>
        </div>
        
        <div class="info-warning">
            <i class="fas fa-exclamation-triangle"></i>
            <span><strong>Important:</strong> Past performance does not guarantee future results. These projections are estimates based on historical data and should not be considered financial advice. Actual returns may vary significantly.</span>
        </div>
    `;
    
    panel.classList.add('open');
    overlay.classList.add('open');
}

/**
 * Show risk metrics info panel
 */
function showRiskMetricsInfo() {
    const panel = document.getElementById('infoPanel');
    const overlay = document.getElementById('infoPanelOverlay');
    const title = document.getElementById('infoPanelTitle');
    const content = document.getElementById('infoPanelContent');
    
    title.innerHTML = '<i class="fas fa-tachometer-alt"></i> Understanding Risk Metrics';
    content.innerHTML = `
        <div class="info-section">
            <h4>Beta (β) - Market Sensitivity</h4>
            <p>Measures how much your fund moves relative to the overall market (S&P 500).</p>
            <ul class="info-list">
                <li><strong>β = 1.0:</strong> Moves exactly with the market</li>
                <li><strong>β > 1.0:</strong> More volatile than market (e.g., 1.2 means 20% more volatile)</li>
                <li><strong>β < 1.0:</strong> Less volatile, more defensive</li>
            </ul>
            <div class="info-example">
                <strong>Example:</strong> A portfolio with β = 1.21 means if the market drops 10%, your portfolio might drop ~12.1%
            </div>
        </div>
        
        <div class="info-section">
            <h4>Sharpe Ratio - Risk-Adjusted Return</h4>
            <p>Measures return earned per unit of risk taken. Higher is better.</p>
            <ul class="info-list">
                <li><strong>&lt; 0.5:</strong> Poor risk-adjusted returns</li>
                <li><strong>0.5 - 1.0:</strong> Acceptable</li>
                <li><strong>1.0 - 2.0:</strong> Good</li>
                <li><strong>&gt; 2.0:</strong> Excellent</li>
            </ul>
            <p class="info-formula">Formula: (Return - Risk-Free Rate) ÷ Volatility</p>
        </div>
        
        <div class="info-section">
            <h4>Volatility - Price Fluctuation</h4>
            <p>Standard deviation of returns, annualized. Shows how much prices swing.</p>
            <ul class="info-list">
                <li><strong>&lt; 15%:</strong> Low volatility (bonds, stable stocks)</li>
                <li><strong>15-25%:</strong> Moderate (typical stock funds)</li>
                <li><strong>&gt; 25%:</strong> High volatility (growth stocks, emerging markets)</li>
            </ul>
        </div>
        
        <div class="info-section">
            <h4>Alpha (α) - Excess Return</h4>
            <p>Return above/below what's expected given the fund's beta.</p>
            <ul class="info-list">
                <li><strong>Positive α:</strong> Fund outperformed expectations (good management)</li>
                <li><strong>Negative α:</strong> Underperformed vs. a passive index</li>
            </ul>
        </div>
        
        <div class="info-warning">
            <i class="fas fa-info-circle"></i>
            <span>Risk metrics are calculated using 5 years of historical data. They help understand past behavior but don't predict future performance.</span>
        </div>
    `;
    
    panel.classList.add('open');
    overlay.classList.add('open');
}

/**
 * Close info panel
 */
function closeInfoPanel() {
    const panel = document.getElementById('infoPanel');
    const overlay = document.getElementById('infoPanelOverlay');
    panel.classList.remove('open');
    overlay.classList.remove('open');
}