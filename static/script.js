// YouTube MP3 Downloader - Working JavaScript
// Version: 3.0 - Render.com Compatible

// Global variables
let currentDownloadId = null;
let progressInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log("🎵 YouTube MP3 Downloader loaded!");
    
    // Set current year
    document.getElementById('current-year').textContent = new Date().getFullYear();
    
    // Load initial data
    loadHistory();
    refreshFiles();
    getStats();
    
    // Setup event listeners
    setupEventListeners();
    
    // Hide loading screen
    setTimeout(() => {
        document.getElementById('loading-screen').style.opacity = '0';
        setTimeout(() => {
            document.getElementById('loading-screen').style.display = 'none';
        }, 500);
    }, 1000);
});

// Setup event listeners
function setupEventListeners() {
    // URL input - Enter key support
    document.getElementById("url").addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            checkURL();
        }
    });
    
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
            document.getElementById('preview-duration').innerHTML = 
                `<i class="fas fa-clock"></i> ${info.duration}`;
            document.getElementById('preview-uploader').innerHTML = 
                `<i class="fas fa-user"></i> ${info.uploader}`;
            
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
            
            showSuccess(`✅ ${info.title}`);
            
            // Enable download button
            document.getElementById('download-btn').disabled = false;
            
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
    const quality = document.getElementById('audio-quality').value;
    
    if (!url) {
        showError('❌ Please paste a YouTube URL first.');
        return;
    }
    
    const downloadBtn = document.getElementById('download-btn');
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
    const maxAttempts = 300; // 5 minutes timeout for longer videos
    
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
                    downloadLink.style.display = 'flex';
                    downloadLink.href = `/download-file/${downloadId}`;
                    downloadLink.innerHTML = '<i class="fas fa-file-download"></i> Download MP3';
                    
                    // Refresh data
                    refreshFiles();
                    getStats();
                    loadHistory();
                    
                    // Clear URL input after 3 seconds
                    setTimeout(() => {
                        document.getElementById('url').value = '';
                        document.getElementById('video-preview').style.display = 'none';
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
        document.getElementById('progress-text').textContent = `${percent.toFixed(1)}%`;
    }
    
    // Update status
    const statusText = progress.status ? progress.status.replace(/_/g, ' ') : 'Processing...';
    if (document.getElementById('progress-status')) {
        document.getElementById('progress-status').textContent = statusText;
    }
    
    // Update details
    if (progress.title && document.getElementById('progress-filename')) {
        document.getElementById('progress-filename').textContent = 
            progress.title.substring(0, 60);
    }
    
    if (progress.speed && document.getElementById('progress-speed')) {
        document.getElementById('progress-speed').textContent = progress.speed;
    }
    
    if (progress.eta && document.getElementById('progress-eta')) {
        document.getElementById('progress-eta').textContent = progress.eta;
    }
    
    // Update size
    if (progress.downloaded_bytes && progress.total_bytes) {
        const downloaded = formatBytes(progress.downloaded_bytes);
        const total = formatBytes(progress.total_bytes);
        if (document.getElementById('progress-size')) {
            document.getElementById('progress-size').textContent = `${downloaded} / ${total}`;
        }
    } else if (progress.downloaded_bytes) {
        if (document.getElementById('progress-size')) {
            document.getElementById('progress-size').textContent = 
                formatBytes(progress.downloaded_bytes);
        }
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
                
                fileItem.innerHTML = `
                    <div class="file-item-header">
                        <span class="file-item-name">${file.name.substring(0, 40)}${file.name.length > 40 ? '...' : ''}</span>
                        <span class="file-item-size">${file.size_mb} MB</span>
                    </div>
                    <div class="file-item-details">
                        <span><i class="fas fa-clock"></i> ${file.modified}</span>
                    </div>
                `;
                
                // Add click to download
                fileItem.addEventListener('click', () => {
                    window.location.href = `/download-direct/${encodeURIComponent(file.name)}`;
                });
                
                filesList.appendChild(fileItem);
            });
        }
    } catch (error) {
        console.error('Error loading files:', error);
    }
}

async function deleteFile(filename) {
    if (!confirm(`Delete "${filename}"?`)) {
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
            loadHistory();
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError(`Error deleting file: ${error.message}`);
    }
}

// ========== STATISTICS ==========
async function getStats() {
    try {
        const response = await fetch("/stats");
        const data = await response.json();
        
        if (data.status === "success") {
            // Update display
            if (document.getElementById('download-count')) {
                document.getElementById('download-count').textContent = data.total_downloads;
            }
            if (document.getElementById('total-size')) {
                document.getElementById('total-size').textContent = data.total_size_mb.toFixed(1) + ' MB';
            }
            if (document.getElementById('free-space')) {
                document.getElementById('free-space').textContent = data.free_space_gb.toFixed(2) + ' GB';
            }
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
                
                historyItem.innerHTML = `
                    <div class="history-item-header">
                        <span class="history-item-title">${file.name.substring(0, 40)}${file.name.length > 40 ? '...' : ''}</span>
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
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    if (!bytes) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

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

function clearOutput() {
    const output = document.getElementById('output');
    if (output) {
        output.textContent = '🚀 YouTube MP3 Downloader - Ready!\n💡 Paste a YouTube URL to get started...';
    }
}

function resetProgress() {
    if (document.getElementById('progress-bar')) {
        document.getElementById('progress-bar').style.width = '0%';
        document.getElementById('progress-text').textContent = '0%';
        document.getElementById('progress-status').textContent = 'Starting...';
        document.getElementById('progress-filename').textContent = 'Waiting for title...';
        document.getElementById('progress-speed').textContent = '0 B/s';
        document.getElementById('progress-eta').textContent = 'Calculating...';
        document.getElementById('progress-size').textContent = '0 B / 0 B';
        document.getElementById('download-file-link').style.display = 'none';
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

function cancelDownload() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    if (currentDownloadId) {
        showInfo('Download cancelled');
        currentDownloadId = null;
    }
    
    hideProgressContainer();
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

function focusUrlInput() {
    const urlInput = document.getElementById('url');
    if (urlInput) {
        urlInput.focus();
    }
}

// Auto-refresh data every 30 seconds
setInterval(() => {
    getStats();
    loadHistory();
    refreshFiles();
}, 30000);