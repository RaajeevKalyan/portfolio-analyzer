/* =============================================================================
   toast.js - Toast Notification System
   ============================================================================= */

const ToastManager = {
    container: null,
    
    /**
     * Initialize the toast container
     */
    init() {
        if (this.container) return;
        
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    },
    
    /**
     * Show a toast notification
     * @param {string} title - Toast title
     * @param {string} message - Toast message
     * @param {string} type - 'success', 'error', 'warning', or 'info'
     * @param {number} duration - How long to show (ms), 0 for persistent
     */
    show(title, message, type = 'info', duration = 5000) {
        this.init();
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        toast.innerHTML = `
            <i class="toast-icon ${icons[type] || icons.info}"></i>
            <div class="toast-content">
                <div class="toast-title">${escapeHtml(title)}</div>
                <div class="toast-message">${escapeHtml(message)}</div>
            </div>
            <button class="toast-close" aria-label="Close">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Close button handler
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => this.dismiss(toast));
        
        // Add to container
        this.container.appendChild(toast);
        
        // Auto-dismiss after duration
        if (duration > 0) {
            setTimeout(() => this.dismiss(toast), duration);
        }
        
        return toast;
    },
    
    /**
     * Dismiss a toast
     */
    dismiss(toast) {
        if (!toast || !toast.parentNode) return;
        
        toast.classList.add('toast-out');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    },
    
    /**
     * Convenience methods
     */
    success(title, message, duration) {
        return this.show(title, message, 'success', duration);
    },
    
    error(title, message, duration) {
        return this.show(title, message, 'error', duration);
    },
    
    warning(title, message, duration) {
        return this.show(title, message, 'warning', duration);
    },
    
    info(title, message, duration) {
        return this.show(title, message, 'info', duration);
    }
};

// Convenience function
function showToast(title, message, type = 'info', duration = 5000) {
    return ToastManager.show(title, message, type, duration);
}
