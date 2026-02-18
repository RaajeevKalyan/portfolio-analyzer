/* =============================================================================
   progress.js - Resolution Progress Tracking
   ============================================================================= */

const ProgressTracker = {
    element: null,
    interval: null,
    isChecking: false,
    pollInterval: 2000, // 2 seconds
    
    /**
     * Initialize progress tracker
     */
    init() {
        this.element = document.getElementById('resolutionProgress');
        
        // Start checking on page load
        this.startChecking();
    },
    
    /**
     * Start polling for progress updates
     */
    startChecking() {
        // Check immediately
        this.checkProgress();
        
        // Then poll periodically
        this.interval = setInterval(() => this.checkProgress(), this.pollInterval);
    },
    
    /**
     * Stop polling
     */
    stopChecking() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    },
    
    /**
     * Check resolution progress from API
     */
    async checkProgress() {
        try {
            const response = await fetch('/api/resolution/progress');
            const data = await response.json();
            
            if (data.is_resolving) {
                this.isChecking = true;
                this.showProgress(data);
            } else {
                this.hideProgress();
                
                // If we were checking and now done, reload to show updated data
                if (this.isChecking) {
                    this.isChecking = false;
                    this.stopChecking();
                    
                    // Show completion toast
                    showToast('Resolution Complete', 'Holdings data has been updated.', 'success');
                    
                    // Reload after a short delay
                    setTimeout(() => location.reload(), 1500);
                }
            }
        } catch (error) {
            console.error('Error checking progress:', error);
        }
    },
    
    /**
     * Show progress UI with current data
     */
    showProgress(data) {
        if (!this.element) return;
        
        this.element.style.display = 'block';
        
        // Update progress percentage
        const progressPct = data.progress_percentage || 0;
        this.updateElement('progressPercent', `${progressPct}%`);
        this.updateElement('progressBarFill', null, { width: `${progressPct}%` });
        
        // Update remaining count
        const remaining = data.total_remaining || data.unresolved_count || 0;
        this.updateElement('remainingCount', remaining.toString());
        
        // Update cache hits and API calls
        this.updateElement('cacheHits', (data.cached_hits || 0).toString());
        this.updateElement('apiCalls', (data.api_calls || 0).toString());
        
        // Update current symbol
        const currentSymbol = data.current_symbol || '';
        this.updateElement('currentSymbol', currentSymbol);
        
        // Update message based on step
        const message = this.getStepMessage(data);
        this.updateElement('progressMessage', message);
    },
    
    /**
     * Get message for current step
     */
    getStepMessage(data) {
        const step = data.current_step;
        
        switch (step) {
            case 'etf_resolution':
                return 'Resolving ETF/Mutual Fund underlying holdings...';
            
            case 'parent_info':
                const parentDone = data.parent_symbols_processed || 0;
                const parentTotal = data.parent_symbols_total || 0;
                return `Fetching sector data for holdings (${parentDone}/${parentTotal})...`;
            
            case 'underlying_info':
                const underlyingDone = data.underlying_symbols_processed || 0;
                const underlyingTotal = data.underlying_symbols_total || 0;
                return `Enriching underlying holdings (${underlyingDone}/${underlyingTotal})...`;
            
            default:
                return 'Processing holdings data...';
        }
    },
    
    /**
     * Hide progress UI
     */
    hideProgress() {
        if (this.element) {
            this.element.style.display = 'none';
        }
    },
    
    /**
     * Update element content or style
     */
    updateElement(id, content = null, styles = null) {
        const el = document.getElementById(id);
        if (!el) return;
        
        if (content !== null) {
            el.textContent = content;
        }
        
        if (styles) {
            Object.assign(el.style, styles);
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    ProgressTracker.init();
});
