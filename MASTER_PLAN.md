# MASTER ARCHITECTURE & UPDATED PLAN: ChatBridge & F2F Live Automation

Comprehensive roadmap combining:
1. **ChatBridge Bot Updates & Migration**: Unreplied Fans Scanner, Coworker Permission System, VPS Migration Guide, and SOP documentation.
2. **F2F Live Stream & OBS Automation**: Updated multi-creator architecture reflecting Benjamin's latest confirmation (*Live streams & live chat are scoped to individual Creator Accounts*).

---

## 🏗️ UPDATED SYSTEM ARCHITECTURE

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENT'S MOBILE PHONE                                 │
│                   (Private Discord Server — Controls & Unreplied Scanner)                │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │
                                  Discord Slash Commands & Webhooks
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           CENTRAL LINUX VPS (Ubuntu Server)                             │
│                                                                                         │
│  ┌───────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────┐  │
│  │ FastAPI Central Hub   │   │ Unreplied Fans Scanner    │   │ Discord Control Bot   │  │
│  │ (Multi-Creator Sync)  │   │ (Posts unreplied fans)    │   │ (Mobile Panel & SOP)  │  │
│  └───────────────────────┘   └───────────────────────────┘   └───────────────────────┘  │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │
                                  Secure HTTP / WebSockets
                                            │
         ┌──────────────────────────────────┼──────────────────────────────────┐
         │                                  │                                  │
         ▼                                  ▼                                  ▼
┌──────────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐
│ WINDOWS VPS NODE #1      │   │ WINDOWS VPS NODE #2      │   │ WINDOWS VPS NODE #5      │
│ Model: @xsophiex         │   │ Model: @chantalkuyt      │   │ Model: @aylen            │
│ ──────────────────────── │   │ ──────────────────────── │   │ ──────────────────────── │
│ • Creator Account Auth   │   │ • Creator Account Auth   │   │ • Creator Account Auth   │
│ • OBS Studio Video Loop  │   │ • OBS Studio Video Loop  │   │ • OBS Studio Video Loop  │
│ • obs_agent.py (5s alert)│   │ • obs_agent.py (5s alert)│   │ • obs_agent.py (5s alert)│
│ • 15s/5s FYP Loop Engine │   │ • 15s/5s FYP Loop Engine │   │ • 15s/5s FYP Loop Engine │
│ • F2F Live Stream & Chat │   │ • F2F Live Stream & Chat │   │ • F2F Live Stream & Chat │
│ • Discord Screenshare    │   │ • Discord Screenshare    │   │ • Discord Screenshare    │
└──────────────────────────┘   └──────────────────────────┘   └──────────────────────────┘
```

---

## 🎯 PART A: ChatBridge Current Bot Enhancements & Migration

### 1. Unreplied Fans Scanner (`services/unreplied_scanner_service.py`)
- **Functionality**: Scans all active chats for each creator model.
- **Detection Logic**: Identifies chats where the last message is an unreplied incoming fan message (`is_from_user: True` or `unread: True`).
- **Discord Notification**: Dispatches rich embed cards to `#unreplied-fans` channel listing fan username, wait time, and direct chat link so human chatters can jump in immediately.

### 2. Coworker Permission & Role Manager (`cogs/coworker_permissions.py`)
- Creates granular Discord permission roles (`@Manager`, `@Chatter`, `@Viewer`).
- Restricts bot settings and configuration commands to `@Manager`.
- Allows `@Chatter` to view unreplied fan feeds and live stream status.

### 3. VPS Migration & SOP Documentation (`MIGRATION_SOP.md`)
- Complete setup guide for Benjamin to deploy the bot on his own Ubuntu VPS before your trial VPS expires in 2–3 days.
- Step-by-step Standard Operating Procedure (SOP) manual for agency chatters.

---

## ⚡ PART B: F2F Live Stream & OBS Automation (Updated Architecture)

### Key Discovery from Client:
> *"Agency account has access to all creator accounts, but NOT inside lives. Only creator account has access to live streams and live chat."*

### Updated Technical Strategy:
1. **Creator-Direct Authentication**:
   - Each Windows VPS Node logs in directly as that Creator Model (`@xsophiex`, `@chantalkuyt`, etc.) using creator credentials + 2FA TOTP (`pyotp`).
2. **OBS WebSocket 5-Second Video End Alert**:
   - `obs_agent.py` monitors OBS Media Source position. When remaining duration $\le 5.0\text{s}$, alerts the engine to pause F2F stream output for $X$ seconds delay before resuming.
3. **F2F FYP Audience Switcher**:
   - Executes 50ms REST API calls (`POST /api/livestreams/{uuid}/audience/`) cycling **15s Global (`public`) $\leftrightarrow$ 5s Followers Only (`fans-and-followers`)**.
4. **Live Stream Chat Dispatcher**:
   - Allows sending live in-stream comments (in Dutch or English) directly from Benjamin's phone via Discord `/live-chat` slash command.

---

## 🗓️ IMPLEMENTATION PHASES

### Phase 1: ChatBridge Migration & Unreplied Fans Scanner (Immediate: 1–2 Days)
- Build `unreplied_scanner_service.py` & `#unreplied-fans` Discord feed.
- Create `MIGRATION_SOP.md` & assist Benjamin with VPS transfer before current VPS expires in 2 days.

### Phase 2: F2F Live Stream API Client & Creator Engine (Days 3–4)
- Build Creator Account 2FA live client for F2F (`POST /api/livestreams/{uuid}/audience/`).
- Build 15s/5s FYP audience loop switcher with response verification.

### Phase 3: OBS Agent & Custom Browser Dock (Days 5–6)
- Build `obs_agent.py` with OBS WebSocket v5 remaining time monitor.
- Create `dock_panel.html` UI embedded natively in OBS Studio.

### Phase 4: Discord Mobile Control Hub & 5-VPS Staging (Day 7)
- Integrate Discord mobile panel (`/live-status`, `/live-toggle`, `/live-chat`).
- Staging on Benjamin's 5 Windows VPS nodes + 1 Central Linux Controller VPS.
