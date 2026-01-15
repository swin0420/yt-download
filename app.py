"""
YouTube Video Downloader
A Flask app for downloading YouTube videos using yt-dlp
"""

import os
import uuid
import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, Response

try:
    import yt_dlp
except ImportError:
    print("Please install yt-dlp: pip install yt-dlp")
    raise

app = Flask(__name__)

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

        # Add browser cookies if not 'none'
        if browser and browser != 'none':
            ydl_opts['cookiesfrombrowser'] = (browser,)

        # Configure format based on choice - prefer pre-combined formats to avoid 403
        if format_choice == 'best':
            ydl_opts['format'] = 'best[ext=mp4]/best'
        elif format_choice == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif format_choice == '1080p':
            ydl_opts['format'] = 'best[height<=1080][ext=mp4]/best[height<=1080]/best'
        elif format_choice == '720p':
            ydl_opts['format'] = 'best[height<=720][ext=mp4]/best[height<=720]/best'
        elif format_choice == '480p':
            ydl_opts['format'] = 'best[height<=480][ext=mp4]/best[height<=480]/best'
        elif format_choice == '360p':
            ydl_opts['format'] = 'best[height<=360][ext=mp4]/best[height<=360]/best'
        else:
            ydl_opts['format'] = format_choice

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Handle audio extraction filename change
            if format_choice == 'audio':
                filename = os.path.splitext(filename)[0] + '.mp3'

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
def index():
    """Serve the main webpage"""
    return render_template("youtube.html")


@app.route("/info", methods=["POST"])
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
        return jsonify({"error": f"Could not fetch video info: {str(e)}"}), 400


@app.route("/download", methods=["POST"])
def download():
    """Start video download"""
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
        "message": "Download started"
    })


@app.route("/progress/<download_id>")
def progress(download_id):
    """Get download progress"""
    if download_id in download_progress:
        return jsonify(download_progress[download_id])
    return jsonify({"error": "Download not found"}), 404


@app.route("/file/<filename>")
def serve_file(filename):
    """Serve downloaded file"""
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


@app.route("/downloads")
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
    print("[*] Press Ctrl+C to stop\n")

    # host='0.0.0.0' allows access from other devices on the network
    app.run(debug=True, port=5051, host='0.0.0.0')
