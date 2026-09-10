#!/bin/bash
set -e

echo "========================================================="
echo " 🌐 F2F Bulletproof Multi-Model Chrome Profile Setup"
echo "========================================================="

MODELS=("xsophiex" "chantalkuyt" "aylen" "zoelynn")
DESKTOP_DIR="/root/Desktop"
mkdir -p "$DESKTOP_DIR"

for MODEL in "${MODELS[@]}"; do
    PROFILE_DIR="/root/.config/chrome-profiles/$MODEL"
    mkdir -p "$PROFILE_DIR"
    echo "📁 Initialized isolated data directory: $PROFILE_DIR"

    # Create Desktop Launcher Shortcut
    SHORTCUT="$DESKTOP_DIR/Chrome - $MODEL.desktop"
    cat <<EOF > "$SHORTCUT"
[Desktop Entry]
Version=1.0
Type=Application
Name=Chrome ($MODEL)
Exec=google-chrome --user-data-dir=$PROFILE_DIR --password-store=basic --disable-features=WebRTCPipeWireCapturer --no-first-run --no-default-browser-check --autoplay-policy=no-user-gesture-required --disable-dev-shm-usage --enable-gpu-rasterization --ignore-gpu-blocklist --disable-background-timer-throttling --disable-renderer-backgrounding "https://f2f.com/live/?creator=$MODEL"
Icon=google-chrome
Path=/root
Terminal=false
StartupNotify=true
Categories=Network;WebBrowser;
EOF
    chmod +x "$SHORTCUT"
    echo "🖥️  Created desktop shortcut: Chrome ($MODEL)"
done

echo ""
echo "✅ All 4 isolated Chrome profiles and desktop shortcuts created successfully!"
echo "========================================================="
