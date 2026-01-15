// YouTube Video Downloader Frontend

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const urlInput = document.getElementById('url-input');
    const fetchBtn = document.getElementById('fetch-btn');
    const browserSelect = document.getElementById('browser-select');
    const videoInfo = document.getElementById('video-info');
    const downloadOptions = document.getElementById('download-options');
    const progressSection = document.getElementById('progress-section');
    const completeSection = document.getElementById('complete-section');
    const errorSection = document.getElementById('error-section');
    const downloadsList = document.getElementById('downloads-list');

    let currentUrl = '';
    let currentBrowser = 'none';

    // Initialize
    loadDownloads();

    // Event Listeners
    fetchBtn.addEventListener('click', fetchVideoInfo);
    urlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            fetchVideoInfo();
        }
    });

    // Format button clicks
    document.querySelectorAll('.format-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const format = this.dataset.format;
            startDownload(format);
        });
    });

    // New download button
    document.getElementById('new-download-btn').addEventListener('click', resetUI);
    document.getElementById('retry-btn').addEventListener('click', resetUI);

    // Fetch video information
    async function fetchVideoInfo() {
        const url = urlInput.value.trim();
        if (!url) {
            showError('Please enter a YouTube URL');
            return;
        }

        currentUrl = url;
        currentBrowser = browserSelect.value;
        setLoading(true);
        hideAllSections();

        try {
            const response = await fetch('/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, browser: currentBrowser })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch video info');
            }

            displayVideoInfo(data);
        } catch (error) {
            showError(error.message);
        } finally {
            setLoading(false);
        }
    }

    // Display video information
    function displayVideoInfo(info) {
        document.getElementById('video-thumbnail').src = info.thumbnail;
        document.getElementById('video-title').textContent = info.title;
        document.getElementById('video-uploader').textContent = info.uploader;
        document.getElementById('video-views').textContent = formatViews(info.view_count);
        document.getElementById('video-duration').textContent = formatDuration(info.duration);
        document.getElementById('video-description').textContent = info.description || 'No description available';

        videoInfo.classList.remove('hidden');
        downloadOptions.classList.remove('hidden');
    }

    // Start download
    async function startDownload(format) {
        hideAllSections();
        progressSection.classList.remove('hidden');

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: currentUrl, format, browser: currentBrowser })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to start download');
            }

            // Poll for progress
            pollProgress(data.download_id);
        } catch (error) {
            showError(error.message);
        }
    }

    // Poll download progress
    async function pollProgress(downloadId) {
        const progressFill = document.getElementById('progress-fill');
        const progressPercent = document.getElementById('progress-percent');
        const progressStatus = document.getElementById('progress-status');
        const progressDetails = document.getElementById('progress-details');

        const poll = async () => {
            try {
                const response = await fetch(`/progress/${downloadId}`);
                const data = await response.json();

                if (data.status === 'downloading') {
                    progressFill.style.width = `${data.percent}%`;
                    progressPercent.textContent = `${data.percent}%`;
                    progressStatus.textContent = 'Downloading...';

                    if (data.speed) {
                        const speed = formatBytes(data.speed) + '/s';
                        const eta = data.eta ? `ETA: ${formatDuration(data.eta)}` : '';
                        progressDetails.textContent = `${speed} ${eta}`;
                    }

                    setTimeout(poll, 500);
                } else if (data.status === 'processing') {
                    progressFill.style.width = '100%';
                    progressPercent.textContent = '100%';
                    progressStatus.textContent = 'Processing...';
                    progressDetails.textContent = 'Converting and finalizing...';
                    setTimeout(poll, 500);
                } else if (data.status === 'complete') {
                    showComplete(data.filename);
                    loadDownloads();
                } else if (data.status === 'error') {
                    showError(data.error || 'Download failed');
                } else if (data.status === 'starting') {
                    progressStatus.textContent = 'Starting download...';
                    setTimeout(poll, 500);
                } else {
                    setTimeout(poll, 500);
                }
            } catch (error) {
                showError('Lost connection to server');
            }
        };

        poll();
    }

    // Show completion
    function showComplete(filename) {
        hideAllSections();
        completeSection.classList.remove('hidden');
        document.getElementById('download-link').href = `/file/${encodeURIComponent(filename)}`;
    }

    // Show error
    function showError(message) {
        hideAllSections();
        errorSection.classList.remove('hidden');
        document.getElementById('error-message').textContent = message;
    }

    // Load downloads list
    async function loadDownloads() {
        try {
            const response = await fetch('/downloads');
            const data = await response.json();

            if (data.files && data.files.length > 0) {
                downloadsList.innerHTML = data.files.slice(0, 10).map(file => `
                    <div class="download-item">
                        <div class="download-item-info">
                            <div class="download-item-name" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</div>
                            <div class="download-item-size">${formatBytes(file.size)}</div>
                        </div>
                        <a href="/file/${encodeURIComponent(file.filename)}" class="download-item-link">Download</a>
                    </div>
                `).join('');
            } else {
                downloadsList.innerHTML = '<p class="no-downloads">No downloads yet</p>';
            }
        } catch (error) {
            console.error('Failed to load downloads:', error);
        }
    }

    // Reset UI
    function resetUI() {
        urlInput.value = '';
        currentUrl = '';
        hideAllSections();
        document.getElementById('progress-fill').style.width = '0%';
        document.getElementById('progress-percent').textContent = '0%';
        document.getElementById('progress-status').textContent = 'Starting download...';
        document.getElementById('progress-details').textContent = '';
    }

    // Hide all dynamic sections
    function hideAllSections() {
        videoInfo.classList.add('hidden');
        downloadOptions.classList.add('hidden');
        progressSection.classList.add('hidden');
        completeSection.classList.add('hidden');
        errorSection.classList.add('hidden');
    }

    // Set loading state
    function setLoading(loading) {
        fetchBtn.disabled = loading;
        const btnText = fetchBtn.querySelector('.btn-text');
        const btnLoading = fetchBtn.querySelector('.btn-loading');

        if (loading) {
            btnText.classList.add('hidden');
            btnLoading.classList.remove('hidden');
        } else {
            btnText.classList.remove('hidden');
            btnLoading.classList.add('hidden');
        }
    }

    // Utility: Format duration
    function formatDuration(seconds) {
        if (!seconds) return '0:00';

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    // Utility: Format view count
    function formatViews(views) {
        if (!views) return '0 views';

        if (views >= 1000000000) {
            return (views / 1000000000).toFixed(1) + 'B views';
        }
        if (views >= 1000000) {
            return (views / 1000000).toFixed(1) + 'M views';
        }
        if (views >= 1000) {
            return (views / 1000).toFixed(1) + 'K views';
        }
        return views + ' views';
    }

    // Utility: Format bytes
    function formatBytes(bytes) {
        if (!bytes) return '0 B';

        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
    }

    // Utility: Escape HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
