# FASTAPI SERVER & SERVICES MODULE PLAN (`fastapi_server/`)

Updated technical specification for the VPS Backend Services, Unreplied Fans Scanner, and F2F Live Stream Automation Engine.

---

## 🎯 Purpose & Core Capabilities

1. **Unreplied Fans Scanner (`services/unreplied_scanner_service.py`)**:
   - Traverses active chats for creator models.
   - Identifies incoming messages that have NOT received a reply from human chatters or the bot.
   - Dispatches real-time alerts to the dedicated `#unreplied-fans` Discord channel.
2. **Creator-Scoped F2F Live API Engine (`services/f2f_live_client.py`)**:
   - F2F Live Streams & Live Chat are scoped directly to individual Creator Accounts.
   - Authenticates using creator credentials + 2FA TOTP (`pyotp`) with Chrome TLS impersonation (`curl_cffi`).
   - Executes 50ms REST requests (`POST /api/livestreams/{uuid}/audience/`).
3. **15s Global ↔ 5s Followers Audience Switcher (`services/audience_switcher.py`)**:
   - Async background task running the FYP traffic loop (`public` $\leftrightarrow$ `fans-and-followers`) with response state verification.
4. **5-Second Video End Stream Pauser (`services/stream_pauser.py`)**:
   - Handles 5-second video end alerts from local OBS agents, pausing F2F stream output for $X$ seconds delay before resuming.

---

## 📂 Proposed Component Files

```text
fastapi_server/
├── plan.md                             # This dedicated module plan
├── .env                                # F2F credentials, 2FA secrets, MongoDB Atlas URI
├── main.py                             # FastAPI entry point & WebSockets
├── requirements.txt                    # Dependencies (fastapi, uvicorn, curl_cffi, pyotp, motor)
├── core/
│   ├── config.py                       # Environment configuration schema
│   └── database.py                     # Cloud MongoDB Atlas connection manager
├── services/
│   ├── unreplied_scanner_service.py    # Unreplied fans scanner & Discord notification builder
│   ├── f2f_live_client.py              # Creator 2FA auth & F2F Live REST API engine
│   ├── audience_switcher.py            # 15s Global ↔ 5s Followers loop engine
│   └── stream_pauser.py                # 5s Video End Auto-Pause & Resume coordinator
└── routes/
    ├── api_routes.py                   # REST endpoints (/api/unreplied-fans, /api/obs-event)
    └── websocket_routes.py             # WebSockets for OBS Dock & Discord Mobile Hub
```

---

## ⚙️ REST & Discord Integration Points

- `GET /api/unreplied-fans`: Returns list of fans currently waiting for a reply.
- `POST /api/obs-event`: Webhook receiver for 5-second video end alerts from Windows VPS nodes.
- `POST /api/live/chat`: Dispatches a live stream comment on behalf of the creator (e.g. in Dutch).
- `POST /api/live/audience`: Toggles audience target between `public` and `fans-and-followers`.
