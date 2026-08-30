import os
import json
import time
import logging
import asyncio
from aiohttp import web
import requests
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] OBSAgent: %(message)s"
)
logger = logging.getLogger("OBSAgent")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "obs_host": "127.0.0.1",
        "obs_port": 4455,
        "obs_password": "",
        "selected_creator": "xsophiex",
        "creators": ["xsophiex", "chantalkuyt", "aylen", "sophie"],
        "pause_trigger_seconds": 5.0,
        "pause_duration_seconds": 3.0,
        "vps_server_url": "http://localhost:8000"
    }

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

active_ws_clients = set()
app_loop = None
camera_event_state = {
    "action": "none",
    "event_id": 0,
    "pause_delay": 10.0,
    "timestamp": 0
}

def broadcast_ws_event(payload: dict):
    """Sends events to all connected F2F browser tabs"""
    global app_loop
    if not app_loop:
        return
    for ws in list(active_ws_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(payload), app_loop)
        except Exception:
            pass

class OBSAgentManager:
    def __init__(self):
        self.config = load_config()
        self.obs_client = None
        self.is_connected = False
        self.current_media_input = None
        self.last_triggered_time = 0
        self.active_creator = self.config.get("selected_creator", "xsophiex")

    def connect_obs(self):
        try:
            import obsws_python as obs
            host = self.config.get("obs_host", "127.0.0.1")
            port = int(self.config.get("obs_port", 4455))
            password = self.config.get("obs_password", "")

            self.obs_client = obs.ReqClient(host=host, port=port, password=password, timeout=3)
            self.is_connected = True
            logger.info(f"✅ Connected to OBS WebSocket at {host}:{port}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Could not connect to OBS WebSocket ({e}). Will retry...")
            self.is_connected = False
            self.obs_client = None
            return False

    def find_active_media_input(self):
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return None

        try:
            inputs = self.obs_client.get_input_list().inputs
            for inp in inputs:
                kind = inp.get("inputKind", "")
                if kind in ("ffmpeg_source", "vlc_source"):
                    return inp.get("inputName")
            if inputs:
                return inputs[0].get("inputName")
        except Exception as e:
            logger.warning(f"Error fetching inputs: {e}")
            self.is_connected = False
            self.obs_client = None
        return None

    def poll_media_status(self):
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return None

        try:
            if not self.current_media_input:
                self.current_media_input = self.find_active_media_input()

            if not self.current_media_input:
                return {"status": "no_media_source"}

            status = self.obs_client.get_media_input_status(self.current_media_input)
            duration_ms = status.media_duration if status.media_duration is not None else 0
            cursor_ms = status.media_cursor if status.media_cursor is not None else 0
            state = status.media_state

            if duration_ms <= 0:
                return {
                    "input_name": self.current_media_input,
                    "duration_sec": 0.0,
                    "cursor_sec": 0.0,
                    "remaining_sec": 0.0,
                    "state": state,
                    "active_creator": self.active_creator,
                    "is_connected": True
                }

            remaining_sec = max(0.0, (duration_ms - cursor_ms) / 1000.0)

            # Detect 5-second remaining boundary
            trigger_sec = self.config.get("pause_trigger_seconds", 5.0)
            now = time.time()
            if 0 < remaining_sec <= trigger_sec and (now - self.last_triggered_time) > (trigger_sec + 3):
                self.last_triggered_time = now
                self.trigger_video_end_event(remaining_sec)

            # Sync telemetry with central FastAPI server for the Dock UI
            vps_url = self.config.get("vps_server_url", "http://localhost:8000")
            try:
                requests.post(f"{vps_url}/api/obs-telemetry", json={
                    "creator": self.active_creator,
                    "media_name": self.current_media_input,
                    "duration_sec": duration_ms / 1000.0,
                    "remaining_sec": remaining_sec,
                    "state": "PLAYING" if state == "OBS_MEDIA_STATE_PLAYING" or state == 1 else str(state)
                }, timeout=0.5)
            except Exception:
                pass

            return {
                "input_name": self.current_media_input,
                "duration_sec": duration_ms / 1000.0,
                "cursor_sec": cursor_ms / 1000.0,
                "remaining_sec": remaining_sec,
                "state": state,
                "active_creator": self.active_creator,
                "is_connected": True
            }
        except Exception as e:
            logger.error(f"Error polling media status: {e}")
            if "connect" in str(e).lower() or "socket" in str(e).lower() or "broken" in str(e).lower():
                self.is_connected = False
                self.obs_client = None
            return {"status": "error", "error": str(e)}

    def _execute_camera_off_and_on(self, media_name: str, remaining_sec: float, pause_delay: float):
        try:
            logger.info(f"📷 [CAMERA OFF] Signaling F2F browser to turn camera OFF for {pause_delay}s (Loop reset)...")

            # 1. Update State & Broadcast to F2F Live Browser Tab
            camera_event_state["event_id"] += 1
            camera_event_state["action"] = "turn_camera_off"
            camera_event_state["pause_delay"] = pause_delay
            camera_event_state["timestamp"] = time.time()

            broadcast_ws_event({
                "action": "turn_camera_off",
                "pause_delay": pause_delay,
                "creator": self.active_creator,
                "remaining_sec": remaining_sec
            })

            # 2. Alert FastAPI server
            vps_url = self.config.get("vps_server_url", "http://localhost:8000")
            payload = {
                "event": "video_ending",
                "creator": self.active_creator,
                "remaining_sec": remaining_sec,
                "media_name": media_name,
                "pause_delay": pause_delay
            }
            try:
                requests.post(f"{vps_url}/api/obs-event", json=payload, timeout=2)
            except Exception:
                pass

            # 3. Wait 10 seconds while the video loops in OBS
            time.sleep(pause_delay)

            # 4. Turn camera back ON on F2F Live in the browser
            logger.info(f"📷 [CAMERA ON] Signaling F2F browser to turn camera ON for @{self.active_creator}!")
            camera_event_state["event_id"] += 1
            camera_event_state["action"] = "turn_camera_on"
            camera_event_state["timestamp"] = time.time()

            broadcast_ws_event({
                "action": "turn_camera_on",
                "creator": self.active_creator
            })

        except Exception as e:
            logger.error(f"Error during camera toggle: {e}")

    def trigger_video_end_event(self, remaining_sec):
        pause_delay = self.config.get("pause_duration_seconds", 10.0)
        logger.info(f"🚨 VIDEO END DETECTED ({remaining_sec:.1f}s remaining on '{self.current_media_input}')! Turning Camera OFF for {pause_delay}s...")
        threading.Thread(
            target=self._execute_camera_off_and_on,
            args=(self.current_media_input, remaining_sec, pause_delay),
            daemon=True
        ).start()

# Web Server & OBS Dock API Routes
agent = OBSAgentManager()

async def handle_status(request):
    data = agent.poll_media_status() or {"status": "disconnected"}
    return web.json_response(data)

async def handle_get_config(request):
    return web.json_response(agent.config)

async def handle_camera_event(request):
    return web.json_response(camera_event_state, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })

async def handle_set_creator(request):
    body = await request.json()
    new_creator = body.get("creator")
    if new_creator:
        agent.active_creator = new_creator
        agent.config["selected_creator"] = new_creator
        save_config(agent.config)
        logger.info(f"👤 Active creator changed to: @{new_creator}")
        return web.json_response({"success": True, "active_creator": new_creator})
    return web.json_response({"success": False, "error": "No creator provided"}, status=400)

async def handle_dock(request):
    html_path = os.path.join(os.path.dirname(__file__), "static", "dock_panel.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return web.Response(text="<h1>OBS Dock UI Not Found</h1>", content_type="text/html", status=404)

async def handle_userscript(request):
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "f2f_camera_controller.user.js"))
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="application/javascript")
    return web.Response(text="// Script not found", status=404)

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    active_ws_clients.add(ws)
    logger.info("🌐 [BROWSER SYNC] F2F Chrome Live tab connected to OBS Agent WebSocket!")
    try:
        async for msg in ws:
            pass
    finally:
        active_ws_clients.discard(ws)
        logger.info("🌐 [BROWSER SYNC] F2F Chrome Live tab disconnected.")
    return ws

async def background_obs_loop():
    while True:
        try:
            agent.poll_media_status()
        except Exception as e:
            logger.error(f"Background loop error: {e}")
        await asyncio.sleep(0.5)

async def start_background_tasks(app):
    global app_loop
    app_loop = asyncio.get_running_loop()
    app['obs_task'] = asyncio.create_task(background_obs_loop())
    yield
    app['obs_task'].cancel()
    try:
        await app['obs_task']
    except asyncio.CancelledError:
        pass

def init_app():
    app = web.Application()
    app.cleanup_ctx.append(start_background_tasks)
    app.router.add_get("/", handle_dock)
    app.router.add_get("/dock_panel.html", handle_dock)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_get("/api/camera-event", handle_camera_event)
    app.router.add_post("/api/set-creator", handle_set_creator)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/f2f_camera_controller.user.js", handle_userscript)
    return app

if __name__ == "__main__":
    logger.info("🚀 Starting OBS Agent Server on port 8080...")
    agent.connect_obs()
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=8080)
