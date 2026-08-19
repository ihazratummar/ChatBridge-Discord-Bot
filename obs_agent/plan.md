# OBS AGENT MODULE PLAN (`obs_agent/`)

Dedicated specification and architecture guide for the client-side OBS Agent and OBS Custom Browser Dock.

---

## 🎯 Purpose & Scope

The `obs_agent/` module runs on the client's local PC alongside OBS Studio. It performs two core tasks:
1. **OBS WebSocket Media Monitoring**: Connects locally to OBS Studio via WebSocket v5 (`ws://127.0.0.1:4455`) to monitor the currently playing Media Source. When **only 5 seconds remain** on the video, it sends a high-priority HTTP POST / WebSocket event to the VPS FastAPI backend.
2. **OBS Custom Browser Dock UI**: Serves a dockable HTML/JS control panel (`dock_panel.html`) rendered directly inside OBS Studio (`Docks -> Custom Browser Docks...`).

---

## 📂 Proposed Component Files

```text
obs_agent/
├── plan.md              # This dedicated module plan
├── config.json          # Local OBS WebSocket settings & VPS server URL
├── obs_agent.py         # Local Python script monitoring OBS Media Input status
├── requirements.txt     # Python dependencies (obsws-python, requests, websocket-client)
└── static/
    └── dock_panel.html  # OBS Custom Browser Dock UI (Creator dropdown & live status)
```

---

## ⚙️ Key Technical Features

### 1. OBS WebSocket v5 Connection (`obs_agent.py`)
- Library: `obsws-python`
- Port: `4455` (default OBS WebSocket v5 port)
- Polling Loop: Calls `GetMediaInputStatus` on the active video Media Source.
- Remaining Time Calculation:
  ```python
  remaining_sec = (total_duration - current_playback_time) / 1000.0
  ```
- **5-Second Video End Alert**:
  When `remaining_sec <= 5.0`, dispatches a payload to VPS:
  `POST https://vps-domain/api/obs-event` with `{"event": "video_ending", "remaining_sec": 5, "creator": active_creator}`.

### 2. OBS Custom Browser Dock UI (`dock_panel.html`)
Rendered inside OBS Studio as a native dockable panel (`Docks -> Custom Browser Docks...`):

```text
┌─────────────────────────────────────────────────────────────┐
│ 🎬 OBS CUSTOM BROWSER DOCK: F2F LIVE MANAGER                │
├─────────────────────────────────────────────────────────────┤
│ 👤 Active Creator Model:                                    │
│    ┌──────────────────────────────────────────────────┐     │
│    │ @xsophiex                                      ▼ │     │
│    └──────────────────────────────────────────────────┘     │
│                                                             │
│ ⚡ Audience Switcher Automation (15s / 5s Loop):             │
│    ┌──────────┐  [ON] Active (15s Global ↔ 5s Followers)    │
│    │ TOGGLE   │  Status: 🟢 12s remaining on Global     │
│    └──────────┘                                             │
│                                                             │
│ ⏱️ Video End Auto-Pause (5s Alert):                         │
│    ┌──────────┐  [ON] Enabled (Pause F2F stream on 5s left) │
│    │ TOGGLE   │  Pause Duration: [ 3 ] seconds              │
│    └──────────┘                                             │
│                                                             │
│ 📊 Live Stream Telemetry & Status:                          │
│    ╭ 🌐 Active Creator  ›  @xsophiex                        │
│    ├ 📺 F2F Live State  ›  🟢 Streaming (ID: ls_9a8b...)   │
│    ├ 👥 Audience Mode   ›  🌐 PUBLIC (Global FYP)           │
│    ├ 🎥 OBS Video Left  ›  01:24 remaining                  │
│    ╰ ⚡ VPS Connection  ›  🟢 Connected (ws://vps:8000/ws)  │
│                                                             │
│ 🕹️ Manual Controls:                                         │
│    [ 🌐 Force Global ]  [ 🔒 Force Followers ]  [ ⏸️ Pause ] │
└─────────────────────────────────────────────────────────────┘
```

- **Creator Selector Dropdown**: Select active model handle (`@xsophiex`, `@chantalkuyt`, `@aylen`, etc.).
- **Audience Switcher Automation Toggle**: ON / OFF toggle for 15s Global / 5s Followers loop.
- **Video End Auto-Pause Toggle**: ON / OFF toggle for 5s video end pause delay.
- **Live Status Telemetry**: Displays OBS video time remaining, F2F stream state, active audience mode (`Global` / `Followers`), and VPS socket connection status.

---

## 🛠️ Operational Setup Instructions

1. Enable OBS WebSocket in OBS Studio (`Tools -> WebSocket Server Settings`):
   - Server Port: `4455`
   - Set Server Password.
2. Configure `obs_agent/config.json` with VPS URL and OBS WebSocket password.
3. Add Custom Browser Dock in OBS Studio (`Docks -> Custom Browser Docks...`):
   - Name: `F2F Live Manager`
   - URL: `http://localhost:8000/dock_panel.html` (or hosted dock URL).
