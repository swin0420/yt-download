# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube Video Downloader - A self-hosted Flask web application for downloading YouTube videos using yt-dlp. Provides a dark-themed UI with progress tracking, format selection, and browser cookie authentication support.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (starts on port 5051)
python app.py

# Server accessible at http://localhost:5051 and from local network
```

**System requirement:** ffmpeg must be installed (auto-detected from common locations)

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
- Format options: best/720p/480p/360p/audio-only (MP3/FLAC)
- `GET /ytdlp-version` returns current yt-dlp version
- `POST /update-ytdlp` upgrades yt-dlp via pip (handles YouTube API changes)

**Key Frontend Details:**
- Polls `/progress/<id>` at 500ms intervals
- State variables: `currentUrl`, `currentBrowser`, format selection
- Helper functions: `formatDuration`, `formatViews`, `formatBytes`, `escapeHtml`
- Footer shows yt-dlp version with update button for easy upgrades
