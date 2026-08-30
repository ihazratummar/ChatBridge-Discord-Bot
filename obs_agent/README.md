# 🎬 F2F Live Manager - Native OBS Studio Plugin

A lightweight, standalone Python plugin that runs **100% inside OBS Studio**. Zero external processes, zero terminal windows.

---

## 🚀 How to Install & Use inside OBS Studio

1. Open **OBS Studio**.
2. Go to top menu: **`Tools` $\rightarrow$ `Scripts`**.
3. Under the **Scripts** tab:
   - Click the **`+` (Add)** button.
   - Select [`f2f_obs_plugin.py`](file:///Volumes/SSD/Coding/python/discord%20bot/ChatBridge/obs_agent/f2f_obs_plugin.py).
4. **Configure Properties directly in OBS**:
   - **Active Creator Model**: Pick the model from the dropdown (e.g. `@xsophiex`).
   - **FastAPI VPS Server URL**: Enter your FastAPI backend address (e.g. `http://YOUR_VPS_IP:8000`).
   - **Alert Threshold**: `5.0` seconds (default).
5. Click **"Send Test Webhook"** to verify connection to your FastAPI backend.

---

## ⚡ How it Operates:
- Runs natively inside OBS.
- Continuously monitors active Media Source video playback.
- When **5 seconds remain** on the video, it sends a non-blocking background HTTP POST request to your FastAPI server (`POST /api/obs-event`).
- When OBS Studio is closed, it unloads cleanly. When OBS Studio starts, it resumes automatically.
