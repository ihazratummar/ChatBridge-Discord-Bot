# 🌐 ChatBridge & F2F Automation Suite

Production-grade automation suite comprising 3 distinct, modular components:

```text
ChatBridge/
├── 🤖 1. DISCORD BOT (Root Project)       -> Handles Fan Outreach, Campaigns & ChatBridge Routing
├── ⚡ 2. FASTAPI LIVE SERVER (fastapi_server/) -> Handles F2F Live FYP Switching & Multi-VPS Event Control
└── 🎬 3. OBS SCRIPT & DOCK (obs_agent/)    -> Native OBS Studio Plugin & Dock for Creator VPS Nodes
```

---

## 📦 1. Discord Bot (Root Directory)
* **Path**: `/` (root)
* **Execution**: `python main.py` (or `.venv/bin/python main.py`)
* **Environment**: `.env` (Discord Token, Cloud MongoDB Atlas URI, F2F Credentials)
* **Features**:
  - **F2F Automated Fan Campaigns**: Sends personalized initial & follow-up messages on behalf of creator models with automated 2FA login.
  - **Reply & Unread Safety Guards**: Strictly preserves unread red badges on F2F so human chatters never lose incoming fan messages.
  - **Cross-Server ChatBridge Routing**: Synchronizes channels across Discord servers.

---

## ⚡ 2. FastAPI Live Automation Server (`fastapi_server/`)
* **Path**: [`fastapi_server/`](file:///Volumes/SSD/Coding/python/discord%20bot/ChatBridge/fastapi_server/)
* **Execution**: `fastapi_server/.venv/bin/python fastapi_server/main.py`
* **Environment**: `fastapi_server/.env`
* **Features**:
  - **Central Multi-VPS Hub**: Listens for video playback events from all creator OBS nodes (`POST /api/obs-event`).
  - **F2F FYP Audience Switcher**: Rapidly cycles **15s Global (`public`) $\leftrightarrow$ 5s Followers (`fans-and-followers`)** via direct F2F Live API calls.
  - **5-Second Video End Auto-Pause**: Pauses F2F live output with a 3-second delay when any creator video loop finishes.
  - **Serves OBS Custom Dock**: Serves the dark-mode OBS Dock at `http://127.0.0.1:8000/dock`.

---

## 🎬 3. Native OBS Studio Plugin & Dock (`obs_agent/`)
* **Path**: [`obs_agent/`](file:///Volumes/SSD/Coding/python/discord%20bot/ChatBridge/obs_agent/)
* **Deployment**: Installed on each Creator Windows/Linux VPS inside OBS Studio (`Tools -> Scripts`).
* **Components**:
  - [`f2f_obs_plugin.py`](file:///Volumes/SSD/Coding/python/discord%20bot/ChatBridge/obs_agent/f2f_obs_plugin.py): Native OBS Python plugin with built-in creator model dropdown (`@xsophiex`, `@chantalkuyt`, `@aylen`).
  - [`static/dock_panel.html`](file:///Volumes/SSD/Coding/python/discord%20bot/ChatBridge/obs_agent/static/dock_panel.html): Visual dock panel for OBS (`Docks -> Custom Browser Docks...`).
* **Features**:
  - Runs **100% inside OBS Studio** with zero background terminals or extra processes.
  - Monitors active video duration in real-time.
  - Shoots asynchronous webhooks to the Central FastAPI Server when **5 seconds remain** on the video.
