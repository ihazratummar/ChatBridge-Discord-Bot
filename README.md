[![Built by RelayWorks](https://img.shields.io/badge/Built%20By-RelayWorks-blue)](https://relayworks.dev/discord-bot)

# 🔗 ChatBridge - 2-Way Discord Channel Bridge Bot

**ChatBridge** is a production-grade, high-performance Python Discord bot that establishes seamless **two-way anonymous message relaying** between channels across different Discord servers.

Designed with privacy, reliability, and security in mind, ChatBridge forwards text, embeds, images, attachments, and replies under customizable direction-specific bot identities without revealing users' real names or avatars.

---

## ✨ Features

- 🔄 **2-Way Synchronous Relay**: Automatically mirrors messages between paired channels across servers.
- 🎭 **Custom Anonymous Identities**: Configurable webhook display names per direction (e.g., `Forgotten Names` for Server A → B, `Message Notifier` for Server B → A).
- 🔔 **Role & `@everyone` Pings**: Configure dedicated role mentions or `@everyone` pings when new messages arrive.
- 🛡️ **Anti-Raid / Mass-Ping Sanitization**: Scopes `allowed_mentions` so unprivileged users cannot trigger unauthorized `@everyone` or role pings via message text.
- ⚡ **High Performance & Scale**: Built on `aiosqlite` with **Write-Ahead Logging (WAL)** and **$O(1)$ in-memory route caching**.
- 🛠️ **Self-Healing Webhooks**: Automatically recovers and recreates webhooks if they are deleted or invalidated.
- 🔒 **Owner-Only Security**: Configuration slash commands are strictly restricted to Server Owners and Administrators.

---

## 🛠️ Slash Commands Reference

All commands require **Administrator** or **Server Owner** permissions.

| Command | Description | Parameters |
| :--- | :--- | :--- |
| `/setup-sync` | Link current channel with a channel in another server | `target_channel_id`, `[bot_name_for_target]`, `[bot_name_for_here]` |
| `/set-name` | Update display name for messages posted into a channel | `custom_name`, `[channel_id]` |
| `/set-role` | Configure role or `@everyone` ping for new messages | `[role]`, `[ping_everyone]`, `[channel_id]` |
| `/sync-status` | Display current bridge pairing and identity settings | *None* |
| `/unlink-sync` | Remove active sync bridge for current channel | *None* |

---

## 🚀 Quick Start & Installation

### 1. Prerequisites
- **Python 3.10+** installed.
- A **Discord Bot Token** created via the [Discord Developer Portal](https://discord.com/developers/applications).

> [!IMPORTANT]
> Ensure **MESSAGE CONTENT INTENT** is toggled ON under your bot's **Bot** tab in the Discord Developer Portal.

### 2. Installation

1. **Clone or download the repository:**
   ```bash
   git clone <repository_url>
   cd ChatBridge
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
   ```

### 3. Run the Bot
```bash
python main.py
```

---

## 📖 Step-by-Step Setup Guide for Servers

1. **Invite Bot**: Invite ChatBridge to both **Server A** and **Server B** with the following permissions:
   - `Manage Webhooks`
   - `Send Messages`
   - `Read Message History`
   - `Embed Links`
   - `Attach Files`

2. **Run Sync Setup**:
   In Server A's channel, copy Server B's Channel ID and run:
   ```text
   /setup-sync target_channel_id: 123456789012345678 bot_name_for_target: "Forgotten Names" bot_name_for_here: "Message Notifier"
   ```

3. **Configure Notifications (Optional)**:
   In Server B's channel, set a role to ping when messages arrive from Server A:
   ```text
   /set-role role: @SupportRole
   ```
   Or for `@everyone`:
   ```text
   /set-role ping_everyone: True
   ```

---

## 📁 Project Architecture

```
ChatBridge/
├── main.py                # Bot lifecycle, gateway event handling, signal management
├── bridge_service.py      # In-memory routing, text chunker, webhook recovery & attachment handlers
├── database.py            # Async SQLite manager with WAL mode enabled
├── cogs/
│   └── owner_commands.py  # Owner slash command cog & input validation
├── requirements.txt       # Dependencies manifest
├── .env                   # Environment secrets
└── README.md              # Documentation
```

---

## 🛡️ License & Support

Built for seamless server integration. For custom modifications or support, contact your bot developer.
# ChatBridge-Discord-Bot
