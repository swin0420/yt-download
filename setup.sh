#!/bin/bash

# YouTube Downloader - Service Setup Script
# Configures auto-start service for macOS, Linux, or Windows (WSL)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="ytdownloader"
PORT=5051

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

detect_os() {
    case "$(uname -s)" in
        Darwin*) echo "macos" ;;
        Linux*)  echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

check_dependencies() {
    log_info "Checking dependencies..."

    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        log_error "Python not found. Please install Python 3.10+"
        exit 1
    fi

    log_info "Python: $($PYTHON_CMD --version)"

    # Check if venv exists
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        log_warn "Virtual environment not found. Creating one..."
        $PYTHON_CMD -m venv "$SCRIPT_DIR/venv"
    fi

    # Check ffmpeg
    if command -v ffmpeg &> /dev/null; then
        log_info "ffmpeg: $(ffmpeg -version 2>&1 | head -n1)"
    else
        log_warn "ffmpeg not found. Some features may not work."
    fi

    # Check Node.js (optional, for YouTube signature solving)
    if command -v node &> /dev/null; then
        log_info "Node.js: $(node --version)"
    else
        log_warn "Node.js not found. YouTube downloads may fail."
    fi
}

install_dependencies() {
    log_info "Installing Python dependencies..."
    source "$SCRIPT_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install flask waitress yt-dlp

    # Optional: YouTube anti-bot plugins
    pip install yt-dlp-ejs bgutil-ytdlp-pot-provider yt-dlp-get-pot 2>/dev/null || \
        log_warn "Could not install YouTube plugins (optional)"

    deactivate
    log_info "Dependencies installed."
}

setup_macos() {
    log_info "Setting up macOS launchd service..."

    PLIST_NAME="com.user.$SERVICE_NAME.plist"
    PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

    # Create plist from template
    cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.$SERVICE_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/venv/bin/python</string>
        <string>$SCRIPT_DIR/app.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

    # Create logs directory
    mkdir -p "$SCRIPT_DIR/logs"

    # Load the service
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"

    log_info "Service installed and started!"
    log_info "Plist location: $PLIST_PATH"
    echo ""
    echo "Commands:"
    echo "  Start:   launchctl start com.user.$SERVICE_NAME"
    echo "  Stop:    launchctl stop com.user.$SERVICE_NAME"
    echo "  Restart: launchctl stop com.user.$SERVICE_NAME && launchctl start com.user.$SERVICE_NAME"
    echo "  Logs:    tail -f $SCRIPT_DIR/logs/stderr.log"
}

setup_linux() {
    log_info "Setting up Linux systemd service..."

    SERVICE_FILE="$HOME/.config/systemd/user/$SERVICE_NAME.service"
    mkdir -p "$HOME/.config/systemd/user"

    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=YouTube Video Downloader
After=network.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/app.py
Restart=always
RestartSec=10
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF

    # Create logs directory
    mkdir -p "$SCRIPT_DIR/logs"

    # Reload and enable service
    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME"
    systemctl --user start "$SERVICE_NAME"

    log_info "Service installed and started!"
    log_info "Service file: $SERVICE_FILE"
    echo ""
    echo "Commands:"
    echo "  Start:   systemctl --user start $SERVICE_NAME"
    echo "  Stop:    systemctl --user stop $SERVICE_NAME"
    echo "  Restart: systemctl --user restart $SERVICE_NAME"
    echo "  Status:  systemctl --user status $SERVICE_NAME"
    echo "  Logs:    journalctl --user -u $SERVICE_NAME -f"
    echo ""
    echo "Note: To keep service running after logout, run:"
    echo "  sudo loginctl enable-linger \$USER"
}

setup_windows() {
    log_info "Setting up Windows startup..."

    # Create a batch file for Windows
    BAT_FILE="$SCRIPT_DIR/start-server.bat"

    cat > "$BAT_FILE" << 'EOF'
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python app.py
EOF

    # Create a VBS file for hidden startup
    VBS_FILE="$SCRIPT_DIR/start-hidden.vbs"

    cat > "$VBS_FILE" << EOF
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "$SCRIPT_DIR/start-server.bat" & chr(34), 0
Set WshShell = Nothing
EOF

    log_info "Windows startup files created!"
    echo ""
    echo "To auto-start on login:"
    echo "  1. Press Win+R, type: shell:startup"
    echo "  2. Create a shortcut to: $VBS_FILE"
    echo ""
    echo "To start manually, run: start-server.bat"
}

show_status() {
    OS=$(detect_os)
    echo ""
    log_info "Checking service status..."

    case $OS in
        macos)
            launchctl list | grep -q "$SERVICE_NAME" && \
                log_info "Service is running" || \
                log_warn "Service is not running"
            ;;
        linux)
            systemctl --user is-active "$SERVICE_NAME" &>/dev/null && \
                log_info "Service is running" || \
                log_warn "Service is not running"
            ;;
        *)
            log_warn "Cannot check status on this OS"
            ;;
    esac

    # Check if port is listening
    if command -v lsof &> /dev/null; then
        lsof -i :$PORT &>/dev/null && \
            log_info "Port $PORT is listening" || \
            log_warn "Port $PORT is not listening"
    fi

    echo ""
    echo "Access the app at: http://localhost:$PORT"
}

uninstall_service() {
    OS=$(detect_os)
    log_info "Uninstalling service..."

    case $OS in
        macos)
            PLIST_PATH="$HOME/Library/LaunchAgents/com.user.$SERVICE_NAME.plist"
            launchctl unload "$PLIST_PATH" 2>/dev/null || true
            rm -f "$PLIST_PATH"
            log_info "macOS service removed"
            ;;
        linux)
            systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
            systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
            rm -f "$HOME/.config/systemd/user/$SERVICE_NAME.service"
            systemctl --user daemon-reload
            log_info "Linux service removed"
            ;;
        *)
            log_warn "Manual uninstall required for this OS"
            ;;
    esac
}

show_help() {
    echo "YouTube Downloader - Setup Script"
    echo ""
    echo "Usage: ./setup.sh [command]"
    echo ""
    echo "Commands:"
    echo "  install     Install dependencies and set up auto-start service"
    echo "  start       Start the service"
    echo "  stop        Stop the service"
    echo "  restart     Restart the service"
    echo "  status      Show service status"
    echo "  uninstall   Remove the auto-start service"
    echo "  help        Show this help message"
    echo ""
    echo "With no command, runs full install."
}

# Main
main() {
    OS=$(detect_os)
    log_info "Detected OS: $OS"

    case "${1:-install}" in
        install)
            check_dependencies
            install_dependencies
            case $OS in
                macos)   setup_macos ;;
                linux)   setup_linux ;;
                windows) setup_windows ;;
                *)       log_error "Unsupported OS: $OS"; exit 1 ;;
            esac
            show_status
            ;;
        start)
            case $OS in
                macos)   launchctl start "com.user.$SERVICE_NAME" ;;
                linux)   systemctl --user start "$SERVICE_NAME" ;;
                *)       log_error "Use start-server.bat on Windows" ;;
            esac
            ;;
        stop)
            case $OS in
                macos)   launchctl stop "com.user.$SERVICE_NAME" ;;
                linux)   systemctl --user stop "$SERVICE_NAME" ;;
                *)       log_error "Stop the process manually on Windows" ;;
            esac
            ;;
        restart)
            case $OS in
                macos)   launchctl stop "com.user.$SERVICE_NAME"; launchctl start "com.user.$SERVICE_NAME" ;;
                linux)   systemctl --user restart "$SERVICE_NAME" ;;
                *)       log_error "Restart manually on Windows" ;;
            esac
            ;;
        status)
            show_status
            ;;
        uninstall)
            uninstall_service
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
