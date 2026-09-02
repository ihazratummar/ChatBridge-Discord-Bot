#!/bin/bash
# ==============================================================================
# OBS Agent - 24/7 PM2 Auto-Installer & Runner Script
# ==============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

APP_NAME="obs-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   🎬 OBS Agent - PM2 Setup & Runner (Port 8080)     ${NC}"
echo -e "${CYAN}======================================================${NC}"

# Check PM2
if ! command -v pm2 &> /dev/null; then
    echo -e "${YELLOW}PM2 not found. Installing PM2 globally...${NC}"
    sudo npm install -g pm2 || npm install -g pm2
fi

# Setup Python Virtual Environment
echo -e "\n${YELLOW}Setting up Python virtual environment...${NC}"
if [ -d ".venv" ]; then
    if ! .venv/bin/python3 -c "import sys" &> /dev/null; then
        echo -e "${YELLOW}Recreating clean Linux .venv...${NC}"
        rm -rf .venv
    fi
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

chmod -R +x .venv/bin/

echo -e "${YELLOW}Installing/Updating dependencies...${NC}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --retries 20 --default-timeout 100 -r requirements.txt

# Start with PM2
echo -e "\n${YELLOW}Launching OBS Agent with PM2 (Port 8080)...${NC}"
if pm2 list | grep -q "$APP_NAME"; then
    pm2 restart "$APP_NAME"
else
    pm2 start .venv/bin/python --name "$APP_NAME" -- obs_agent.py
fi

pm2 save

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}   ✅ OBS Agent is RUNNING 24/7 on Port 8080!        ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "  • ${YELLOW}pm2 status${NC}           → Check status"
echo -e "  • ${YELLOW}pm2 logs $APP_NAME${NC}    → View real-time logs"
echo -e "  • ${YELLOW}pm2 restart $APP_NAME${NC} → Restart agent\n"
