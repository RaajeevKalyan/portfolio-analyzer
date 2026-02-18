/* =============================================================================
   upload.js - CSV Upload Modal Functionality
   ============================================================================= */

let currentBrokerId = null;
let selectedFile = null;

/**
 * Open the upload modal for a specific broker
 */
function openUploadModal(brokerId, brokerName) {
    currentBrokerId = brokerId;
    selectedFile = null;
    
    // Update modal content
    document.getElementById('uploadBrokerId').value = brokerId;
    document.getElementById('uploadBrokerName').textContent = `Upload CSV for ${brokerName}`;
    
    // Reset form state
    document.getElementById('csvFile').value = '';
    document.getElementById('selectedFile').style.display = 'none';
    document.getElementById('uploadError').style.display = 'none';
    document.getElementById('uploadSuccess').style.display = 'none';
    document.getElementById('uploadSubmitBtn').disabled = true;
    document.getElementById('uploadDropzone').style.display = 'block';
    
    // Show modal
    document.getElementById('uploadModal').classList.add('show');
    document.body.style.overflow = 'hidden';
    
    // Setup drag and drop
    setupDragAndDrop();
}

/**
 * Close the upload modal
 */
function closeUploadModal() {
    document.getElementById('uploadModal').classList.remove('show');
    document.body.style.overflow = '';
    currentBrokerId = null;
    selectedFile = null;
}

/**
 * Setup drag and drop handlers
 */
function setupDragAndDrop() {
    const dropzone = document.getElementById('uploadDropzone');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => {
            dropzone.classList.add('dragover');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => {
            dropzone.classList.remove('dragover');
        }, false);
    });
    
    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    }, false);
    
    // Click to open file browser
    dropzone.addEventListener('click', (e) => {
        if (e.target.tagName !== 'INPUT') {
            document.getElementById('csvFile').click();
        }
    });
}

/**
 * Handle file selection from input
 */
function handleFileSelect(input) {
    if (input.files && input.files.length > 0) {
        handleFile(input.files[0]);
    }
}

/**
 * Handle the selected file
 */
function handleFile(file) {
    // Validate file type
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showUploadError('Please select a CSV file.');
        return;
    }
    
    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
        showUploadError('File size must be less than 10MB.');
        return;
    }
    
    selectedFile = file;
    
    // Update UI
    document.getElementById('uploadDropzone').style.display = 'none';
    document.getElementById('selectedFile').style.display = 'flex';
    document.getElementById('selectedFileName').textContent = file.name;
    document.getElementById('uploadSubmitBtn').disabled = false;
    document.getElementById('uploadError').style.display = 'none';
}

/**
 * Clear the selected file
 */
function clearSelectedFile() {
    selectedFile = null;
    document.getElementById('csvFile').value = '';
    document.getElementById('selectedFile').style.display = 'none';
    document.getElementById('uploadDropzone').style.display = 'block';
    document.getElementById('uploadSubmitBtn').disabled = true;
}

/**
 * Show upload error message
 */
function showUploadError(message) {
    const errorEl = document.getElementById('uploadError');
    errorEl.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
    errorEl.style.display = 'block';
    document.getElementById('uploadSuccess').style.display = 'none';
}

/**
 * Show upload success message
 */
function showUploadSuccess(message) {
    const successEl = document.getElementById('uploadSuccess');
    successEl.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
    successEl.style.display = 'block';
    document.getElementById('uploadError').style.display = 'none';
}

/**
 * Submit the upload form
 */
async function submitUpload() {
    if (!selectedFile || !currentBrokerId) {
        showUploadError('Please select a file to upload.');
        return;
    }
    
    const submitBtn = document.getElementById('uploadSubmitBtn');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
    
    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('broker', currentBrokerId);
        
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            showUploadSuccess(result.message || 'File uploaded successfully!');
            
            // Show toast
            if (typeof showToast === 'function') {
                showToast('Upload Successful', result.message || 'Your portfolio has been updated.', 'success');
            }
            
            // Reload page after short delay
            setTimeout(() => {
                location.reload();
            }, 1500);
        } else {
            showUploadError(result.error || result.message || 'Upload failed. Please try again.');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    } catch (error) {
        console.error('Upload error:', error);
        showUploadError('An error occurred while uploading. Please try again.');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// Close modal on ESC key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const uploadModal = document.getElementById('uploadModal');
        if (uploadModal && uploadModal.classList.contains('show')) {
            closeUploadModal();
        }
    }
});

// Close modal on overlay click
document.addEventListener('DOMContentLoaded', () => {
    const uploadModal = document.getElementById('uploadModal');
    if (uploadModal) {
        uploadModal.addEventListener('click', (e) => {
            if (e.target === uploadModal) {
                closeUploadModal();
            }
        });
    }
});