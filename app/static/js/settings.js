/* =============================================================================
   settings.js - Settings Modal Management
   ============================================================================= */

const SettingsManager = {
    modal: null,
    backdrop: null,
    isOpen: false,
    
    // Default settings
    defaults: {
        concentrationThreshold: 20,
        overlapWarning: 70,
        sectorLimit: 40,
        brokerVisibility: {}
    },
    
    /**
     * Initialize settings manager
     */
    init() {
        this.modal = document.getElementById('settingsModal');
        this.backdrop = document.getElementById('settingsBackdrop');
        
        if (!this.modal) {
            console.warn('Settings modal not found');
            return;
        }
        
        // Load saved settings
        this.loadSettings();
        
        // Bind events
        this.bindEvents();
    },
    
    /**
     * Bind event handlers
     */
    bindEvents() {
        // Close button
        const closeBtn = this.modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }
        
        // Backdrop click
        if (this.backdrop) {
            this.backdrop.addEventListener('click', () => this.close());
        }
        
        // Save button
        const saveBtn = this.modal.querySelector('#saveSettingsBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveSettings());
        }
        
        // Reset button
        const resetBtn = this.modal.querySelector('#resetSettingsBtn');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.resetToDefaults());
        }
        
        // Slider inputs - update display value on change
        this.modal.querySelectorAll('input[type="range"]').forEach(slider => {
            slider.addEventListener('input', (e) => {
                const valueDisplay = document.getElementById(e.target.id + 'Value');
                if (valueDisplay) {
                    valueDisplay.textContent = e.target.value + '%';
                }
            });
        });
        
        // ESC key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });
    },
    
    /**
     * Open settings modal
     */
    open() {
        if (!this.modal) return;
        
        this.modal.classList.add('open');
        if (this.backdrop) {
            this.backdrop.classList.add('show');
        }
        this.isOpen = true;
        document.body.style.overflow = 'hidden';
    },
    
    /**
     * Close settings modal
     */
    close() {
        if (!this.modal) return;
        
        this.modal.classList.remove('open');
        if (this.backdrop) {
            this.backdrop.classList.remove('show');
        }
        this.isOpen = false;
        document.body.style.overflow = '';
    },
    
    /**
     * Toggle settings modal
     */
    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    },
    
    /**
     * Load settings from localStorage
     */
    loadSettings() {
        // Concentration threshold
        const concentration = getStoredValue('risk_concentration', this.defaults.concentrationThreshold);
        this.setSliderValue('concentrationThreshold', concentration);
        
        // Overlap warning
        const overlap = getStoredValue('risk_overlap', this.defaults.overlapWarning);
        this.setSliderValue('overlapWarning', overlap);
        
        // Sector limit
        const sector = getStoredValue('risk_sector', this.defaults.sectorLimit);
        this.setSliderValue('sectorLimit', sector);
        
        // Broker visibility
        this.loadBrokerVisibility();
    },
    
    /**
     * Set slider value and update display
     */
    setSliderValue(id, value) {
        const slider = document.getElementById(id);
        const display = document.getElementById(id + 'Value');
        
        if (slider) {
            slider.value = value;
        }
        if (display) {
            display.textContent = value + '%';
        }
    },
    
    /**
     * Get slider value
     */
    getSliderValue(id) {
        const slider = document.getElementById(id);
        return slider ? parseInt(slider.value) : null;
    },
    
    /**
     * Load broker visibility settings
     */
    loadBrokerVisibility() {
        const visibility = getStoredValue('broker_visibility', {});
        
        document.querySelectorAll('.broker-item input[type="checkbox"]').forEach(checkbox => {
            const broker = checkbox.id.replace('broker-', '');
            const isVisible = visibility[broker] !== false; // Default to visible
            
            // Don't change if disabled (has data)
            if (!checkbox.disabled) {
                checkbox.checked = isVisible;
            }
        });
    },
    
    /**
     * Save settings to localStorage
     */
    saveSettings() {
        // Save thresholds
        const concentration = this.getSliderValue('concentrationThreshold');
        if (concentration !== null) {
            setStoredValue('risk_concentration', concentration);
        }
        
        const overlap = this.getSliderValue('overlapWarning');
        if (overlap !== null) {
            setStoredValue('risk_overlap', overlap);
        }
        
        const sector = this.getSliderValue('sectorLimit');
        if (sector !== null) {
            setStoredValue('risk_sector', sector);
        }
        
        // Save broker visibility
        const visibility = {};
        document.querySelectorAll('.broker-item input[type="checkbox"]').forEach(checkbox => {
            const broker = checkbox.id.replace('broker-', '');
            visibility[broker] = checkbox.checked;
        });
        setStoredValue('broker_visibility', visibility);
        
        // Show success toast
        showToast('Settings Saved', 'Your preferences have been saved.', 'success');
        
        // Close modal
        this.close();
        
        // Refresh charts with new settings
        if (typeof refreshCharts === 'function') {
            refreshCharts();
        } else {
            // Reload page to apply settings
            location.reload();
        }
    },
    
    /**
     * Reset to default settings
     */
    resetToDefaults() {
        this.setSliderValue('concentrationThreshold', this.defaults.concentrationThreshold);
        this.setSliderValue('overlapWarning', this.defaults.overlapWarning);
        this.setSliderValue('sectorLimit', this.defaults.sectorLimit);
        
        // Reset broker visibility (all visible)
        document.querySelectorAll('.broker-item input[type="checkbox"]').forEach(checkbox => {
            if (!checkbox.disabled) {
                checkbox.checked = true;
            }
        });
        
        showToast('Settings Reset', 'Settings have been reset to defaults.', 'info');
    },
    
    /**
     * Get current threshold values
     */
    getThresholds() {
        return {
            concentration: getStoredValue('risk_concentration', this.defaults.concentrationThreshold),
            overlap: getStoredValue('risk_overlap', this.defaults.overlapWarning),
            sector: getStoredValue('risk_sector', this.defaults.sectorLimit)
        };
    },
    
    /**
     * Check if a broker is visible
     */
    isBrokerVisible(broker) {
        const visibility = getStoredValue('broker_visibility', {});
        return visibility[broker.toLowerCase()] !== false;
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    SettingsManager.init();
});

// Global function to open settings
function openSettings() {
    SettingsManager.open();
}

function closeSettings() {
    SettingsManager.close();
}
