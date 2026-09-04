"""
FastAPI Server for F2F Live Stream Automation & OBS Webhook Receiver.
Listens on http://127.0.0.1:8000 for events from OBS Studio native plugin.
"""

import os
import logging
import asyncio
import json
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
        "has_joined_room": getattr(client, "has_joined_room", False),
        "channel_name": client.active_channel_name,
        "livestream_uuid": client.active_livestream_uuid,
        "chat_seq_counter": client.chat_seq_counter,
        "queue_count": len(client.incoming_chat_queue),
        "last_raw_packet": getattr(client, "last_raw_packet", ""),
        "last_error": getattr(client, "last_error", ""),
        "last_packet_time": getattr(client, "last_packet_time", 0)
    }

@app.post("/api/live/chat/rejoin")
async def rejoin_live_chat_room(request: Request):
    """
    Forces immediate rediscovery and room join for creator's live stream.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    creator = data.get("creator", "xsophiex")
    client = live_chat_manager.get_client(creator)
    if not client.is_running:
        await client.start()
    
    # Re-fetch live channel & token
    channel_name, token = await client.get_live_details_and_token()
    target_channel = channel_name or client.creator_handle
    if client.ws and not client.ws.closed:
        join_packet = "42" + json.dumps(["livestream:chat:user:join", target_channel, client.chat_token or ""])
        await client.ws.send_str(join_packet)
        client.has_joined_room = True
        client.joined_channel_name = target_channel
        return {"success": True, "creator": creator, "room": target_channel, "chat_token": bool(client.chat_token)}
    return {"success": False, "error": "WebSocket not connected"}

@app.get("/api/live/diag")
async def diagnose_live(creator: str = "xsophiex"):
    """
    Runs an end-to-end diagnosis of creator session, livestream status, and live chat socket.
    """
    creator_client = creator_manager.get_or_create_creator(creator)
    client = live_chat_manager.get_client(creator)
    
    login_ok = creator_client.is_authenticated
    if not login_ok:
        login_ok = await creator_client.login()

    await creator_client._ensure_session()
    headers = creator_client._get_headers()
    cookies = creator_client._get_cookies()

    results = {
        "creator": creator,
        "is_authenticated": creator_client.is_authenticated,
        "socket_is_connected": client.is_connected,
        "socket_is_running": client.is_running,
        "has_joined_room": getattr(client, "has_joined_room", False),
        "active_channel_name": client.active_channel_name,
        "active_livestream_uuid": client.active_livestream_uuid,
        "chat_token_present": bool(client.chat_token),
        "chat_seq_counter": client.chat_seq_counter,
        "queue_count": len(client.incoming_chat_queue)
    }

    try:
        r1 = await creator_client.session.get(f"https://f2f.com/api/creators/{creator}/livestream/", headers=headers, cookies=cookies)
        results["livestream_api"] = {
            "status": r1.status_code,
            "data": r1.json() if r1.status_code == 200 else r1.text[:200]
        }
    except Exception as e:
        results["livestream_api"] = {"error": str(e)}

    try:
        r2 = await creator_client.session.get(f"https://f2f.com/api/creators/{creator}/livestream/chat/token", headers=headers, cookies=cookies)
        results["chat_token_api"] = {
            "status": r2.status_code,
            "data": r2.json() if r2.status_code == 200 else r2.text[:200]
        }
    except Exception as e:
        results["chat_token_api"] = {"error": str(e)}

    return results

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
    text = data.get("text", "")
    username = data.get("username", "")

    client = live_chat_manager.get_client(creator)
    if not message_id and (text or username):
        message_id = client.find_message_id(text=text, username=username)

    if not message_id:
        return {"success": False, "error": "No message_id provided and could not be resolved from active queue"}

    success = await client.delete_chat(message_id)
    return {"success": success, "creator": creator, "message_id": message_id}

@app.post("/api/live/chat/block")
async def block_live_chat_user(request: Request):
    """
    Bans/blocks a user from the active F2F live stream.
    Tries direct username ban, matches from active viewers list, and falls back to mute.
    """
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    username = (data.get("username") or "").strip().lstrip("@")
    if not username:
        return {"success": False, "error": "No username provided"}

    client = live_chat_manager.get_client(creator)
    creator_client = creator_manager.get_or_create_creator(creator)

    livestream_uuid = client.active_livestream_uuid
    if not livestream_uuid:
        await client.get_live_details_and_token()
        livestream_uuid = client.active_livestream_uuid

    if not livestream_uuid:
        return {"success": False, "error": "No active livestream found"}

    try:
        if not creator_client.is_authenticated:
            await creator_client.login()
        await creator_client._ensure_session()
        headers = creator_client._get_headers()
        cookies = creator_client._get_cookies()

        target_username = username

        # 1. Try to resolve exact account username from viewers list (in case username passed was display_name)
        try:
            viewers_url = f"https://f2f.com/api/livestreams/{livestream_uuid}/viewers/"
            r_v = await creator_client.session.get(viewers_url, headers=headers, cookies=cookies)
            if r_v.status_code == 200:
                v_data = r_v.json()
                results = v_data.get("results") or (v_data if isinstance(v_data, list) else [])
                for item in results:
                    u_obj = item.get("user") or {}
                    u_name = (u_obj.get("username") or "").lower()
                    d_name = (u_obj.get("display_name") or "").lower()
                    if username.lower() in (u_name, d_name):
                        target_username = u_obj.get("username") or username
                        logger.info(f"🎯 Matched viewer '{username}' -> exact F2F username '{target_username}'")
                        break
        except Exception as e:
            logger.debug(f"Viewer lookup note: {e}")

        # 2. Try POST .../viewers/{target_username}/ban/
        ban_url = f"https://f2f.com/api/livestreams/{livestream_uuid}/viewers/{target_username}/ban/"
        resp = await creator_client.session.post(ban_url, headers=headers, cookies=cookies)
        logger.info(f"🚫 [@{creator}] Ban request for viewer '{target_username}' (UUID: {livestream_uuid}): status {resp.status_code}")

        if resp.status_code in (200, 201, 204):
            return {"success": True, "creator": creator, "username": target_username, "action": "banned"}
        elif resp.status_code == 400 and "already" in resp.text.lower():
            return {"success": True, "creator": creator, "username": target_username, "note": "Already banned"}

        # 3. Fallback: Try POST .../viewers/{target_username}/mute/
        mute_url = f"https://f2f.com/api/livestreams/{livestream_uuid}/viewers/{target_username}/mute/"
        resp_mute = await creator_client.session.post(mute_url, headers=headers, cookies=cookies)
        logger.info(f"🔇 [@{creator}] Mute fallback for viewer '{target_username}': status {resp_mute.status_code}")

        if resp_mute.status_code in (200, 201, 204):
            return {"success": True, "creator": creator, "username": target_username, "action": "muted"}
        elif resp_mute.status_code == 400 and "already" in resp_mute.text.lower():
            return {"success": True, "creator": creator, "username": target_username, "note": "Already muted"}

        return {"success": False, "status_code": resp.status_code, "error": resp.text}
    except Exception as e:
        logger.error(f"❌ Exception banning/muting viewer '{username}': {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/live/chat/unban")
async def unban_live_chat_user(request: Request):
    """
    Unbans / unmutes a user from the creator's live stream and blocked list.
    """
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    username = (data.get("username") or "").strip().lstrip("@")
    if not username:
        return {"success": False, "error": "No username provided"}

    client = live_chat_manager.get_client(creator)
    creator_client = creator_manager.get_or_create_creator(creator)

    livestream_uuid = client.active_livestream_uuid
    if not livestream_uuid:
        await client.get_live_details_and_token()
        livestream_uuid = client.active_livestream_uuid

    if not creator_client.is_authenticated:
        await creator_client.login()
    await creator_client._ensure_session()
    headers = creator_client._get_headers()
    cookies = creator_client._get_cookies()

    actions_taken = []

    # 1. Try unban / unmute on livestream viewer endpoint
    if livestream_uuid:
        unban_urls = [
            f"https://f2f.com/api/livestreams/{livestream_uuid}/viewers/{username}/unban/",
            f"https://f2f.com/api/livestreams/{livestream_uuid}/viewers/{username}/mute/",  # Mute toggles unmuted state
        ]
        for u in unban_urls:
            try:
                r = await creator_client.session.post(u, headers=headers, cookies=cookies)
                if r.status_code in (200, 201, 204):
                    actions_taken.append(f"Livestream viewer unbanned ({r.status_code})")
                    break
            except Exception:
                pass

    # 2. Try creator account settings unblock endpoints
    creator_unblock_urls = [
        f"https://f2f.com/api/creators/{creator}/banned_users/{username}/",
        f"https://f2f.com/api/creators/{creator}/blocked_users/{username}/",
        f"https://f2f.com/api/users/{username}/unblock/",
    ]
    for u in creator_unblock_urls:
        try:
            r = await creator_client.session.delete(u, headers=headers, cookies=cookies)
            if r.status_code in (200, 204):
                actions_taken.append(f"Creator settings unblock ({r.status_code})")
        except Exception:
            pass

    return {
        "success": True,
        "creator": creator,
        "username": username,
        "actions_taken": actions_taken,
        "note": "Unban processed. Can also be unbanned directly in F2F Web -> Settings -> Creator Settings -> Banned Users."
    }

@app.get("/api/live/viewers")
async def get_live_viewers(creator: str = "xsophiex"):
    """
    Fetches the list of active viewers for the creator's current livestream.
    """
    creator_client = creator_manager.get_or_create_creator(creator)
    client = live_chat_manager.get_client(creator)
    if not creator_client.is_authenticated:
        await creator_client.login()
    await creator_client._ensure_session()
    headers = creator_client._get_headers()
    cookies = creator_client._get_cookies()
    uuid = client.active_livestream_uuid
    if not uuid:
        await client.get_live_details_and_token()
        uuid = client.active_livestream_uuid
    if not uuid:
        return {"error": "Not live"}
    url = f"https://f2f.com/api/livestreams/{uuid}/viewers/"
    resp = await creator_client.session.get(url, headers=headers, cookies=cookies)
    try:
        data = resp.json()
    except Exception:
        data = resp.text
    return {"status_code": resp.status_code, "data": data}

@app.post("/api/live/audience")
async def update_live_audience(request: Request):
    """
    Updates live stream audience target ('public', 'fans-and-followers', 'fans-only').
    """
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    target = data.get("target", "public")
    creator_client = creator_manager.get_or_create_creator(creator)
    success = await creator_client.set_audience(target)
    return {"success": success, "creator": creator, "target": target}

@app.post("/api/live/tipgoal")
async def update_live_tip_goal(request: Request):
    """
    Updates active live stream tip goal amount.
    """
    data = await request.json()
    creator = data.get("creator", "xsophiex")
    tip_goal = int(data.get("tip_goal", 50))
    creator_client = creator_manager.get_or_create_creator(creator)
    success = await creator_client.set_tip_goal(tip_goal)
    return {"success": success, "creator": creator, "tip_goal": tip_goal}

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
