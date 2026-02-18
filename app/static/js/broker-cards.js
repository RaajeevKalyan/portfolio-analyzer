/* =============================================================================
   broker-cards.js - Broker Card Functionality
   ============================================================================= */

// Store broker charts
let brokerCharts = {};

/* =========================================================================
   Tab Switching
   ========================================================================= */

function switchTab(broker, tabName) {
    const card = document.querySelector(`.broker-card[data-broker="${broker}"]`);
    if (!card) return;
    
    // Update tab buttons
    card.querySelectorAll('.broker-tab').forEach(tab => tab.classList.remove('active'));
    event.target.closest('.broker-tab').classList.add('active');
    
    // Update tab panes
    card.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
    const targetPane = card.querySelector(`#${broker}-${tabName}`);
    if (targetPane) targetPane.classList.add('active');
    
    // Load history data when history tab is clicked
    if (tabName === 'history') {
        loadBrokerSnapshots(broker);
    }
}

/* =========================================================================
   History Tab - Load Snapshots from Database
   ========================================================================= */

async function loadBrokerSnapshots(broker) {
    const container = document.getElementById(`${broker}-snapshots-container`);
    if (!container) return;
    
    // Show loading state
    container.innerHTML = '<div class="no-snapshots"><i class="fas fa-spinner fa-spin"></i><p>Loading...</p></div>';
    
    try {
        const response = await fetch(`/api/broker/${broker}/snapshots`);
        const data = await response.json();
        
        if (data.success && data.snapshots && data.snapshots.length > 0) {
            container.innerHTML = `
                <table class="snapshots-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.snapshots.map(s => `
                            <tr>
                                <td class="snapshot-date">${s.date}</td>
                                <td class="snapshot-value">$${parseFloat(s.total_value).toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } else {
            container.innerHTML = `
                <div class="no-snapshots">
                    <i class="fas fa-inbox"></i>
                    <p>No upload history yet</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading snapshots:', error);
        container.innerHTML = `
            <div class="no-snapshots">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading history</p>
            </div>
        `;
    }
}

/* =========================================================================
   Upload Tab - File Handling
   ========================================================================= */

function triggerUpload(broker) {
    const input = document.getElementById(`file-input-${broker}`);
    if (input) input.click();
}

function handleFileSelect(event, broker) {
    const file = event.target.files[0];
    if (file) uploadFile(file, broker);
}

function handleDragOver(event) {
    event.preventDefault();
    event.currentTarget.classList.add('dragover');
}

function handleDragLeave(event) {
    event.currentTarget.classList.remove('dragover');
}

function handleDrop(event, broker) {
    event.preventDefault();
    event.currentTarget.classList.remove('dragover');
    
    const file = event.dataTransfer.files[0];
    if (file && file.name.endsWith('.csv')) {
        uploadFile(file, broker);
    } else {
        showToast('Invalid File', 'Please drop a CSV file', 'error');
    }
}

async function uploadFile(file, broker) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('broker', broker);
    
    showToast('Uploading...', `Processing ${file.name}`, 'success');
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Upload Successful', `Uploaded ${data.data.total_positions} positions!`, 'success');
            
            // Start checking resolution progress
            if (typeof startProgressChecking === 'function') {
                startProgressChecking();
            }
            
            // Reload page after delay
            setTimeout(() => location.reload(), 2000);
        } else {
            showToast('Upload Failed', data.message || 'An error occurred', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showToast('Network Error', `Could not connect: ${error.message}`, 'error');
    }
}

/* =========================================================================
   Overview Tab - Broker Charts
   ========================================================================= */

/**
 * Initialize all broker charts
 * Called from dashboard with broker data from page-data JSON
 */
function initializeBrokerCharts(brokers) {
    if (!brokers || !Array.isArray(brokers)) return;
    
    brokers.forEach(broker => {
        if (broker.has_data) {
            createBrokerChart(broker.name, broker.total_value);
        }
    });
}

/**
 * Create chart for a single broker
 */
async function createBrokerChart(broker, currentValue) {
    const ctx = document.getElementById(`chart-${broker}`);
    if (!ctx) return;
    
    // Try to load real historical data from API
    try {
        const response = await fetch(`/api/broker/${broker}/history`);
        const data = await response.json();
        
        if (data.success && data.history && data.history.length > 0) {
            const labels = data.history.map(h => h.date);
            const values = data.history.map(h => h.value);
            renderBrokerChart(ctx, broker, labels, values);
            return;
        }
    } catch (error) {
        console.error('Error loading chart data:', error);
    }
    
    // Fallback: show single data point if no history
    const today = new Date();
    const dateLabel = today.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    renderBrokerChart(ctx, broker, [dateLabel], [currentValue]);
}

/**
 * Render the chart with given data
 */
function renderBrokerChart(ctx, broker, labels, data) {
    const theme = document.documentElement.getAttribute('data-theme');
    const gridColor = theme === 'dark' ? '#4a5568' : '#e2e8f0';
    const textColor = theme === 'dark' ? '#cbd5e0' : '#718096';
    
    // Destroy existing chart if present
    if (brokerCharts[broker]) {
        brokerCharts[broker].destroy();
    }
    
    brokerCharts[broker] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Portfolio Value',
                data: data,
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                tension: 0.4,
                fill: true,
                pointRadius: data.length === 1 ? 6 : 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$' + context.parsed.y.toLocaleString('en-US', { 
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2
                            });
                        }
                    }
                }
            },
            scales: {
                y: {
                    grid: { color: gridColor },
                    ticks: {
                        color: textColor,
                        callback: function(value) {
                            return '$' + value.toLocaleString('en-US', { maximumFractionDigits: 0 });
                        }
                    }
                },
                x: {
                    grid: { color: gridColor },
                    ticks: { color: textColor }
                }
            }
        }
    });
}

/**
 * Recreate all broker charts (called on theme change)
 */
function recreateBrokerCharts() {
    const pageData = getPageData();
    if (pageData && pageData.brokers) {
        initializeBrokerCharts(pageData.brokers);
    }
}

/* =========================================================================
   Resolution Progress
   ========================================================================= */

let progressInterval = null;

function startProgressChecking() {
    checkResolutionProgress();
    if (!progressInterval) {
        progressInterval = setInterval(checkResolutionProgress, 5000);
    }
}

function stopProgressChecking() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

function checkResolutionProgress() {
    fetch('/api/resolution/progress')
        .then(response => response.json())
        .then(data => {
            const progressDiv = document.getElementById('resolutionProgress');
            if (!progressDiv) return;
            
            if (data.is_resolving) {
                progressDiv.style.display = 'block';
                
                const cachedEl = document.getElementById('cachedCount');
                const requestEl = document.getElementById('requestCount');
                
                if (cachedEl) cachedEl.textContent = data.cached_symbols || 0;
                if (requestEl) requestEl.textContent = data.requests_this_hour || 0;
            } else {
                progressDiv.style.display = 'none';
                stopProgressChecking();
            }
        })
        .catch(error => {
            console.error('Progress check error:', error);
        });
}

/* =========================================================================
   Initialization
   ========================================================================= */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize broker charts if Chart.js is loaded
    if (typeof Chart !== 'undefined') {
        const pageData = getPageData();
        if (pageData && pageData.brokers) {
            initializeBrokerCharts(pageData.brokers);
        }
    }
    
    // Check for ongoing resolution
    checkResolutionProgress();
});