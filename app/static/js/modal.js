/* =============================================================================
   modal.js - Underlying Holdings Modal
   ============================================================================= */

const UnderlyingModal = {
    modal: null,
    currentData: [],
    directHoldings: new Set(),
    
    /**
     * Initialize modal
     */
    init() {
        this.modal = document.getElementById('underlyingModal');
        
        if (!this.modal) return;
        
        this.bindEvents();
    },
    
    /**
     * Bind event handlers
     */
    bindEvents() {
        // Close on overlay click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.close();
            }
        });
        
        // Close button
        const closeBtn = this.modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }
        
        // Search input
        const searchInput = document.getElementById('underlyingSearch');
        if (searchInput) {
            searchInput.addEventListener('input', debounce(() => this.filterTable(), 300));
        }
        
        // Overlap filter checkbox
        const overlapCheckbox = document.getElementById('overlapOnlyCheckbox');
        if (overlapCheckbox) {
            overlapCheckbox.addEventListener('change', () => this.filterTable());
        }
        
        // ESC key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.classList.contains('show')) {
                this.close();
            }
        });
    },
    
    /**
     * Open modal and load data for a symbol
     */
    async open(symbol) {
        if (!this.modal) return;
        
        try {
            // Show loading state
            this.modal.classList.add('show');
            document.body.style.overflow = 'hidden';
            
            // Fetch data
            const response = await fetch(`/api/holdings/underlying/${symbol}`);
            
            if (!response.ok) {
                throw new Error('Failed to fetch underlying holdings');
            }
            
            const data = await response.json();
            
            // Update header
            this.updateHeader(data);
            
            // Store data
            this.currentData = data.underlying_holdings || [];
            this.directHoldings = new Set(data.direct_holdings || []);
            
            // Render table
            this.renderTable(this.currentData);
            
            // Reset filters
            const searchInput = document.getElementById('underlyingSearch');
            if (searchInput) searchInput.value = '';
            
            const overlapCheckbox = document.getElementById('overlapOnlyCheckbox');
            if (overlapCheckbox) overlapCheckbox.checked = false;
            
        } catch (error) {
            console.error('Error loading underlying holdings:', error);
            showToast('Error', 'Failed to load underlying holdings. Please try again.', 'error');
            this.close();
        }
    },
    
    /**
     * Close modal
     */
    close() {
        if (this.modal) {
            this.modal.classList.remove('show');
            document.body.style.overflow = '';
        }
    },
    
    /**
     * Update modal header with fund info
     */
    updateHeader(data) {
        this.updateElement('modalFundSymbol', data.symbol);
        this.updateElement('modalFundName', data.name);
        this.updateElement('modalTotalValue', formatCurrency(data.total_value));
        this.updateElement('modalQuantity', `${formatNumber(data.quantity)} shares @ ${formatCurrency(data.price)}`);
        this.updateElement('modalUnderlyingCount', `${data.underlying_holdings.length} stocks`);
    },
    
    /**
     * Render the underlying holdings table
     */
    renderTable(holdings) {
        const tbody = document.getElementById('underlyingTableBody');
        if (!tbody) return;
        
        if (!holdings || holdings.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="empty-state">No underlying holdings data available</td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = holdings.map(holding => {
            const isOverlap = this.directHoldings.has(holding.symbol);
            const sector = holding.sector || 'Unknown';
            const country = holding.country || 'Unknown';
            
            return `
                <tr>
                    <td class="underlying-symbol">${escapeHtml(holding.symbol)}</td>
                    <td class="underlying-name">${escapeHtml(holding.name || holding.symbol)}</td>
                    <td>${formatPercent(holding.weight)}</td>
                    <td>${formatCurrency(holding.value)}</td>
                    <td class="${sector === 'Unknown' ? 'text-muted' : ''}">${escapeHtml(sector)}</td>
                    <td class="${country === 'Unknown' ? 'text-muted' : ''}">${escapeHtml(country)}</td>
                    <td>
                        ${isOverlap ? `
                            <span class="overlap-badge">
                                <i class="fas fa-exclamation-triangle"></i>
                                Also held
                            </span>
                        ` : ''}
                    </td>
                </tr>
            `;
        }).join('');
    },
    
    /**
     * Filter table based on search and overlap filter
     */
    filterTable() {
        const searchInput = document.getElementById('underlyingSearch');
        const overlapCheckbox = document.getElementById('overlapOnlyCheckbox');
        
        const searchTerm = (searchInput?.value || '').toLowerCase().trim();
        const overlapOnly = overlapCheckbox?.checked || false;
        
        let filtered = this.currentData;
        
        // Filter by search term
        if (searchTerm) {
            filtered = filtered.filter(h => 
                h.symbol.toLowerCase().includes(searchTerm) ||
                (h.name && h.name.toLowerCase().includes(searchTerm))
            );
        }
        
        // Filter by overlap
        if (overlapOnly) {
            filtered = filtered.filter(h => this.directHoldings.has(h.symbol));
        }
        
        this.renderTable(filtered);
    },
    
    /**
     * Update element text content
     */
    updateElement(id, content) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = content;
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    UnderlyingModal.init();
});

// Global function for onclick handlers
function viewUnderlying(symbol) {
    UnderlyingModal.open(symbol);
}

function closeUnderlyingModal() {
    UnderlyingModal.close();
}
