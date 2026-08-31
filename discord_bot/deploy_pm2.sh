#!/bin/bash
# ==============================================================================
# ChatBridge Discord Bot - 24/7 PM2 Auto-Installer & Runner Script
# ==============================================================================

set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

APP_NAME="chatbridge-discord-bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   🚀 ChatBridge Discord Bot - PM2 Setup & Runner     ${NC}"
echo -e "${CYAN}======================================================${NC}"

# ------------------------------------------------------------------------------
# 1. Check & Install System Packages (Ubuntu/Debian)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[1/5] Checking System Prerequisites...${NC}"

if command -v apt-get &> /dev/null; then
    echo -e "${YELLOW}Detected Debian/Ubuntu system. Updating packages...${NC}"
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv curl git build-essential
elif command -v brew &> /dev/null; then
    echo -e "${YELLOW}Detected macOS (Homebrew)...${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Check & Install Node.js and PM2
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[2/5] Checking Node.js & PM2...${NC}"

if ! command -v node &> /dev/null || ! command -v npm &> /dev/null; then
    echo -e "${YELLOW}Node.js/NPM not found. Installing Node.js LTS...${NC}"
    if command -v apt-get &> /dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif command -v brew &> /dev/null; then
        brew install node
    else
        echo -e "${RED}Error: Please install Node.js and NPM manually on your OS.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ Node.js version: $(node -v)${NC}"
echo -e "${GREEN}✓ NPM version: $(npm -v)${NC}"

if ! command -v pm2 &> /dev/null; then
    echo -e "${YELLOW}PM2 not found. Installing PM2 globally...${NC}"
    sudo npm install -g pm2 || npm install -g pm2
fi

echo -e "${GREEN}✓ PM2 version: $(pm2 -v)${NC}"

# ------------------------------------------------------------------------------
# 3. Setup Python Virtual Environment & Dependencies
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[3/5] Setting up Python Environment...${NC}"

# If .venv exists but is from another OS (like Mac) or broken, remove and recreate
if [ -d ".venv" ]; then
    if ! .venv/bin/python3 -c "import sys" &> /dev/null; then
        echo -e "${YELLOW}Detected incompatible or invalid .venv (e.g. copied from Mac). Recreating clean Linux .venv...${NC}"
        rm -rf .venv
    fi
fi

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating clean Python virtual environment (.venv)...${NC}"
    python3 -m venv .venv
fi

chmod -R +x .venv/bin/

echo -e "${YELLOW}Installing/Updating Python dependencies...${NC}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo -e "${GREEN}✓ Python dependencies installed successfully.${NC}"

# ------------------------------------------------------------------------------
# 4. Check .env Configuration File
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[4/5] Checking Environment Configuration...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}No .env found. Copying .env.example -> .env...${NC}"
        cp .env.example .env
        echo -e "${RED}⚠️  IMPORTANT: Please edit .env with your DISCORD_BOT_TOKEN and credentials!${NC}"
    else
        echo -e "${RED}⚠️  Warning: No .env file found in $(pwd)${NC}"
    fi
else
    echo -e "${GREEN}✓ .env configuration file exists.${NC}"
fi

# ------------------------------------------------------------------------------
# 5. Start / Restart Bot with PM2
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[5/5] Launching Discord Bot with PM2 (24/7 Mode)...${NC}"

# Check if bot is already running in PM2
if pm2 list | grep -q "$APP_NAME"; then
    echo -e "${YELLOW}Restarting existing PM2 process: $APP_NAME...${NC}"
    pm2 restart "$APP_NAME"
else
    echo -e "${YELLOW}Starting new PM2 process: $APP_NAME...${NC}"
    pm2 start .venv/bin/python --name "$APP_NAME" -- main.py
fi

# Save PM2 process list so it automatically restarts on VPS reboot
pm2 save

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}   ✅ Discord Bot is NOW RUNNING 24/7 with PM2!       ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "\n${CYAN}Useful PM2 Management Commands:${NC}"
echo -e "  • ${YELLOW}pm2 status${NC}                → Check bot status & uptime"
echo -e "  • ${YELLOW}pm2 logs $APP_NAME${NC}         → View live real-time console logs"
echo -e "  • ${YELLOW}pm2 stop $APP_NAME${NC}         → Stop the bot"
echo -e "  • ${YELLOW}pm2 restart $APP_NAME${NC}      → Restart the bot"
echo -e "  • ${YELLOW}pm2 delete $APP_NAME${NC}       → Remove bot from PM2"
echo -e "  • ${YELLOW}pm2 startup${NC}               → Enable auto-start on system boot\n"
