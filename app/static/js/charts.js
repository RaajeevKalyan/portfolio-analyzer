/* =============================================================================
   charts.js - Risk Analysis Charts (Sector, Geography, Concentration)
   ============================================================================= */

// Chart instances (for cleanup)
let sectorChart = null;
let geographyChart = null;
let concentrationChart = null;

/**
 * Initialize all charts
 */
function initCharts(riskMetrics) {
    if (!riskMetrics) {
        console.warn('No risk metrics provided for charts');
        return;
    }
    
    createSectorChart(riskMetrics.sectors);
    createGeographyChart(riskMetrics.geography);
    createConcentrationChart(riskMetrics.concentration);
}

/**
 * Refresh all charts with current data
 */
function refreshCharts() {
    // Fetch fresh data and re-render
    fetch('/api/risk-metrics')
        .then(response => response.json())
        .then(result => {
            // API returns {success: true, data: {...}}
            if (result.success && result.data) {
                initCharts(result.data);
            } else {
                console.error('Risk metrics API error:', result.error || 'Unknown error');
            }
        })
        .catch(error => {
            console.error('Error fetching risk metrics:', error);
        });
}

/**
 * Create Sector Allocation Chart (Horizontal Bar)
 */
function createSectorChart(sectors) {
    const ctx = document.getElementById('sectorChart');
    const legendDiv = document.getElementById('sectorLegend');
    const container = ctx ? ctx.parentElement : document.querySelector('.sector-chart-container');
    
    // Check for empty state
    if (!sectors || Object.keys(sectors).length === 0) {
        showEmptyState(container, 'Sector data not available yet');
        if (legendDiv) legendDiv.innerHTML = '';
        return;
    }
    
    // Check if only Unknown
    if (Object.keys(sectors).length === 1 && sectors['Unknown']) {
        showEmptyState(container, 'Sector data not available yet');
        if (legendDiv) legendDiv.innerHTML = '';
        return;
    }
    
    // Sort sectors by value descending
    const sortedEntries = Object.entries(sectors).sort((a, b) => b[1] - a[1]);
    const labels = sortedEntries.map(([k]) => k);
    const data = sortedEntries.map(([, v]) => v);
    
    // Get threshold from settings
    const threshold = SettingsManager ? SettingsManager.getThresholds().sector : 40;
    
    // Color sectors exceeding threshold in red
    const backgroundColors = labels.map((label, idx) => {
        if (label === 'Unknown') return '#cbd5e0';
        return data[idx] > threshold ? '#ef4444' : '#667eea';
    });
    
    // Destroy existing chart
    if (sectorChart) {
        sectorChart.destroy();
    }
    
    // Reset container if it was showing empty state
    if (container && !ctx) {
        container.innerHTML = '<canvas id="sectorChart"></canvas>';
    }
    
    const canvas = document.getElementById('sectorChart');
    if (!canvas) return;
    
    sectorChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: backgroundColors,
                borderColor: '#ffffff',
                borderWidth: 2,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => context.parsed.x.toFixed(1) + '%'
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: (value) => value + '%'
                    },
                    grid: {
                        color: 'rgba(0,0,0,0.05)'
                    }
                },
                y: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
    
    // Update legend
    if (legendDiv) {
        legendDiv.innerHTML = sortedEntries.map(([label, value], idx) =>
            `<div class="chart-legend-item">
                <div class="legend-color" style="background: ${backgroundColors[idx]};"></div>
                <span class="legend-label">${escapeHtml(label)}</span>
                <span class="legend-value">${value.toFixed(1)}%</span>
            </div>`
        ).join('');
    }
}

/**
 * Create Geography Chart (Doughnut)
 */
function createGeographyChart(geography) {
    const ctx = document.getElementById('geographyChart');
    const legendDiv = document.getElementById('geographyLegend');
    const container = ctx ? ctx.parentElement : document.querySelector('.geography-chart-container');
    
    // Check for empty state
    if (!geography || Object.keys(geography).length === 0) {
        showEmptyState(container, 'Geography data not available yet');
        if (legendDiv) legendDiv.innerHTML = '';
        return;
    }
    
    // Check if only Unknown
    if (Object.keys(geography).length === 1 && geography['Unknown']) {
        showEmptyState(container, 'Geography data not available yet');
        if (legendDiv) legendDiv.innerHTML = '';
        return;
    }
    
    const labels = Object.keys(geography);
    const data = Object.values(geography);
    
    // Color mapping
    const colorMap = {
        'US': '#667eea',
        'International Developed': '#764ba2',
        'Emerging Markets': '#f093fb',
        'Cash': '#10b981',
        'Unknown': '#cbd5e0',
        'Other': '#a0aec0'
    };
    
    const backgroundColors = labels.map(label => colorMap[label] || '#a0aec0');
    
    // Destroy existing chart
    if (geographyChart) {
        geographyChart.destroy();
    }
    
    // Reset container if needed
    if (container && !ctx) {
        container.innerHTML = '<canvas id="geographyChart"></canvas>';
    }
    
    const canvas = document.getElementById('geographyChart');
    if (!canvas) return;
    
    geographyChart = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: backgroundColors,
                borderColor: '#ffffff',
                borderWidth: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => context.label + ': ' + context.parsed.toFixed(1) + '%'
                    }
                }
            },
            cutout: '60%'
        }
    });
    
    // Update legend
    if (legendDiv) {
        legendDiv.innerHTML = labels.map((label, idx) =>
            `<div class="chart-legend-item">
                <div class="legend-color" style="background: ${backgroundColors[idx]};"></div>
                <span class="legend-label">${escapeHtml(label)}</span>
                <span class="legend-value">${data[idx].toFixed(1)}%</span>
            </div>`
        ).join('');
    }
}

/**
 * Create Concentration Chart/List
 */
function createConcentrationChart(concentration) {
    const container = document.querySelector('.concentration-chart-container');
    
    if (!container) return;
    
    // Get threshold from settings
    const threshold = SettingsManager ? SettingsManager.getThresholds().concentration : 20;
    
    // Check if we have any holdings data at all
    // Look for actual holding rows (not the empty state message row)
    const holdingRows = document.querySelectorAll('#holdingsTableBody .holding-row');
    const hasHoldings = holdingRows && holdingRows.length > 0;
    
    // Also check if total net worth is > 0 as another indicator
    const netWorthElement = document.querySelector('.net-worth-box.primary .box-value');
    const netWorthText = netWorthElement ? netWorthElement.textContent : '$0.00';
    const netWorth = parseFloat(netWorthText.replace(/[$,]/g, '')) || 0;
    
    if (!hasHoldings || netWorth === 0) {
        // No data at all - show same message as other charts
        container.innerHTML = `
            <p class="empty-state">Stock data not available yet</p>
        `;
        return;
    }
    
    // Filter stocks that exceed the threshold (client-side filtering)
    const highConcentration = (concentration || []).filter(item => item.allocation_pct > threshold);
    
    if (highConcentration.length === 0) {
        // Data exists but no concentration issues - this is good!
        container.innerHTML = `
            <div class="success-state">
                <i class="fas fa-check-circle"></i>
                <p>No high concentration detected</p>
                <small>No individual stocks exceed the ${threshold}% threshold</small>
            </div>
        `;
        return;
    }
    
    // Show concentration warnings
    let html = `
        <div class="concentration-warning">
            <i class="fas fa-exclamation-triangle"></i>
            <div class="concentration-warning-text">
                ${highConcentration.length} stock${highConcentration.length > 1 ? 's' : ''} exceed${highConcentration.length === 1 ? 's' : ''} 
                the ${threshold}% concentration threshold
            </div>
        </div>
        <div class="concentration-list">
    `;
    
    highConcentration.forEach(item => {
        const pct = item.allocation_pct.toFixed(1);
        html += `
            <div class="concentration-item">
                <span class="concentration-symbol">${escapeHtml(item.symbol)}</span>
                <div class="concentration-bar">
                    <div class="concentration-bar-fill" style="width: ${Math.min(pct, 100)}%"></div>
                </div>
                <span class="concentration-value">${pct}%</span>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

/**
 * Show empty state in a container
 */
function showEmptyState(container, message) {
    if (!container) return;
    
    container.innerHTML = `
        <p class="empty-state">${escapeHtml(message)}</p>
    `;
}

/**
 * Escape HTML helper (if not defined elsewhere)
 */
if (typeof escapeHtml !== 'function') {
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}