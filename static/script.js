// YouTube MP3 Downloader - Working JavaScript
// Version: 3.0

// Global variables
let currentDownloadId = null;
let progressInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log("🎵 YouTube MP3 Downloader loaded!");
    
    // Set current year
    const yearElement = document.getElementById('current-year');
    if (yearElement) {
        yearElement.textContent = new Date().getFullYear();
    }
    
    // Load initial data
    loadHistory();
    refreshFiles();
    getStats();
    
    // Setup event listeners
    setupEventListeners();
    
    // Hide loading screen
    setTimeout(() => {
        const loadingScreen = document.getElementById('loading-screen');
        if (loadingScreen) {
            loadingScreen.style.opacity = '0';
            setTimeout(() => {
                loadingScreen.style.display = 'none';
            }, 500);
        }
    }, 1000);
});

// Setup event listeners
function setupEventListeners() {
    // URL input - Enter key support
    const urlInput = document.getElementById("url");
    if (urlInput) {
        urlInput.addEventListener("keypress", function(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                checkURL();
            }
        });
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(event) {
        // Ctrl/Cmd + Enter to download
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            startDownload();
        }
    });
}

// ========== URL CHECKING ==========
async function checkURL() {
    const url = document.getElementById('url').value.trim();
    const checkBtn = document.getElementById('check-btn');
    
    if (!url) {
        showError('❌ Please enter a YouTube URL first');
        return;
    }
    
    checkBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
    checkBtn.disabled = true;
    
    showOutput(`🔍 Checking URL: ${url.substring(0, 80)}...`);
    
    // Hide previous preview
    const videoPreview = document.getElementById('video-preview');
    if (videoPreview) {
        videoPreview.style.display = 'none';
    }
    
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
            if (preview) {
                const previewTitle = document.getElementById('preview-title');
                const previewDuration = document.getElementById('preview-duration');
                const previewUploader = document.getElementById('preview-uploader');
                const thumbnail = document.getElementById('preview-thumbnail');
                const warning = document.getElementById('preview-warning');
                
                if (previewTitle) previewTitle.textContent = info.title;
                if (previewDuration) previewDuration.innerHTML = `<i class="fas fa-clock"></i> ${info.duration}`;
                if (previewUploader) previewUploader.innerHTML = `<i class="fas fa-user"></i> ${info.uploader}`;
                
                // Show thumbnail
                if (thumbnail) {
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
                }
                
                // Show warning
                if (warning) {
                    if (info.warning) {
                        warning.textContent = info.warning;
                        warning.style.display = 'block';
                    } else {
                        warning.style.display = 'none';
                    }
                }
                
                preview.style.display = 'block';
            }
            
            showSuccess(`✅ ${info.title}`);
            
            // Enable download button
            const downloadBtn = document.getElementById('download-btn');
            if (downloadBtn) {
                downloadBtn.disabled = false;
            }
            
        } else {
            showError(`❌ ${data.message}`);
        }
        
    } catch (error) {
        showError(`❌ Error checking URL: ${error.message}`);
    } finally {
        checkBtn.innerHTML = '<i class="fas fa-info-circle"></i> Check URL';
        checkBtn.disabled = false;
    }
}

// ========== DOWNLOAD FUNCTIONS ==========
async function startDownload() {
    const url = document.getElementById('url').value.trim();
    const quality = document.getElementById('audio-quality') ? document.getElementById('audio-quality').value : '192';
    const downloadBtn = document.getElementById('download-btn');
    
    if (!url) {
        showError('❌ Please paste a YouTube URL first.');
        return;
    }
    
    downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
    downloadBtn.disabled = true;
    
    // Show progress container
    showProgressContainer();
    resetProgress();
    
    showOutput(`📥 Starting download...`);
    
    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ 
                url: url,
                quality: quality
            })
        });
        
        if (!response.ok) {
            throw new Error(`Server error ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Download response:', data);
        
        if (data.status === 'started') {
            showSuccess('✅ Download started successfully!');
            currentDownloadId = data.download_id;
            
            // Start progress monitoring
            startProgressMonitoring(data.download_id);
            
        } else if (data.status === 'error') {
            showError(`❌ ${data.message}`);
            hideProgressContainer();
        } else {
            showError('❌ Unexpected response from server');
            hideProgressContainer();
        }
        
    } catch (error) {
        showError(`❌ Error: ${error.message}`);
        hideProgressContainer();
    } finally {
        downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download MP3';
        downloadBtn.disabled = false;
    }
}

// ========== PROGRESS MONITORING ==========
function startProgressMonitoring(downloadId) {
    console.log(`🚀 Starting progress monitoring: ${downloadId}`);
    
    // Clear any existing interval
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    let attempts = 0;
    const maxAttempts = 300; // 5 minutes timeout
    
    progressInterval = setInterval(async () => {
        attempts++;
        
        try {
            const response = await fetch(`/progress/${downloadId}`);
            
            if (!response.ok) {
                if (response.status === 404 && attempts > 5) {
                    clearInterval(progressInterval);
                    showError('❌ Download session lost. Please try again.');
                    hideProgressContainer();
                    return;
                }
                return; // Try again
            }
            
            const data = await response.json();
            
            if (data.status === 'success') {
                updateProgressUI(data.progress);
                
                // Check if completed
                if (data.progress.status === 'completed' || 
                    (data.progress.percent && parseFloat(data.progress.percent) >= 100)) {
                    
                    clearInterval(progressInterval);
                    showSuccess('✅ Download completed!');
                    
                    // Show download button
                    const downloadLink = document.getElementById('download-file-link');
                    if (downloadLink) {
                        downloadLink.style.display = 'flex';
                        downloadLink.href = `/download-file/${downloadId}`;
                        downloadLink.innerHTML = '<i class="fas fa-file-download"></i> Download MP3';
                    }
                    
                    // Refresh data
                    refreshFiles();
                    getStats();
                    loadHistory();
                    
                    // Clear URL input after 3 seconds
                    setTimeout(() => {
                        const urlInput = document.getElementById('url');
                        const videoPreview = document.getElementById('video-preview');
                        if (urlInput) urlInput.value = '';
                        if (videoPreview) videoPreview.style.display = 'none';
                    }, 3000);
                }
                
                // Check for errors
                if (data.progress.status === 'error') {
                    clearInterval(progressInterval);
                    showError(`❌ ${data.progress.message || 'Download failed'}`);
                    hideProgressContainer();
                }
                
            } else {
                console.error('Progress check failed:', data.message);
            }
            
        } catch (error) {
            console.error('Error checking progress:', error);
        }
        
        // Timeout after max attempts
        if (attempts >= maxAttempts) {
            clearInterval(progressInterval);
            showError('❌ Download timeout. Please try again.');
            hideProgressContainer();
        }
        
    }, 2000); // Check every 2 seconds
}

function updateProgressUI(progress) {
    // Update progress bar
    const percent = parseFloat(progress.percent) || 0;
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
        progressBar.style.width = `${percent}%`;
        const progressText = document.getElementById('progress-text');
        if (progressText) progressText.textContent = `${percent.toFixed(1)}%`;
    }
    
    // Update status
    const statusText = progress.status ? progress.status.replace(/_/g, ' ') : 'Processing...';
    const progressStatus = document.getElementById('progress-status');
    if (progressStatus) progressStatus.textContent = statusText;
    
    // Update details
    if (progress.title) {
        const progressFilename = document.getElementById('progress-filename');
        if (progressFilename) progressFilename.textContent = progress.title.substring(0, 60);
    }
    
    if (progress.speed) {
        const progressSpeed = document.getElementById('progress-speed');
        if (progressSpeed) progressSpeed.textContent = progress.speed;
    }
    
    if (progress.eta) {
        const progressEta = document.getElementById('progress-eta');
        if (progressEta) progressEta.textContent = progress.eta;
    }
}

// ========== FILE MANAGEMENT ==========
async function refreshFiles() {
    try {
        const response = await fetch('/list-files');
        const data = await response.json();
        
        if (data.status === 'success') {
            const filesList = document.getElementById('files-list');
            
            if (!filesList) return;
            
            if (data.files.length === 0) {
                filesList.innerHTML = `
                    <div class="files-placeholder">
                        <i class="fas fa-music"></i>
                        <p>No files downloaded yet</p>
                        <small>Downloaded files will appear here</small>
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
                fileItem.title = `Click to download: ${file.name}`;
                
                const displayName = file.name.length > 40 ? file.name.substring(0, 40) + '...' : file.name;
                
                fileItem.innerHTML = `
                    <div class="file-item-header">
                        <span class="file-item-name">${displayName}</span>
                        <span class="file-item-size">${file.size_mb} MB</span>
                    </div>
                    <div class="file-item-details">
                        <span><i class="fas fa-clock"></i> ${file.modified}</span>
                    </div>
                `;
                
                // Add click to download
                fileItem.addEventListener('click', () => {
                    window.location.href = `/download-file/${encodeURIComponent(file.name)}`;
                });
                
                filesList.appendChild(fileItem);
            });
        }
    } catch (error) {
        console.error('Error loading files:', error);
    }
}

// ========== STATISTICS ==========
async function getStats() {
    try {
        const response = await fetch("/stats");
        const data = await response.json();
        
        if (data.status === "success") {
            // Update display
            const downloadCount = document.getElementById('download-count');
            const totalSize = document.getElementById('total-size');
            const freeSpace = document.getElementById('free-space');
            
            if (downloadCount) downloadCount.textContent = data.total_downloads;
            if (totalSize) totalSize.textContent = data.total_size_mb.toFixed(1) + ' MB';
            if (freeSpace) freeSpace.textContent = data.free_space_gb.toFixed(2) + ' GB';
        }
    } catch (error) {
        console.error('Error getting stats:', error);
    }
}

async function loadHistory() {
    try {
        const response = await fetch('/list-files');
        const data = await response.json();
        
        const historyList = document.getElementById('history-list');
        if (!historyList) return;
        
        if (data.status === 'success' && data.files.length > 0) {
            const recentFiles = data.files.slice(0, 3);
            historyList.innerHTML = '';
            
            recentFiles.forEach(file => {
                const historyItem = document.createElement('div');
                historyItem.className = 'history-item status-success';
                
                const displayName = file.name.length > 40 ? file.name.substring(0, 40) + '...' : file.name;
                
                historyItem.innerHTML = `
                    <div class="history-item-header">
                        <span class="history-item-title">${displayName}</span>
                        <span class="history-item-status">Downloaded</span>
                    </div>
                    <div class="history-item-details">
                        <span><i class="fas fa-clock"></i> ${file.modified}</span>
                        <span><i class="fas fa-database"></i> ${file.size_mb} MB</span>
                    </div>
                `;
                
                historyList.appendChild(historyItem);
            });
        } else {
            historyList.innerHTML = `
                <div class="history-placeholder">
                    <i class="fas fa-history"></i>
                    <p>No download history yet</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// ========== UTILITY FUNCTIONS ==========
function showOutput(message) {
    const output = document.getElementById('output');
    if (!output) return;
    
    output.textContent += `\n${message}`;
    output.scrollTop = output.scrollHeight;
}

function showSuccess(message) {
    showOutput(`✅ ${message}`);
}

function showError(message) {
    showOutput(`❌ ${message}`);
}

function resetProgress() {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
        progressBar.style.width = '0%';
        const progressText = document.getElementById('progress-text');
        if (progressText) progressText.textContent = '0%';
        const progressStatus = document.getElementById('progress-status');
        if (progressStatus) progressStatus.textContent = 'Starting...';
        const progressFilename = document.getElementById('progress-filename');
        if (progressFilename) progressFilename.textContent = 'Waiting for title...';
        const progressSpeed = document.getElementById('progress-speed');
        if (progressSpeed) progressSpeed.textContent = '0 B/s';
        const progressEta = document.getElementById('progress-eta');
        if (progressEta) progressEta.textContent = 'Calculating...';
        const downloadFileLink = document.getElementById('download-file-link');
        if (downloadFileLink) downloadFileLink.style.display = 'none';
    }
}

function showProgressContainer() {
    const container = document.getElementById('progress-container');
    if (container) {
        container.style.display = 'block';
    }
}

function hideProgressContainer() {
    const container = document.getElementById('progress-container');
    if (container) {
        container.style.display = 'none';
    }
}

// ========== MISC ==========
function copyOutput() {
    const output = document.getElementById('output');
    if (!output) return;
    
    navigator.clipboard.writeText(output.textContent)
        .then(() => {
            showSuccess('Output copied to clipboard!');
        })
        .catch(err => {
            showError(`Failed to copy: ${err}`);
        });
}

// Auto-refresh data every 30 seconds
setInterval(() => {
    getStats();
    loadHistory();
    refreshFiles();
}, 30000);