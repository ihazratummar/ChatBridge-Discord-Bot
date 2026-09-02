"""
FastAPI Server for F2F Live Stream Automation & OBS Webhook Receiver.
Listens on http://127.0.0.1:8000 for events from OBS Studio native plugin.
"""

import os
import logging
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from services.f2f_live_service import creator_manager

# Configure rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] FastAPI-Live: %(message)s"
)
logger = logging.getLogger("FastAPI-Live")

app = FastAPI(title="F2F Live Stream Manager API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory status for live telemetry
live_status = {
    "active_creator": "xsophiex",
    "last_event": "none",
    "last_media_name": "none",
    "remaining_sec": 0.0,
    "total_events_received": 0,
    "f2f_stream_state": "READY"
}

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "FastAPI F2F Live Manager"}

@app.get("/api/status")
async def get_status():
    return JSONResponse(content=live_status)

@app.post("/api/obs-telemetry")
async def receive_obs_telemetry(request: Request):
    """
    Receives real-time video playback countdown from OBS Studio
    """
    data = await request.json()
    live_status["active_creator"] = data.get("creator", live_status.get("active_creator", "xsophiex"))
    live_status["input_name"] = data.get("media_name", "")
    live_status["duration_sec"] = data.get("duration_sec", 0.0)
    live_status["remaining_sec"] = data.get("remaining_sec", 0.0)
    live_status["state"] = data.get("state", "PLAYING")
    live_status["is_connected"] = True
    return {"status": "ok"}

@app.post("/api/set-creator")
async def set_creator(request: Request):
    data = await request.json()
    creator = data.get("creator")
    if creator:
        old_creator = live_status.get("active_creator")
        if old_creator and old_creator != creator:
            creator_manager.get_or_create_creator(old_creator).stop_fyp_loop()

        live_status["active_creator"] = creator
        logger.info(f"👤 Active creator switched to: @{creator}")
        new_client = creator_manager.get_or_create_creator(creator)
        asyncio.create_task(new_client.start_fyp_loop(global_sec=15, followers_sec=5))
        return {"status": "ok", "active_creator": creator}
    return {"status": "error", "message": "No creator specified"}

@app.get("/api/config")
async def get_config():
    return {
        "selected_creator": live_status.get("active_creator", "xsophiex"),
        "creators": ["xsophiex", "chantalkuyt", "aylen"]
    }

@app.post("/api/obs-event")
async def receive_obs_event(request: Request):
    """
    Receives real-time video playback events from OBS Studio f2f_obs_plugin.py
    """
    data = await request.json()
    event_type = data.get("event", "unknown")
    creator = data.get("creator", "unknown")
    remaining_sec = data.get("remaining_sec", 0.0)
    media_name = data.get("media_name", "unknown")

    live_status["active_creator"] = creator
    live_status["last_event"] = event_type
    live_status["last_media_name"] = media_name
    live_status["remaining_sec"] = remaining_sec
    live_status["total_events_received"] += 1

    if event_type == "video_ending":
        pause_delay = float(data.get("pause_delay", 10.0))
        logger.info(f"🚨 [OBS TRIGGER] Video ending in {remaining_sec}s on '{media_name}' for Creator @{creator}! Initiating {pause_delay}s pause cycle...")
        creator_client = creator_manager.get_or_create_creator(creator)
        asyncio.create_task(creator_client.handle_video_ending_pause(delay_sec=pause_delay))
        return {
            "status": "success",
            "action": "f2f_pause_dispatched",
            "creator": creator,
            "delay_sec": pause_delay
        }
    
    elif event_type == "test_ping":
        logger.info(f"🧪 [TEST PING] Connection verified from OBS for Creator @{creator}!")
        return {
            "status": "success",
            "message": f"Connection verified for @{creator}"
        }

    return {"status": "received", "data": data}

from services.f2f_live_socket_service import live_chat_manager

# ─── Direct Live Chat Endpoints (Zero-Latency Server-to-Server) ──
@app.get("/api/live/chat/incoming")
async def get_incoming_live_chats(creator: str = "xsophiex", since_seq: int = 0):
    """
    Returns new incoming live chat messages and tips for a creator model directly from F2F WebSocket.
    """
    client = live_chat_manager.get_client(creator)
    if not client.is_running:
        await client.start()
    chats = client.get_incoming_chats(since_seq=since_seq)
    return {
        "creator": creator,
        "chats": chats,
        "max_seq": client.chat_seq_counter,
        "is_connected": client.is_connected
    }

@app.get("/api/live/chat/debug")
async def get_live_chat_debug(creator: str = "xsophiex"):
    """
    Returns real-time telemetry of the live chat WebSocket connection.
    """
    client = live_chat_manager.get_client(creator)
    return {
        "creator": creator,
        "is_connected": client.is_connected,
        "is_running": client.is_running,
        "channel_name": client.active_channel_name,
        "livestream_uuid": client.active_livestream_uuid,
        "chat_seq_counter": client.chat_seq_counter,
        "queue_count": len(client.incoming_chat_queue),
        "last_raw_packet": getattr(client, "last_raw_packet", ""),
        "last_error": getattr(client, "last_error", ""),
        "last_packet_time": getattr(client, "last_packet_time", 0)
    }

@app.post("/api/live/chat/send")
async def send_live_chat_message(request: Request):
    """
    Dispatches a chat message to F2F Live stream directly over WebSocket.
    """
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    text = data.get("message") or data.get("text", "")
    if not text:
        return {"success": False, "error": "No message text provided"}

    client = live_chat_manager.get_client(creator)
    if not client.is_running:
        await client.start()
        await asyncio.sleep(1)

    success = await client.send_chat(text)
    return {"success": success, "creator": creator, "text": text}

@app.post("/api/live/chat/delete")
async def delete_live_chat_message(request: Request):
    """
    Deletes a message from F2F Live stream directly over WebSocket.
    """
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    message_id = data.get("message_id") or data.get("id", "")
    if not message_id:
        return {"success": False, "error": "No message_id provided"}

    client = live_chat_manager.get_client(creator)
    success = await client.delete_chat(message_id)
    return {"success": success, "creator": creator, "message_id": message_id}

@app.post("/api/live/chat/connect")
async def connect_live_chat_socket(request: Request):
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    client = live_chat_manager.get_client(creator)
    await client.start()
    return {"status": "started", "creator": creator}

@app.post("/api/live/chat/disconnect")
async def disconnect_live_chat_socket(request: Request):
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    client = live_chat_manager.get_client(creator)
    await client.stop()
    return {"status": "stopped", "creator": creator}

@app.get("/dock", response_class=HTMLResponse)
async def serve_dock():
    """
    Serves the Custom Browser Dock UI for OBS Studio.
    """
    dock_html_path = os.path.join(os.path.dirname(__file__), "..", "obs_agent", "static", "dock_panel.html")
    if os.path.exists(dock_html_path):
        with open(dock_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dock UI not found</h1>", status_code=404)

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting FYP Traffic Switcher Engine (15s Global / 5s Followers)...")
    creator = live_status.get("active_creator", "xsophiex")
    client = creator_manager.get_or_create_creator(creator)
    asyncio.create_task(client.start_fyp_loop(global_sec=15, followers_sec=5))
    logger.info("⚡ Starting Direct F2F Live Chat WebSocket Engine...")
    asyncio.create_task(live_chat_manager.start_all())

if __name__ == "__main__":
    logger.info("🚀 Starting FastAPI Server on http://0.0.0.0:8000 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, app_dir=os.path.dirname(__file__))
