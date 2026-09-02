#!/bin/bash
# ==============================================================================
# FastAPI Server - 24/7 PM2 Auto-Installer & Runner Script
# ==============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

APP_NAME="fastapi-live"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   ⚡ F2F FastAPI Server - PM2 Setup & Runner        ${NC}"
echo -e "${CYAN}======================================================${NC}"

# Check Node & PM2
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

# Check .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}Copied .env.example -> .env. Please update credentials if needed.${NC}"
    fi
fi

# Start with PM2
echo -e "\n${YELLOW}Launching FastAPI Server with PM2 (Port 8000)...${NC}"
if pm2 list | grep -q "$APP_NAME"; then
    pm2 restart "$APP_NAME"
else
    pm2 start .venv/bin/python --name "$APP_NAME" -- main.py
fi

pm2 save

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}   ✅ FastAPI Server is RUNNING 24/7 on Port 8000!   ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "  • ${YELLOW}pm2 status${NC}           → Check status"
echo -e "  • ${YELLOW}pm2 logs $APP_NAME${NC}    → View real-time logs"
echo -e "  • ${YELLOW}pm2 restart $APP_NAME${NC} → Restart server\n"
