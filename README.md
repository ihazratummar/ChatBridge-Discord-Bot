# 🌐 ChatBridge - Multi-Topology Discord Channel Bridge Bot

**ChatBridge** is a production-grade, high-performance Python Discord bot that establishes flexible **multi-channel message relaying networks** across different Discord servers.

Whether you need **1-to-1 pairing**, **1-to-Many broadcasting**, **Many-to-One aggregation**, or **Many-to-Many mesh networks**, ChatBridge handles multi-connection topologies effortlessly with automatic message deduplication and direction-specific anonymous bot identities.

---

## ✨ Features & Supported Topologies

- ↔️ **1-to-1 Direct Sync**: Mirror messages bi-directionally between two specific channels.
- 📢 **1-to-Many (Broadcast)**: 1 source channel broadcasts to $N$ destination channels simultaneously.
- 📥 **Many-to-One (Aggregation)**: $N$ client channels feed into a single central management/support channel.
- 🕸️ **Many-to-Many (Mesh Network)**: $N$ channels linked together in a full 2-way sync group.
- 🔀 **Multiple Connections**: Channels can belong to multiple distinct bridge networks simultaneously without duplicate posts.
- 🎭 **Custom Anonymous Identities**: Configurable webhook display names per channel/direction (e.g. `Forgotten Names`, `Message Notifier`).
- 🔔 **Role & `@everyone` Pings**: Configure dedicated role mentions or `@everyone` pings when new messages arrive.
- 🛡️ **Anti-Raid / Mass-Ping Protection**: Scopes `allowed_mentions` so unprivileged users cannot trigger unauthorized `@everyone` or role pings via message text.
- ⚡ **High Performance & Scale**: Built on `aiosqlite` with **Write-Ahead Logging (WAL)** and **$O(1)$ in-memory route caching**.
- 🐳 **Docker & CI/CD Ready**: Includes `Dockerfile`, `.dockerignore`, and GitHub Actions workflow for automated VPS deployment.

---

## 🛠️ Slash Commands Reference

All commands require **Administrator** or **Server Owner** permissions.

| Command | Description | Parameters |
| :--- | :--- | :--- |
| `/setup-sync` | Quickly bridge current channel with another (1:1 or group join) | `target_channel_id`, `[mode]`, `[bot_name_for_target]`, `[bot_name_for_here]` |
| `/bridge-create` | Create a new named multi-channel bridge network | `network_name` |
| `/bridge-add` | Add a channel to an existing bridge network (1:1, 1:N, N:1, N:M) | `group_id`, `[target_channel_id]`, `[mode]`, `[custom_name]` |
| `/bridge-remove` | Remove a channel from a bridge network | `group_id`, `[target_channel_id]` |
| `/set-name` | Update display name for messages posted into a channel | `custom_name`, `[channel_id]`, `[group_id]` |
| `/set-role` | Configure role or `@everyone` ping for new messages | `[role]`, `[ping_everyone]`, `[channel_id]`, `[group_id]` |
| `/sync-status` | Display active bridge networks, channel members, modes, and pings | *None* |

---

## 🚀 VPS & Docker Deployment Setup

### 1. GitHub Repository Secrets Required
Add the following secrets to your GitHub repository under **Settings ➔ Secrets and variables ➔ Actions**:
- `DOCKERHUB_USERNAME`: Your Docker Hub username.
- `DOCKERHUB_TOKEN`: Your Docker Hub access token.

### 2. VPS Server Setup
On your VPS:
1. **Set up environment file at `/home/envs/chatbridge.env`:**
   ```env
   DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
   DB_PATH=/app/data/chatbridge.db
   ```
2. **Create persistent database volume folder:**
   ```bash
   mkdir -p /home/chatbridge/data
   ```
3. **Register GitHub Self-Hosted Runner:**
   Add a self-hosted runner on your VPS under **Settings ➔ Actions ➔ Runners**.

When you push to the `main` branch, GitHub Actions will automatically build the image, push it to Docker Hub, pull it on your VPS, and restart the `ChatBridge` container!
