import os
import json
import time
import logging
import asyncio
import argparse
from aiohttp import web
import requests
import threading
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] OBSAgent: %(message)s"
)
logger = logging.getLogger("OBSAgent")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
BASE_VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "videos")
os.makedirs(BASE_VIDEOS_DIR, exist_ok=True)

# Parse command-line arguments for multi-instance support
parser = argparse.ArgumentParser(description="F2F OBS Agent Multi-Instance Server")
parser.add_argument("--creator", default=os.getenv("CREATOR", "xsophiex"), help="Creator username (e.g. xsophiex)")
parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")), help="HTTP server port")
parser.add_argument("--obs-port", type=int, default=int(os.getenv("OBS_PORT", "4455")), help="OBS WebSocket port")
parser.add_argument("--obs-password", default=os.getenv("OBS_PASSWORD", ""), help="OBS WebSocket password")
args, _ = parser.parse_known_args()

# Model-specific video folder (e.g. videos/xsophiex/ or fallback to videos/)
CREATOR_VIDEOS_DIR = os.path.join(BASE_VIDEOS_DIR, args.creator)
if os.path.exists(CREATOR_VIDEOS_DIR):
    VIDEOS_DIR = CREATOR_VIDEOS_DIR
else:
    VIDEOS_DIR = BASE_VIDEOS_DIR

def load_config():
    cfg = {
        "obs_host": "127.0.0.1",
        "obs_port": args.obs_port,
        "obs_password": args.obs_password,
        "selected_creator": args.creator,
        "creators": ["xsophiex", "chantalkuyt", "aylen", "sophie", "zoelynn", "chantalkuytmistress"],
        "pause_trigger_seconds": 5.0,
        "pause_duration_seconds": 10.0,
        "vps_server_url": "http://localhost:8000"
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
                # Override with CLI args if specified
                cfg["selected_creator"] = args.creator
                cfg["obs_port"] = args.obs_port
        except Exception:
            pass
    return cfg

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

active_ws_clients = set()
app_loop = None
camera_event_state = {
    "action": "none",
    "event_id": 0,
    "pause_delay": 10.0,
    "timestamp": 0,
    "chat_message": ""
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

    def list_available_videos(self):
        videos = []
        if os.path.exists(VIDEOS_DIR):
            for f in os.listdir(VIDEOS_DIR):
                if f.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")):
                    videos.append(f)
        return sorted(videos)

    def switch_video(self, video_name: str):
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return {"success": False, "error": "Not connected to OBS"}

        video_path = os.path.join(VIDEOS_DIR, video_name)
        if not os.path.exists(video_path):
            return {"success": False, "error": f"Video file '{video_name}' not found in {VIDEOS_DIR}"}

        try:
            input_name = self.current_media_input or self.find_active_media_input() or "Media"
            self.obs_client.set_input_settings(
                input_name,
                {"local_file": video_path},
                overlay=True
            )
            self.last_triggered_time = time.time()
            logger.info(f"🎬 Successfully switched OBS Media source '{input_name}' to: {video_name}")
            return {"success": True, "active_video": video_name, "input_name": input_name}
        except Exception as e:
            logger.error(f"Failed to switch video: {e}")
            return {"success": False, "error": str(e)}

    def start_virtual_cam(self):
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
        if self.obs_client:
            try:
                self.obs_client.start_virtual_cam()
                logger.info("🎥 OBS Virtual Camera started!")
                return {"success": True, "virtual_cam": "running"}
            except Exception as e:
                logger.error(f"Error starting virtual cam: {e}")
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "OBS not connected"}

    def stop_virtual_cam(self):
        if self.obs_client:
            try:
                self.obs_client.stop_virtual_cam()
                logger.info("⏹️ OBS Virtual Camera stopped.")
                return {"success": True, "virtual_cam": "stopped"}
            except Exception as e:
                logger.error(f"Error stopping virtual cam: {e}")
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "OBS not connected"}

    def find_chrome_profile_directory(self) -> str:
        """Auto-detects Chrome profile folder (e.g. 'Profile 1') for the model from Chrome's Local State."""
        local_state_path = os.path.expanduser("~/.config/google-chrome/Local State")
        if os.path.exists(local_state_path):
            try:
                with open(local_state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    info_cache = data.get("profile", {}).get("info_cache", {})
                    for prof_dir, prof_info in info_cache.items():
                        name = prof_info.get("name", "").lower()
                        user_name = prof_info.get("user_name", "").lower()
                        if self.active_creator.lower() in name or self.active_creator.lower() in user_name:
                            logger.info(f"🔍 Found Chrome Profile '{prof_dir}' matching creator @{self.active_creator}")
                            return prof_dir
            except Exception as e:
                logger.debug(f"Profile lookup note: {e}")
        return "Default"

    def get_active_display(self) -> str:
        """Finds the active X11 display (XRDP session :10.0 or local :0)."""
        if "DISPLAY" in os.environ and os.environ["DISPLAY"]:
            return os.environ["DISPLAY"]
        try:
            import glob
            sockets = glob.glob("/tmp/.X11-unix/X*")
            if sockets:
                nums = [s.split("X")[-1] for s in sockets]
                if "10" in nums:
                    return ":10.0"
                if "0" in nums:
                    return ":0"
                return f":{nums[-1]}.0"
        except Exception:
            pass
        return ":10.0"

    def _is_chrome_running_for_creator(self, creator: str) -> bool:
        """Check if Chrome is already running with this creator's dedicated data directory."""
        try:
            import subprocess
            result = subprocess.run(
                ["pgrep", "-a", "chrome"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if f"chrome-profiles/{creator}" in line or f"chrome-{creator}" in line:
                        return True
        except Exception:
            pass
        return False

    def ensure_browser_open(self):
        """Launches Google Chrome to F2F Live page with dedicated isolated profile per model.
        Uses --user-data-dir and --password-store=basic to guarantee 100% permanent login sessions."""
        try:
            creator = self.active_creator.lower()
            if self._is_chrome_running_for_creator(creator):
                logger.info(f"🌐 Chrome is already running for @{creator} — session preserved.")
                return

            import subprocess
            import platform
            system = platform.system()
            target_url = "https://f2f.com/live/"
            profile_dir = os.path.expanduser(f"~/.config/chrome-profiles/{creator}")
            os.makedirs(profile_dir, exist_ok=True)

            if system == "Linux":
                env = os.environ.copy()
                display = self.get_active_display()
                env["DISPLAY"] = display
                cmd = [
                    "google-chrome",
                    target_url,
                    f"--user-data-dir={profile_dir}",
                    "--password-store=basic",
                    "--use-fake-ui-for-media-stream",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-dev-shm-usage",
                    "--enable-gpu-rasterization",
                    "--ignore-gpu-blocklist",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding"
                ]
                subprocess.Popen(cmd, env=env)
                logger.info(f"🌐 Launched isolated Google Chrome for @{creator} (Dir: {profile_dir}) on DISPLAY={display}")
            elif system == "Darwin":
                cmd = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    target_url,
                    f"--user-data-dir={profile_dir}",
                    "--password-store=basic",
                    "--no-first-run",
                    "--no-default-browser-check"
                ]
                subprocess.Popen(cmd)
            elif system == "Windows":
                os.system(f'start chrome --user-data-dir="{profile_dir}" {target_url}')
        except Exception as e:
            logger.warning(f"Note on browser launch: {e}")

    def trigger_go_live(self, title: str = "", message: str = "", tip_goal: str = ""):
        self.ensure_browser_open()
        try:
            self.start_virtual_cam()
        except Exception as e:
            logger.warning(f"Virtual cam warning: {e}")
        camera_event_state["event_id"] += 1
        camera_event_state["action"] = "go_live"
        camera_event_state["title"] = title
        camera_event_state["message"] = message
        camera_event_state["tip_goal"] = tip_goal
        camera_event_state["timestamp"] = time.time()
        logger.info(f"🚀 Triggered 'Go Live' for @{self.active_creator} (Title: '{title}')")
        return {"success": True, "action": "go_live", "title": title}

    def trigger_end_stream(self):
        camera_event_state["event_id"] += 1
        camera_event_state["action"] = "end_stream"
        camera_event_state["timestamp"] = time.time()
        incoming_chat_queue.clear()
        self.stop_virtual_cam()
        logger.info(f"🛑 Triggered 'End Stream' for @{self.active_creator} — All live chat memory cleared.")
        return {"success": True, "action": "end_stream"}

    def send_live_chat(self, text: str):
        camera_event_state["event_id"] += 1
        camera_event_state["action"] = "send_chat"
        camera_event_state["chat_message"] = text
        camera_event_state["timestamp"] = time.time()
        broadcast_ws_event({
            "action": "send_chat",
            "text": text,
            "creator": self.active_creator
        })
        logger.info(f"💬 Dispatched live chat to F2F: '{text}'")
        return {"success": True, "message": text}

    def delete_live_chat(self, message_id: str = "", text: str = "", username: str = ""):
        camera_event_state["event_id"] += 1
        camera_event_state["action"] = "delete_chat"
        camera_event_state["delete_message_id"] = message_id
        camera_event_state["delete_text"] = text
        camera_event_state["delete_username"] = username
        camera_event_state["timestamp"] = time.time()
        broadcast_ws_event({
            "action": "delete_chat",
            "message_id": message_id,
            "text": text,
            "username": username,
            "creator": self.active_creator
        })
        logger.info(f"🗑️ Dispatched message deletion to F2F: id='{message_id}', text='{text}'")
        return {"success": True, "action": "delete_chat", "message_id": message_id}

# In-memory queue for incoming chats from browser
incoming_chat_queue = []

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
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })

async def handle_list_videos(request):
    videos = agent.list_available_videos()
    return web.json_response({"videos": videos, "count": len(videos)})

async def handle_switch_video(request):
    body = await request.json()
    video_name = body.get("video_name")
    if not video_name:
        return web.json_response({"success": False, "error": "No video_name provided"}, status=400)
    result = agent.switch_video(video_name)
    return web.json_response(result)

async def handle_go_live(request):
    body = await request.json() if request.can_read_body else {}
    title = body.get("title", "")
    msg = body.get("message", "")
    goal = body.get("tip_goal", "")
    res = agent.trigger_go_live(title=title, message=msg, tip_goal=goal)
    return web.json_response(res)

async def handle_end_stream(request):
    res = agent.trigger_end_stream()
    return web.json_response(res)

async def handle_virtual_cam_start(request):
    res = agent.start_virtual_cam()
    return web.json_response(res)

async def handle_virtual_cam_stop(request):
    res = agent.stop_virtual_cam()
    return web.json_response(res)

async def handle_send_chat(request):
    body = await request.json()
    msg = body.get("message") or body.get("text")
    if not msg:
        return web.json_response({"success": False, "error": "No message provided"}, status=400)
    res = agent.send_live_chat(msg)
    return web.json_response(res)

async def handle_delete_chat(request):
    body = await request.json()
    msg_id = body.get("message_id", "")
    text = body.get("text", "")
    username = body.get("username", "")
    res = agent.delete_live_chat(message_id=msg_id, text=text, username=username)
    return web.json_response(res)

chat_counter = 0

async def handle_incoming_chat(request):
    # DOM scraper chat input is permanently disabled. Live chat is handled by FastAPI.
    return web.json_response({"status": "disabled", "chat": None}, headers={"Access-Control-Allow-Origin": "*"})

async def handle_get_incoming_chats(request):
    # DOM scraper queue is permanently disabled. Live chat is handled by FastAPI.
    return web.json_response({"chats": [], "max_seq": 0, "timestamp": time.time()}, headers={"Access-Control-Allow-Origin": "*"})

async def handle_clear_incoming_chats(request):
    global chat_counter, incoming_chat_queue
    incoming_chat_queue.clear()
    chat_counter = 0
    logger.info("🧹 Cleared live chat queue and reset sequence counter.")
    return web.json_response({"status": "cleared", "count": 0}, headers={"Access-Control-Allow-Origin": "*"})

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

async def handle_obs_event(request):
    body = await request.json() if request.can_read_body else {}
    event_type = body.get("event", "video_ending")
    remaining_sec = float(body.get("remaining_sec", 5.0))
    media_name = body.get("media_name", "Media")
    logger.info(f"🚨 [OBS PLUGIN EVENT] Received '{event_type}' for @{agent.active_creator} ({remaining_sec:.1f}s remaining on '{media_name}')")
    if event_type == "video_ending":
        agent.trigger_video_end_event(remaining_sec)
    return web.json_response({"success": True, "event": event_type}, headers={"Access-Control-Allow-Origin": "*"})

def init_app():
    app = web.Application()
    app.cleanup_ctx.append(start_background_tasks)
    app.router.add_get("/", handle_dock)
    app.router.add_get("/dock", handle_dock)
    app.router.add_get("/dock_panel.html", handle_dock)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_get("/api/camera-event", handle_camera_event)
    app.router.add_get("/api/videos", handle_list_videos)
    app.router.add_post("/api/switch-video", handle_switch_video)
    app.router.add_post("/api/stream/go-live", handle_go_live)
    app.router.add_post("/api/stream/end", handle_end_stream)
    app.router.add_post("/api/virtual-cam/start", handle_virtual_cam_start)
    app.router.add_post("/api/virtual-cam/stop", handle_virtual_cam_stop)
    app.router.add_post("/api/send-chat", handle_send_chat)
    app.router.add_post("/api/stream/send-chat", handle_send_chat)
    app.router.add_post("/api/stream/delete-chat", handle_delete_chat)
    app.router.add_post("/api/incoming-chat", handle_incoming_chat)
    app.router.add_get("/api/stream/incoming-chats", handle_get_incoming_chats)
    app.router.add_get("/api/stream/clear-chats", handle_clear_incoming_chats)
    app.router.add_post("/api/stream/clear-chats", handle_clear_incoming_chats)
    app.router.add_post("/api/obs-event", handle_obs_event)
    app.router.add_post("/api/creator", handle_set_creator)
    app.router.add_get("/f2f_camera_controller.user.js", handle_userscript)
    app.router.add_get("/ws", handle_ws)
    return app

if __name__ == "__main__":
    logger.info(f"🚀 Starting OBS Agent Server for @{args.creator} on port {args.port} (OBS WebSocket port: {args.obs_port})...")
    agent.connect_obs()
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=args.port)
