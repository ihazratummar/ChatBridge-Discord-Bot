# FASTAPI SERVER MODULE PLAN (`fastapi_server/`)

Dedicated specification and architecture guide for the VPS-side FastAPI Backend and F2F Live Stream Automation Engine.

---

## 🎯 Purpose & Scope

The `fastapi_server/` module runs on the remote VPS server. It handles:
1. **F2F API Live Control Engine**: Executes 50ms HTTP REST API requests to F2F to toggle live stream audience settings (`POST /api/livestreams/{uuid}/audience/`) with full 2FA TOTP authentication (`pyotp`) and Chrome TLS impersonation (`curl_cffi`).
2. **15s Global ↔ 5s Followers Audience Switcher**: Background async loop cycling audience modes (15s `"public"` $\rightarrow$ 5s `"fans-and-followers"` $\rightarrow$ repeat) with live response state verification.
3. **5-Second Video End Auto-Pause Coordinator**: Receives `video_ending` webhooks from the local OBS Agent, pauses/mutes F2F stream output for a configurable $X$-second delay, then resumes playback.
4. **REST & WebSocket Control Endpoints**: Provides web API routes for the OBS Custom Browser Dock and live status telemetry.

---

## 📂 Proposed Component Files

```text
fastapi_server/
├── plan.md                       # This dedicated module plan
├── .env                          # F2F credentials, 2FA secret, MongoDB Atlas URI
├── main.py                       # FastAPI application entry point
├── requirements.txt              # Dependencies (fastapi, uvicorn, curl_cffi, pyotp, motor)
├── core/
│   ├── config.py                 # Environment Pydantic schema
│   └── database.py               # Cloud MongoDB Atlas connection manager
├── services/
│   ├── f2f_live_client.py        # curl_cffi client (2FA TOTP login & F2F REST API)
│   ├── audience_switcher.py      # 15s Global ↔ 5s Followers loop engine
│   └── stream_pauser.py          # 5s Video End Auto-Pause & Resume coordinator
└── routes/
    ├── api_routes.py             # REST API endpoints (/api/active-creator, /api/obs-event, etc.)
    └── websocket_routes.py       # Bi-directional WebSocket endpoint for OBS Dock UI
```

---

## ⚙️ Key Technical Features

### 1. F2F Live Client (`services/f2f_live_client.py`)
- Reuses `curl_cffi` AsyncSession with Chrome TLS fingerprinting.
- Autonomous 2FA TOTP login via `pyotp`.
- Methods:
  - `get_active_livestream_uuid(creator_handle: str) -> str`
  - `set_audience_mode(creator_handle: str, livestream_uuid: str, mode: str) -> bool`
    - `mode`: `"public"` (Global FYP preview) | `"fans-and-followers"` (Followers & Fans only)
  - `pause_stream_output(creator_handle: str, livestream_uuid: str)`
  - `resume_stream_output(creator_handle: str, livestream_uuid: str)`

### 2. Audience Switcher Loop (`services/audience_switcher.py`)
- Cycles:
  1. `POST /api/livestreams/{uuid}/audience/` with `{"target": "public"}` $\rightarrow$ Sleep 15s.
  2. `POST /api/livestreams/{uuid}/audience/` with `{"target": "fans-and-followers"}` $\rightarrow$ Sleep 5s.
- **Response State Verification**: Verifies response JSON `{"target": mode}`. If F2F glitches or returns HTTP error, retries immediately.

### 3. Video End Stream Pauser (`services/stream_pauser.py`)
- Triggered by `POST /api/obs-event` (`event: "video_ending"`).
- Pauses F2F output/audio.
- Waits configurable delay ($X$ seconds).
- Resumes F2F output once new video begins.

---

## 🛠️ REST API Endpoints (`routes/api_routes.py`)

- `POST /api/active-creator`: Updates active creator model handle.
- `POST /api/obs-event`: Webhook receiver for 5-second video end alerts from client's PC.
- `POST /api/audience-loop/start`: Starts 15s/5s audience toggle loop for creator.
- `POST /api/audience-loop/stop`: Stops 15s/5s audience toggle loop.
- `WebSocket /ws/dock`: Real-time telemetry feed for OBS Dock UI.
