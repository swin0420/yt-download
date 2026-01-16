"""
YouTube Video Downloader
A Flask app for downloading YouTube videos using yt-dlp
"""

import os
import uuid
import time
import logging
import threading
from functools import wraps
from collections import defaultdict
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, abort, Response
from werkzeug.utils import secure_filename

try:
    import yt_dlp
except ImportError:
    print("Please install yt-dlp: pip install yt-dlp")
    raise

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# AUTHENTICATION
# =============================================================================
# Set these environment variables, or change the defaults below
AUTH_USERNAME = os.environ.get('YT_AUTH_USER', 'admin')
AUTH_PASSWORD = os.environ.get('YT_AUTH_PASS', 'changeme')
AUTH_ENABLED = os.environ.get('YT_AUTH_ENABLED', 'true').lower() in ('1', 'true', 'yes')

def check_auth(username, password):
    """Check if username/password combination is valid"""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

def authenticate():
    """Send 401 response that enables basic auth"""
    return Response(
        'Authentication required. Please log in.',
        401,
        {'WWW-Authenticate': 'Basic realm="YouTube Downloader"'}
    )

def requires_auth(f):
    """Decorator to require authentication on routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not AUTH_ENABLED:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# =============================================================================
# RATE LIMITING
# =============================================================================
# Download rate limit: 10 downloads per 10 minutes per IP
DOWNLOAD_RATE_LIMIT = 10  # max downloads
DOWNLOAD_RATE_WINDOW = 600  # 10 minutes in seconds
download_requests = defaultdict(list)

# Update cooldown: 5 minutes between updates (global)
UPDATE_COOLDOWN = 300  # 5 minutes in seconds
last_update_time = 0

def check_download_rate_limit(ip):
    """
    Check if IP is within rate limit for downloads.
    Returns (allowed, remaining, reset_seconds)
    """
    now = time.time()
    # Clean old entries
    download_requests[ip] = [t for t in download_requests[ip] if now - t < DOWNLOAD_RATE_WINDOW]

    remaining = DOWNLOAD_RATE_LIMIT - len(download_requests[ip])

    if remaining <= 0:
        # Calculate when the oldest request will expire
        oldest = min(download_requests[ip])
        reset_seconds = int(DOWNLOAD_RATE_WINDOW - (now - oldest))
        return False, 0, reset_seconds

    # Record this request
    download_requests[ip].append(now)
    return True, remaining - 1, 0

# Configuration
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def get_ffmpeg_location():
    """Auto-detect ffmpeg location"""
    import shutil
    # Check common locations
    locations = [
        shutil.which('ffmpeg'),  # System PATH
        '/opt/homebrew/bin/ffmpeg',  # macOS Apple Silicon (Homebrew)
        '/usr/local/bin/ffmpeg',  # macOS Intel (Homebrew)
        '/usr/bin/ffmpeg',  # Linux
        'C:\\ffmpeg\\bin\\ffmpeg.exe',  # Windows
    ]
    for loc in locations:
        if loc and os.path.exists(loc):
            return os.path.dirname(loc)
    return None  # Let yt-dlp try to find it

FFMPEG_LOCATION = get_ffmpeg_location()

# Track download progress (with timestamps for cleanup)
download_progress = {}

def cleanup_old_progress(max_age_seconds=3600):
    """Remove progress entries older than max_age_seconds"""
    now = time.time()
    to_delete = [
        k for k, v in download_progress.items()
        if v.get('timestamp', 0) < now - max_age_seconds
    ]
    for k in to_delete:
        del download_progress[k]


def get_video_info(url, browser='none'):
    """Get video information without downloading"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ffmpeg_location': FFMPEG_LOCATION,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
    }

    # YouTube-specific settings
    if 'youtube.com' in url or 'youtu.be' in url:
        ydl_opts['extractor_args'] = {'youtube': {'player_client': ['tv', 'web_safari']}}
        # Enable Node.js runtime for signature solving
        ydl_opts['js_runtimes'] = {'node': {'path': '/opt/homebrew/bin/node'}}

    # Add browser cookies if not 'none'
    if browser and browser != 'none':
        ydl_opts['cookiesfrombrowser'] = (browser,)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        # Get available formats
        formats = []
        if 'formats' in info:
            for f in info['formats']:
                format_info = {
                    'format_id': f.get('format_id', ''),
                    'ext': f.get('ext', ''),
                    'resolution': f.get('resolution', 'audio only'),
                    'filesize': f.get('filesize') or f.get('filesize_approx'),
                    'vcodec': f.get('vcodec', 'none'),
                    'acodec': f.get('acodec', 'none'),
                    'fps': f.get('fps'),
                    'tbr': f.get('tbr'),
                }

                # Only include formats with video or standalone audio
                if f.get('vcodec') != 'none' or (f.get('acodec') != 'none' and f.get('vcodec') == 'none'):
                    formats.append(format_info)

        return {
            'title': info.get('title', 'Unknown'),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Unknown'),
            'view_count': info.get('view_count', 0),
            'description': info.get('description', '')[:500] if info.get('description') else '',
            'formats': formats,
        }


def progress_hook(d, download_id):
    """Track download progress"""
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded = d.get('downloaded_bytes', 0)

        if total > 0:
            percent = (downloaded / total) * 100
        else:
            percent = 0

        download_progress[download_id] = {
            'status': 'downloading',
            'percent': round(percent, 1),
            'speed': d.get('speed', 0),
            'eta': d.get('eta', 0),
            'timestamp': time.time(),
        }
    elif d['status'] == 'finished':
        download_progress[download_id] = {
            'status': 'processing',
            'percent': 100,
            'timestamp': time.time(),
        }


def download_video(url, format_choice, download_id, browser='none'):
    """Download video in background thread"""
    try:
        # Set output template
        output_template = os.path.join(DOWNLOAD_FOLDER, f'{download_id}_%(title)s.%(ext)s')

        ydl_opts = {
            'outtmpl': output_template,
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': FFMPEG_LOCATION,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }

        # YouTube-specific settings
        if 'youtube.com' in url or 'youtu.be' in url:
            ydl_opts['extractor_args'] = {'youtube': {'player_client': ['tv', 'web_safari']}}
            # Enable Node.js runtime for signature solving
            ydl_opts['js_runtimes'] = {'node': {'path': '/opt/homebrew/bin/node'}}

        # Add browser cookies if not 'none'
        if browser and browser != 'none':
            ydl_opts['cookiesfrombrowser'] = (browser,)

        # Configure format based on choice
        if format_choice == 'best':
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        elif format_choice == 'audio':
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif format_choice == 'flac':
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'flac',
            }]
        elif format_choice == '1080p':
            ydl_opts['format'] = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best'
        elif format_choice == '720p':
            ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best'
        elif format_choice == '480p':
            ydl_opts['format'] = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]/best'
        elif format_choice == '360p':
            ydl_opts['format'] = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]/best'
        else:
            ydl_opts['format'] = format_choice

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Handle audio extraction filename change
            if format_choice == 'audio':
                filename = os.path.splitext(filename)[0] + '.mp3'
            elif format_choice == 'flac':
                filename = os.path.splitext(filename)[0] + '.flac'

            # Get just the filename without path
            basename = os.path.basename(filename)

            download_progress[download_id] = {
                'status': 'complete',
                'percent': 100,
                'filename': basename,
                'timestamp': time.time(),
            }

    except Exception as e:
        download_progress[download_id] = {
            'status': 'error',
            'error': str(e),
            'timestamp': time.time(),
        }


@app.route("/")
@requires_auth
def index():
    """Serve the main webpage"""
    return render_template("youtube.html")


@app.route("/info", methods=["POST"])
@requires_auth
def video_info():
    """Get video information"""
    data = request.get_json()
    url = data.get("url", "").strip()
    browser = data.get("browser", "none")

    if not url:
        return jsonify({"error": "Please enter a video URL"}), 400

    # Basic URL validation - accept any http/https URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        info = get_video_info(url, browser)
        return jsonify(info)
    except Exception as e:
        # Log full error for debugging, return sanitized message to user
        logger.error(f"Failed to fetch video info for {url}: {e}")
        return jsonify({"error": "Could not fetch video info. Please check the URL and try again."}), 400


@app.route("/download", methods=["POST"])
@requires_auth
def download():
    """Start video download"""
    # Check rate limit
    client_ip = request.remote_addr
    allowed, remaining, reset_seconds = check_download_rate_limit(client_ip)

    if not allowed:
        logger.warning(f"Rate limit exceeded for IP {client_ip}")
        return jsonify({
            "error": f"Rate limit exceeded. You can download {DOWNLOAD_RATE_LIMIT} videos per {DOWNLOAD_RATE_WINDOW // 60} minutes. Try again in {reset_seconds} seconds.",
            "retry_after": reset_seconds
        }), 429

    data = request.get_json()
    url = data.get("url", "").strip()
    format_choice = data.get("format", "best")
    browser = data.get("browser", "none")

    if not url:
        return jsonify({"error": "Please enter a video URL"}), 400

    # Add https if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Generate unique download ID
    download_id = uuid.uuid4().hex[:12]

    # Cleanup old progress entries
    cleanup_old_progress()

    # Initialize progress with timestamp
    download_progress[download_id] = {
        'status': 'starting',
        'percent': 0,
        'timestamp': time.time(),
    }

    # Start download in background thread
    thread = threading.Thread(
        target=download_video,
        args=(url, format_choice, download_id, browser)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        "download_id": download_id,
        "message": "Download started",
        "rate_limit_remaining": remaining
    })


@app.route("/progress/<download_id>")
@requires_auth
def progress(download_id):
    """Get download progress"""
    if download_id in download_progress:
        return jsonify(download_progress[download_id])
    return jsonify({"error": "Download not found"}), 404


@app.route("/file/<filename>")
@requires_auth
def serve_file(filename):
    """Serve downloaded file"""
    # Security: sanitize filename to prevent path traversal attacks
    safe_name = secure_filename(filename)
    if not safe_name:
        logger.warning(f"Invalid filename requested: {filename}")
        abort(400)

    # Additional check: filename should match after sanitization
    # This catches encoded traversal attempts like %2e%2e
    if safe_name != filename:
        logger.warning(f"Filename sanitization changed value: {filename} -> {safe_name}")
        abort(400)

    return send_from_directory(DOWNLOAD_FOLDER, safe_name, as_attachment=True)


@app.route("/downloads")
@requires_auth
def list_downloads():
    """List all downloaded files"""
    files = []
    if os.path.exists(DOWNLOAD_FOLDER):
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith('.'):
                continue  # Skip hidden files like .DS_Store
            filepath = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.isfile(filepath):
                files.append({
                    'filename': f,
                    'size': os.path.getsize(filepath),
                    'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                })

    # Sort by modification time, newest first
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({"files": files})


@app.route("/ytdlp-version")
@requires_auth
def ytdlp_version():
    """Get current yt-dlp version"""
    return jsonify({"version": yt_dlp.version.__version__})


@app.route("/update-ytdlp", methods=["POST"])
@requires_auth
def update_ytdlp():
    """Update yt-dlp to the latest version"""
    global last_update_time
    import subprocess
    import sys

    # Check cooldown
    now = time.time()
    if now - last_update_time < UPDATE_COOLDOWN:
        remaining = int(UPDATE_COOLDOWN - (now - last_update_time))
        return jsonify({
            "success": False,
            "error": f"Please wait {remaining} seconds before updating again."
        }), 429

    try:
        old_version = yt_dlp.version.__version__
        last_update_time = now  # Set cooldown timer

        # Run pip upgrade
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            logger.error(f"yt-dlp update failed: {result.stderr}")
            return jsonify({
                "success": False,
                "error": "Update failed. Check server logs for details."
            }), 500

        # Reload yt_dlp to get new version
        import importlib
        importlib.reload(yt_dlp.version)
        new_version = yt_dlp.version.__version__

        logger.info(f"yt-dlp updated: {old_version} -> {new_version}")
        return jsonify({
            "success": True,
            "old_version": old_version,
            "new_version": new_version,
            "message": f"Updated from {old_version} to {new_version}" if old_version != new_version else "Already up to date"
        })

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp update timed out")
        return jsonify({
            "success": False,
            "error": "Update timed out. Please try again."
        }), 500
    except Exception as e:
        logger.error(f"yt-dlp update error: {e}")
        return jsonify({
            "success": False,
            "error": "Update failed. Check server logs for details."
        }), 500


def get_local_ip():
    """Get the local IP address for network access"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    local_ip = get_local_ip()

    print("\n" + "="*50)
    print("  YouTube Video Downloader")
    print("="*50)
    print(f"\n[*] Local:   http://localhost:5051")
    print(f"[*] Network: http://{local_ip}:5051  <- Use this on your phone")

    if AUTH_ENABLED:
        print(f"\n[*] Authentication ENABLED")
        print(f"    Username: {AUTH_USERNAME}")
        print(f"    Password: {'*' * len(AUTH_PASSWORD)}")
        print(f"    (Set YT_AUTH_USER and YT_AUTH_PASS env vars to change)")
        print(f"    (Set YT_AUTH_ENABLED=false to disable)")
    else:
        print(f"\n[!] Authentication DISABLED")

    print(f"\n[*] Rate limit: {DOWNLOAD_RATE_LIMIT} downloads per {DOWNLOAD_RATE_WINDOW // 60} minutes")
    print("[*] Press Ctrl+C to stop\n")

    # Use Waitress for production-quality serving (handles broken pipes gracefully)
    try:
        from waitress import serve
        print("[*] Using Waitress server")
        serve(app, host='0.0.0.0', port=5051, threads=4)
    except ImportError:
        print("[!] Waitress not installed, using Flask dev server")
        print("[!] Run: pip install waitress (recommended for phone access)")
        debug_mode = os.environ.get('DEBUG', '').lower() in ('1', 'true')
        app.run(debug=debug_mode, port=5051, host='0.0.0.0')
