# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube Video Downloader - A self-hosted Flask web application for downloading YouTube videos using yt-dlp. Provides a dark-themed UI with progress tracking, format selection, and browser cookie authentication support.

## Commands

```bash
# Activate the virtual environment
source venv/bin/activate

# Run the application (starts on port 5051)
python app.py

# Server accessible at http://localhost:5051 and from local network
```

## System Requirements

- **Python 3.12+** (via Homebrew: `brew install python@3.12`)
- **ffmpeg** (auto-detected from common locations)

### Virtual Environment Setup

The app uses a Python 3.12 venv at `./venv/`:

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask waitress yt-dlp
```

### Auto-Start Service (Cross-Platform)

Use `setup.sh` to install as a background service:

```bash
./setup.sh           # Install and start service
./setup.sh start     # Start the service
./setup.sh stop      # Stop the service
./setup.sh restart   # Restart the service
./setup.sh status    # Check if running
./setup.sh uninstall # Remove auto-start
```

**Platform-specific details:**
- **macOS**: Uses launchd (`~/Library/LaunchAgents/com.user.ytdownloader.plist`)
- **Linux**: Uses systemd user service (`~/.config/systemd/user/ytdownloader.service`)
- **Windows**: Creates startup batch/VBS files

**Manual launchd control (macOS):**
```bash
launchctl stop com.user.ytdownloader
launchctl start com.user.ytdownloader
```

**Note:** The owner's instance uses a custom plist at `com.nekonya.ytdownloader` with auth env vars configured.

## Authentication & Rate Limiting

The app includes security features for network deployment:

**Authentication** (enabled by default):
```bash
# Environment variables
YT_AUTH_ENABLED=true   # Enable/disable auth
YT_AUTH_USER=admin     # Username (default: admin)
YT_AUTH_PASS=changeme  # Password (default: changeme)
```

**Rate Limiting**:
- Downloads: 10 per 10 minutes per IP (configurable via `DOWNLOAD_RATE_LIMIT`, `DOWNLOAD_RATE_WINDOW`)
- yt-dlp updates: 5 minute cooldown (`UPDATE_COOLDOWN`)

## Architecture

**Stack:** Python/Flask backend + vanilla JavaScript/HTML/CSS frontend

```
Flask Backend (app.py)
├── Routes: /, /info, /download, /progress/<id>, /file/<name>, /downloads, /ytdlp-version, /update-ytdlp
├── yt-dlp integration for video extraction
├── Background thread downloads with progress tracking
└── Browser cookie authentication (Brave, Chrome, Firefox, Safari, Edge)
           ↕ REST API (JSON)
Frontend (templates/ + static/)
├── youtube.html - HTML structure
├── youtube.js - API calls, polling, UI state management
└── youtube.css - Dark theme with CSS custom properties
```

**Download Flow:**
1. `POST /info` → Extract metadata with yt-dlp (no download)
2. `POST /download` → Start background thread, returns download ID
3. `GET /progress/<id>` → Poll every 500ms for progress
4. File saved to `./downloads/`, served via `GET /file/<name>`

**Key Backend Details:**
- `download_progress` dict tracks active downloads in memory
- `progress_hook()` callback updates progress during yt-dlp download
- `get_ffmpeg_location()` auto-detects ffmpeg on macOS/Linux/Windows
- Uses yt-dlp's `cookiesfrombrowser` for authenticated downloads
- Format selection: `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best`
- Format options: best (up to 4K)/1080p/720p/480p/360p/audio-only (MP3/FLAC)
- `GET /ytdlp-version` returns current yt-dlp version
- `POST /update-ytdlp` upgrades yt-dlp via pip
- `GET /downloads` lists all downloaded files

**Key Frontend Details:**
- Polls `/progress/<id>` at 500ms intervals
- State variables: `currentUrl`, `currentBrowser`, format selection
- Helper functions: `formatDuration`, `formatViews`, `formatBytes`, `escapeHtml`
- Footer shows yt-dlp version with update button

## Troubleshooting

### "The downloaded file is empty" error

YouTube is blocking the download. Try:

1. **Select your browser** for cookie authentication
2. **Close the browser** before fetching (Windows requirement - browser locks cookie database)
3. **Make sure you're logged into YouTube** in that browser
4. **Update yt-dlp** via the button in the web UI footer

### "Could not copy Chrome cookie database" (Windows)

Chrome locks its database while running. Solutions:
- Close Chrome completely (check Task Manager)
- Use Firefox instead (doesn't have this locking issue)
- Use Edge if you're logged into YouTube there

### Low quality downloads (360p instead of 720p+)

- Check format strings in `app.py` - complex protocol filters can cause fallback
- Current working format: `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best`

## Project Status

This project is feature-complete and stable. No new features are planned.
