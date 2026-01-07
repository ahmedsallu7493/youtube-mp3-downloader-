// Enhanced YouTube MP3 Downloader with Batch Download and History Features

// Global variables
let currentDownloadId = null;
let progressInterval = null;
let isDownloading = false;
let isCheckingURL = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log("YouTube MP3 Downloader - Enhanced Edition loaded!");
    
    // Set current year
    document.getElementById('current-year').textContent = new Date().getFullYear();
    
    // Load initial data
    loadHistory();
    refreshFiles();
    getStats();
    
    // Auto-focus input
    setTimeout(() => {
        document.getElementById('url').focus();
    }, 500);
    
    // Hide loading screen
    setTimeout(() => {
        document.getElementById('loading-screen').style.opacity = '0';
        setTimeout(() => {
            document.getElementById('loading-screen').style.display = 'none';
        }, 500);
    }, 1000);
});

// ========== URL VALIDATION & PREVIEW ==========

// Check URL and get video info
async function checkURL() {
    const url = document.getElementById('url').value.trim();
    const checkBtn = document.getElementById('check-btn');
    
    if (!url) {
        showError('Please enter a YouTube URL first');
        return;
    }
    
    if (isCheckingURL) return;
    
    isCheckingURL = true;
    checkBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
    checkBtn.disabled = true;
    
    const output = document.getElementById('output');
    output.textContent += `\n🔍 Checking URL: ${url.substring(0, 80)}...`;
    output.scrollTop = output.scrollHeight;
    
    // Hide previous preview
    document.getElementById('video-preview').style.display = 'none';
    
    try {
        const response = await fetch('/check-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            const info = data.info;
            
            // Show video preview
            const preview = document.getElementById('video-preview');
            document.getElementById('preview-title').textContent = info.title;
            document.getElementById('preview-duration').innerHTML = `<i class="fas fa-clock"></i> ${info.duration}`;
            document.getElementById('preview-uploader').innerHTML = `<i class="fas fa-user"></i> ${info.uploader}`;
            
            // Show thumbnail if available
            const thumbnail = document.getElementById('preview-thumbnail');
            thumbnail.innerHTML = '';
            if (info.thumbnail) {
                const img = document.createElement('img');
                img.src = info.thumbnail;
                img.alt = info.title;
                img.style.width = '100%';
                img.style.height = '100%';
                img.style.objectFit = 'cover';
                thumbnail.appendChild(img);
            } else {
                thumbnail.innerHTML = '<i class="fab fa-youtube"></i>';
            }
            
            // Show warning if any
            const warning = document.getElementById('preview-warning');
            if (info.warning) {
                warning.textContent = info.warning;
                warning.style.display = 'block';
            } else {
                warning.style.display = 'none';
            }
            
            preview.style.display = 'block';
            
            showSuccess(`✅ Video info loaded: "${info.title}" (${info.duration})`);
            
            // Enable download button
            document.getElementById('download-btn').disabled = false;
            
        } else {
            showError(`❌ ${data.message}`);
            document.getElementById('video-preview').style.display = 'none';
        }
        
    } catch (error) {
        showError(`❌ Error checking URL: ${error.message}`);
        document.getElementById('video-preview').style.display = 'none';
    } finally {
        isCheckingURL = false;
        checkBtn.innerHTML = '<i class="fas fa-info-circle"></i> Check URL';
        checkBtn.disabled = false;
    }
}

// ========== DOWNLOAD FUNCTIONS ==========

// Start single download
async function startDownload() {
    if (isDownloading) {
        showError('A download is already in progress');
        return;
    }
    
    const url = document.getElementById('url').value.trim();
    const quality = document.getElementById('audio-quality').value;
    const downloadBtn = document.getElementById('download-btn');
    
    // Validation
    if (!url) {
        showError('❌ Please paste a YouTube URL first.');
        return;
    }
    
    // Set loading state
    isDownloading = true;
    downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
    downloadBtn.disabled = true;
    
    // Show progress container
    document.getElementById('progress-container').style.display = 'block';
    document.getElementById('download-file-link').style.display = 'none';
    
    // Reset progress bar
    resetProgress();
    
    // Show initial message
    const output = document.getElementById('output');
    output.textContent += `\n📥 Starting download...`;
    output.scrollTop = output.scrollHeight;
    
    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                url: url,
                quality: quality
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'started') {
            currentDownloadId = data.download_id;
            
            // Start progress monitoring
            startProgressMonitoring(data.download_id, data.download_url);
            
            showSuccess('Download started successfully!');
        } else if (data.status === 'error') {
            showError(data.message);
            resetDownloadButton();
            hideProgressContainer();
            
            // If queue position is provided, show it
            if (data.queue_position) {
                showInfo(`You are position ${data.queue_position} in the queue`);
            }
        } else {
            showError('Unexpected response from server');
            resetDownloadButton();
            hideProgressContainer();
        }
        
    } catch (error) {
        showError(`Error starting download: ${error.message}`);
        resetDownloadButton();
        hideProgressContainer();
    }
}

// Start batch download
async function startBatchDownload() {
    const urlsText = document.getElementById('batch-urls').value.trim();
    
    if (!urlsText) {
        showError('Please enter at least one URL');
        return;
    }
    
    // Parse URLs
    const urls = urlsText.split('\n')
        .map(url => url.trim())
        .filter(url => url.length > 0);
    
    if (urls.length === 0) {
        showError('No valid URLs found');
        return;
    }
    
    // Close modal
    closeBatchModal();
    
    const quality = document.getElementById('audio-quality').value;
    const output = document.getElementById('output');
    
    output.textContent += `\n📦 Starting batch download of ${urls.length} video(s)...`;
    output.scrollTop = output.scrollHeight;
    
    try {
        const response = await fetch('/batch-download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                urls: urls,
                quality: quality
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showSuccess(`Batch download started: ${data.message}`);
            
            // Show progress for first download if started
            if (data.results && data.results.length > 0) {
                const firstResult = data.results.find(r => r.status === 'queued');
                if (firstResult) {
                    currentDownloadId = firstResult.download_id;
                    showProgressContainer();
                    startProgressMonitoring(firstResult.download_id, null);
                }
            }
            
            // Log all results
            data.results.forEach(result => {
                if (result.status === 'error') {
                    output.textContent += `\n❌ ${result.url}: ${result.message}`;
                } else {
                    output.textContent += `\n✅ ${result.url}: Queued`;
                }
            });
            
            output.scrollTop = output.scrollHeight;
            
        } else {
            showError(data.message);
        }
        
    } catch (error) {
        showError(`Error starting batch download: ${error.message}`);
    }
}

// Start progress monitoring
function startProgressMonitoring(downloadId, downloadUrl) {
    // Clear any existing interval
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    
    // Update progress every second
    progressInterval = setInterval(async () => {
        try {
            const response = await fetch(`/progress/${downloadId}`);
            const data = await response.json();
            
            if (data.status === 'success') {
                const progress = data.progress;
                
                // Update progress bar
                const percent = parseInt(progress.percent) || 0;
                document.getElementById('progress-bar').style.width = `${percent}%`;
                document.getElementById('progress-text').textContent = `${percent}%`;
                
                // Update status
                let statusText = 'Starting...';
                if (progress.status === 'converting') {
                    statusText = 'Converting to MP3...';
                } else if (progress.status === 'downloading') {
                    statusText = 'Downloading...';
                } else if (progress.status === 'completed') {
                    statusText = 'Completed!';
                } else if (progress.status) {
                    statusText = progress.status;
                }
                document.getElementById('progress-status').textContent = statusText;
                
                // Update details
                if (progress.title) {
                    document.getElementById('progress-filename').textContent = progress.title;
                }
                document.getElementById('progress-speed').textContent = progress.speed || '0 B/s';
                document.getElementById('progress-eta').textContent = progress.eta || 'Calculating...';
                
                // Update size
                const downloaded = formatBytes(progress.downloaded_bytes || 0);
                const total = formatBytes(progress.total_bytes || 0);
                document.getElementById('progress-size').textContent = `${downloaded} / ${total}`;
                
                // Handle completion
                if (progress.status === 'completed' || (progress.result && progress.result.status === 'success')) {
                    clearInterval(progressInterval);
                    progressInterval = null;
                    
                    // Show download button
                    const downloadLink = document.getElementById('download-file-link');
                    if (downloadUrl) {
                        downloadLink.href = downloadUrl;
                        downloadLink.style.display = 'flex';
                        downloadLink.innerHTML = '<i class="fas fa-file-download"></i> Download File';
                    }
                    
                    // Update button text
                    resetDownloadButton();
                    
                    // Clear URL input
                    document.getElementById('url').value = '';
                    
                    // Update output
                    const result = progress.result || { message: 'Download completed!' };
                    showSuccess(result.message);
                    
                    // Auto-click download link after 1 second
                    setTimeout(() => {
                        if (downloadLink.href && downloadLink.href !== '#') {
                            downloadLink.click();
                        }
                    }, 1000);
                    
                    // Refresh data
                    loadHistory();
                    refreshFiles();
                    getStats();
                    
                    // Clear download ID after 30 seconds
                    setTimeout(() => {
                        currentDownloadId = null;
                    }, 30000);
                }
                
                // Handle error
                if (progress.status === 'error') {
                    clearInterval(progressInterval);
                    progressInterval = null;
                    showError(progress.message || 'Download failed');
                    resetDownloadButton();
                    currentDownloadId = null;
                }
            } else if (data.status === 'error') {
                // Download not found or error
                clearInterval(progressInterval);
                progressInterval = null;
                showError(data.message || 'Progress check failed');
                resetDownloadButton();
                currentDownloadId = null;
            }
        } catch (error) {
            console.error('Error checking progress:', error);
            // Don't stop on network errors
        }
    }, 1000);
}

// Cancel download
function cancelDownload() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    if (currentDownloadId) {
        showError('Download cancelled');
        currentDownloadId = null;
    }
    
    resetDownloadButton();
    hideProgressContainer();
}

// Reset download button
function resetDownloadButton() {
    isDownloading = false;
    const downloadBtn = document.getElementById('download-btn');
    downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download MP3';
    downloadBtn.disabled = false;
}

// Reset progress display
function resetProgress() {
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-text').textContent = '0%';
    document.getElementById('progress-status').textContent = 'Starting...';
    document.getElementById('progress-filename').textContent = 'Waiting for title...';
    document.getElementById('progress-speed').textContent = '0 B/s';
    document.getElementById('progress-eta').textContent = 'Calculating...';
    document.getElementById('progress-size').textContent = '0 B / 0 B';
}

// Show progress container
function showProgressContainer() {
    document.getElementById('progress-container').style.display = 'block';
}

// Hide progress container
function hideProgressContainer() {
    document.getElementById('progress-container').style.display = 'none';
}

// ========== HISTORY FUNCTIONS ==========

// Load download history
async function loadHistory() {
    try {
        const response = await fetch('/get-history');
        const data = await response.json();
        
        if (data.status === 'success') {
            const historyList = document.getElementById('history-list');
            
            if (data.history.length === 0) {
                historyList.innerHTML = `
                    <div class="history-placeholder">
                        <i class="fas fa-history"></i>
                        <p>No download history yet</p>
                    </div>
                `;
                return;
            }
            
            // Display last 3 items
            const recentHistory = data.history.slice(0, 3);
            historyList.innerHTML = '';
            
            recentHistory.forEach(item => {
                const historyItem = document.createElement('div');
                historyItem.className = `history-item status-${item.status}`;
                
                const timestamp = new Date(item.timestamp).toLocaleString();
                const size = item.size_mb > 0 ? `${item.size_mb.toFixed(1)} MB` : 'N/A';
                
                historyItem.innerHTML = `
                    <div class="history-item-header">
                        <span class="history-item-title">${item.title || 'Unknown'}</span>
                        <span class="history-item-status">${item.status}</span>
                    </div>
                    <div class="history-item-details">
                        <span><i class="fas fa-clock"></i> ${timestamp}</span>
                        <span><i class="fas fa-database"></i> ${size}</span>
                    </div>
                `;
                
                historyList.appendChild(historyItem);
            });
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Show full history modal
async function showHistory() {
    try {
        const response = await fetch('/get-history');
        const data = await response.json();
        
        if (data.status === 'success') {
            const historyContainer = document.getElementById('history-container');
            
            if (data.history.length === 0) {
                historyContainer.innerHTML = `
                    <div class="history-placeholder">
                        <i class="fas fa-history"></i>
                        <p>No download history yet</p>
                    </div>
                `;
            } else {
                historyContainer.innerHTML = '';
                
                data.history.forEach(item => {
                    const historyItem = document.createElement('div');
                    historyItem.className = `history-item status-${item.status}`;
                    
                    const timestamp = new Date(item.timestamp).toLocaleString();
                    const size = item.size_mb > 0 ? `${item.size_mb.toFixed(1)} MB` : 'N/A';
                    const urlPreview = item.url ? item.url.substring(0, 50) + '...' : 'N/A';
                    
                    historyItem.innerHTML = `
                        <div class="history-item-header">
                            <span class="history-item-title">${item.title || 'Unknown'}</span>
                            <span class="history-item-status">${item.status}</span>
                        </div>
                        <div class="history-item-details">
                            <span><i class="fas fa-clock"></i> ${timestamp}</span>
                            <span><i class="fas fa-database"></i> ${size}</span>
                            <span><i class="fas fa-link"></i> ${urlPreview}</span>
                        </div>
                    `;
                    
                    historyContainer.appendChild(historyItem);
                });
            }
            
            document.getElementById('history-modal').style.display = 'flex';
        }
    } catch (error) {
        console.error('Error loading history:', error);
        showError(`Error loading history: ${error.message}`);
    }
}

// Clear history
async function clearHistory() {
    if (!confirm('Are you sure you want to clear all download history?')) {
        return;
    }
    
    try {
        const response = await fetch('/clear-history', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showSuccess('History cleared successfully');
            loadHistory();
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError(`Error clearing history: ${error.message}`);
    }
}

// ========== FILE MANAGEMENT ==========

// Refresh files list
async function refreshFiles() {
    try {
        const response = await fetch('/list-files');
        const data = await response.json();
        
        if (data.status === 'success') {
            const filesList = document.getElementById('files-list');
            
            if (data.files.length === 0) {
                filesList.innerHTML = `
                    <div class="files-placeholder">
                        <i class="fas fa-music"></i>
                        <p>No files downloaded yet</p>
                    </div>
                `;
                return;
            }
            
            // Display last 3 files
            const recentFiles = data.files.slice(0, 3);
            filesList.innerHTML = '';
            
            recentFiles.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                
                fileItem.innerHTML = `
                    <div class="file-item-header">
                        <span class="file-item-name">${file.name}</span>
                        <span class="file-item-size">${file.size_mb} MB</span>
                    </div>
                    <div class="file-item-details">
                        <span><i class="fas fa-clock"></i> ${file.modified}</span>
                    </div>
                `;
                
                // Add click to download
                fileItem.addEventListener('click', () => {
                    window.open(`/download-file?path=${encodeURIComponent(file.path)}`, '_blank');
                });
                
                filesList.appendChild(fileItem);
            });
        }
    } catch (error) {
        console.error('Error loading files:', error);
    }
}

// Show files modal
async function showFiles() {
    try {
        const response = await fetch('/list-files');
        const data = await response.json();
        
        if (data.status === 'success') {
            const filesContainer = document.getElementById('files-container');
            
            if (data.files.length === 0) {
                filesContainer.innerHTML = `
                    <div class="files-placeholder">
                        <i class="fas fa-music"></i>
                        <p>No files downloaded yet</p>
                    </div>
                `;
            } else {
                filesContainer.innerHTML = '';
                
                data.files.forEach(file => {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'file-item';
                    
                    fileItem.innerHTML = `
                        <div class="file-item-header">
                            <span class="file-item-name">${file.name}</span>
                            <span class="file-item-size">${file.size_mb} MB</span>
                        </div>
                        <div class="file-item-details">
                            <span><i class="fas fa-clock"></i> ${file.modified}</span>
                            <button class="btn-delete-file" onclick="deleteFile('${file.name}')" title="Delete file">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        </div>
                    `;
                    
                    // Add click to download
                    fileItem.addEventListener('click', (e) => {
                        if (!e.target.closest('.btn-delete-file')) {
                            window.open(`/download-file?path=${encodeURIComponent(file.path)}`, '_blank');
                        }
                    });
                    
                    filesContainer.appendChild(fileItem);
                });
            }
            
            document.getElementById('files-modal').style.display = 'flex';
        }
    } catch (error) {
        console.error('Error loading files:', error);
        showError(`Error loading files: ${error.message}`);
    }
}

// Delete file
async function deleteFile(filename) {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) {
        return;
    }
    
    try {
        const response = await fetch('/delete-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showSuccess(`Deleted: ${filename}`);
            refreshFiles();
            getStats();
            
            // Close files modal if open
            closeFilesModal();
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError(`Error deleting file: ${error.message}`);
    }
}

// ========== SYSTEM FUNCTIONS ==========

// Get storage statistics
async function getStats() {
    try {
        const response = await fetch("/stats");
        const data = await response.json();
        
        if (data.status === "success") {
            // Update display
            document.getElementById('download-count').textContent = data.stats.total_downloads;
            document.getElementById('total-size').textContent = data.stats.total_size_mb.toFixed(1) + ' MB';
            document.getElementById('free-space').textContent = data.free_space_gb.toFixed(2) + ' GB';
            
            return data;
        }
    } catch (error) {
        console.error('Error getting stats:', error);
    }
}

// List all files
async function listFiles() {
    const output = document.getElementById('output');
    
    output.textContent += "\n📁 Listing downloaded files...";
    output.scrollTop = output.scrollHeight;
    
    try {
        const response = await fetch("/list-files");
        const data = await response.json();
        
        if (data.status === "success") {
            output.textContent += `\n📁 Downloaded Files (${data.count}):`;
            
            if (data.files.length > 0) {
                data.files.forEach(file => {
                    output.textContent += `\n   • ${file.name} (${file.size_mb} MB) - ${file.modified}`;
                });
                output.textContent += `\n\n   Total Size: ${data.total_size_mb} MB`;
            } else {
                output.textContent += `\n   No files downloaded yet.`;
            }
            
            output.style.color = "#2ed573";
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError(`Failed to list files: ${error.message}`);
    }
    
    output.scrollTop = output.scrollHeight;
}

// Cleanup temporary files
async function cleanupFiles() {
    const output = document.getElementById('output');
    
    output.textContent += "\n🧹 Cleaning up temporary files...";
    output.scrollTop = output.scrollHeight;
    
    try {
        const response = await fetch("/cleanup", {
            method: "POST"
        });
        
        const data = await response.json();
        
        if (data.status === "success") {
            output.textContent += `\n✅ ${data.message}`;
            output.style.color = "#2ed573";
            
            // Refresh stats
            getStats();
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError(`Cleanup failed: ${error.message}`);
    }
    
    output.scrollTop = output.scrollHeight;
}

// Open downloads folder
function openDownloads() {
    showInfo('Opening downloads folder...');
    // This would need server-side implementation for actual folder opening
}

// ========== MODAL FUNCTIONS ==========

// Show batch download modal
function showBatchModal() {
    document.getElementById('batch-urls').value = '';
    document.getElementById('batch-modal').style.display = 'flex';
    document.getElementById('batch-urls').focus();
}

// Close batch modal
function closeBatchModal() {
    document.getElementById('batch-modal').style.display = 'none';
}

// Close history modal
function closeHistoryModal() {
    document.getElementById('history-modal').style.display = 'none';
}

// Close files modal
function closeFilesModal() {
    document.getElementById('files-modal').style.display = 'none';
}

// Close modal when clicking outside
document.addEventListener('click', function(event) {
    const modals = ['batch-modal', 'history-modal', 'files-modal'];
    modals.forEach(modalId => {
        const modal = document.getElementById(modalId);
        if (modal && event.target === modal) {
            modal.style.display = 'none';
        }
    });
});

// Close modal with Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeBatchModal();
        closeHistoryModal();
        closeFilesModal();
    }
});

// ========== UTILITY FUNCTIONS ==========

// Format bytes to human readable format
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    if (bytes === undefined || bytes === null) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Show success message
function showSuccess(message) {
    const output = document.getElementById('output');
    output.textContent += `\n✅ ${message}`;
    output.scrollTop = output.scrollHeight;
}

// Show error message
function showError(message) {
    const output = document.getElementById('output');
    output.textContent += `\n❌ ${message}`;
    output.scrollTop = output.scrollHeight;
}

// Show info message
function showInfo(message) {
    const output = document.getElementById('output');
    output.textContent += `\nℹ️ ${message}`;
    output.scrollTop = output.scrollHeight;
}

// Clear output
function clearOutput() {
    document.getElementById('output').textContent = '🚀 YouTube MP3 Downloader - Enhanced Edition\n\n💡 Enter a YouTube URL to get started.';
}

// Clear input
function clearInput() {
    document.getElementById('url').value = '';
    document.getElementById('video-preview').style.display = 'none';
}

// Copy output to clipboard
function copyOutput() {
    const output = document.getElementById('output');
    navigator.clipboard.writeText(output.textContent)
        .then(() => {
            showSuccess('Output copied to clipboard!');
        })
        .catch(err => {
            showError(`Failed to copy: ${err}`);
        });
}

// Focus URL input
function focusUrlInput() {
    document.getElementById('url').focus();
}

// ========== EVENT LISTENERS ==========

// URL input - Enter key support
document.getElementById("url").addEventListener("keypress", function(event) {
    if (event.key === "Enter" && !isDownloading) {
        event.preventDefault();
        checkURL();
    }
});

// URL input - Focus effect
document.getElementById("url").addEventListener("focus", function() {
    const inputGroup = document.querySelector('.input-group');
    inputGroup.style.borderColor = '#70a1ff';
    inputGroup.style.boxShadow = '0 0 0 4px rgba(112, 161, 255, 0.15)';
});

// URL input - Blur effect
document.getElementById("url").addEventListener("blur", function() {
    const inputGroup = document.querySelector('.input-group');
    if (!this.value.trim()) {
        inputGroup.style.borderColor = 'rgba(112, 161, 255, 0.2)';
        inputGroup.style.boxShadow = 'none';
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // Ctrl/Cmd + Enter to start download
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !isDownloading) {
        event.preventDefault();
        startDownload();
    }
    
    // Ctrl/Cmd + K to clear output
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        clearOutput();
    }
    
    // Ctrl/Cmd + B for batch download
    if ((event.ctrlKey || event.metaKey) && event.key === 'b') {
        event.preventDefault();
        showBatchModal();
    }
});

// Handle mobile navigation visibility
function handleMobileNav() {
    const mobileNav = document.querySelector('.mobile-nav');
    if (window.innerWidth <= 768) {
        mobileNav.style.display = 'flex';
    } else {
        mobileNav.style.display = 'none';
    }
}

// Initial call
handleMobileNav();
window.addEventListener('resize', handleMobileNav);

// Auto-refresh data every 30 seconds
setInterval(() => {
    getStats();
    loadHistory();
    refreshFiles();
}, 30000);

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (progressInterval) {
        clearInterval(progressInterval);
    }
});

// Initialize tooltips
function initTooltips() {
    const tooltips = document.querySelectorAll('[title]');
    tooltips.forEach(element => {
        element.addEventListener('mouseenter', function() {
            // Could add custom tooltip implementation here
        });
    });
}

// Call initialization
setTimeout(initTooltips, 1000);