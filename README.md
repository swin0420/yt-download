# YouTube Video Downloader

A self-hosted web app for downloading YouTube videos using yt-dlp.

## Features

- Download videos in multiple qualities (Best, 720p, 480p, 360p)
- Extract audio as MP3
- Progress tracking with speed and ETA
- Dark themed UI
- Browser cookie support for restricted content
- Works on macOS, Linux, and Windows

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/Cannibal420/yt-download.git
cd yt-download
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
# or
pip3 install -r requirements.txt
```

### 3. Install ffmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to PATH.

### 4. Run the app

```bash
python app.py
# or
python3 app.py
```

### 5. Open in browser

```
http://localhost:5051
```

## Usage

1. Paste a YouTube URL
2. Select your browser (for cookie auth) or use "No Cookies" for public videos
3. Click "Fetch Info"
4. Choose quality/format
5. Wait for download
6. Click "Save File"

## Browser Cookies

For age-restricted or private videos, select your browser from the dropdown. Make sure you're logged into YouTube on that browser.

Supported browsers:
- Brave
- Chrome
- Firefox
- Safari
- Edge

## Troubleshooting

**"ffmpeg not found"**
- Make sure ffmpeg is installed and in your PATH

**"403 Forbidden"**
- Try selecting your browser for cookie authentication
- Make sure you're logged into YouTube

**"Sign in to confirm you're not a bot"**
- Select your browser from the dropdown (must be logged into YouTube)

## Tech Stack

- Python + Flask
- yt-dlp
- ffmpeg
- Vanilla JS/CSS

## Disclaimer

This tool is for personal use only. Respect copyright laws and YouTube's Terms of Service.
