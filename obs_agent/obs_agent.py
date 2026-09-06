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
import base64
from typing import Dict, List, Optional

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

# Auto-create model subfolder (e.g. videos/xsophiex/)
CREATOR_VIDEOS_DIR = os.path.join(BASE_VIDEOS_DIR, args.creator)
os.makedirs(CREATOR_VIDEOS_DIR, exist_ok=True)
VIDEOS_DIR = CREATOR_VIDEOS_DIR

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
        self.current_video_file = None
        self._cached_transform = {"flipped_h": False, "flipped_v": False}
        self._last_transform_check = 0
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

    def get_active_video_name(self, input_name: str = None) -> str:
        """Retrieves the exact filename of the video currently loaded in OBS Media source."""
        if getattr(self, "current_video_file", None):
            return self.current_video_file
        target = input_name or self.current_media_input or "Media"
        if self.is_connected and self.obs_client:
            try:
                res = self.obs_client.get_input_settings(target)
                settings = getattr(res, "input_settings", {})
                if isinstance(settings, dict):
                    local_file = settings.get("local_file", "")
                    if local_file:
                        file_name = os.path.basename(local_file)
                        self.current_video_file = file_name
                        return file_name
                    playlist = settings.get("playlist", [])
                    if isinstance(playlist, list) and playlist:
                        first_item = playlist[0]
                        if isinstance(first_item, dict) and first_item.get("value"):
                            file_name = os.path.basename(first_item["value"])
                            self.current_video_file = file_name
                            return file_name
            except Exception:
                pass
        return target

    def find_scene_item(self, source_name: str = None):
        """Finds (scene_name, item_id) for the target source across program scene or scene list."""
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return None, None

        target = source_name or self.current_media_input or self.find_active_media_input() or "Media"

        # 1. Try active program scene first
        try:
            cur = self.obs_client.get_current_program_scene()
            scene_name = getattr(cur, "current_program_scene_name", None) or getattr(cur, "scene_name", None)
            if scene_name:
                try:
                    item_res = self.obs_client.get_scene_item_id(scene_name, target)
                    item_id = getattr(item_res, "scene_item_id", None)
                    if item_id is not None:
                        return scene_name, item_id
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Search through all available scenes
        try:
            scene_list = self.obs_client.get_scene_list()
            scenes = getattr(scene_list, "scenes", [])
            for sc in scenes:
                s_name = sc.get("sceneName") if isinstance(sc, dict) else getattr(sc, "scene_name", None)
                if not s_name:
                    continue
                try:
                    item_res = self.obs_client.get_scene_item_id(s_name, target)
                    item_id = getattr(item_res, "scene_item_id", None)
                    if item_id is not None:
                        return s_name, item_id
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Scene item search note: {e}")

        return None, None

    def get_transform_status(self, source_name: str = None) -> dict:
        """Returns the current orientation and scale of the target source."""
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return {"flipped_h": False, "flipped_v": False, "connected": False}

        scene_name, item_id = self.find_scene_item(source_name)
        if not scene_name or item_id is None:
            return {"flipped_h": False, "flipped_v": False, "error": "Scene item not found"}

        try:
            res = self.obs_client.get_scene_item_transform(scene_name, item_id)
            transform = getattr(res, "scene_item_transform", {})
            if isinstance(transform, dict):
                scale_x = float(transform.get("scaleX", 1.0))
                scale_y = float(transform.get("scaleY", 1.0))
            else:
                scale_x = float(getattr(transform, "scale_x", 1.0))
                scale_y = float(getattr(transform, "scale_y", 1.0))

            status = {
                "flipped_h": scale_x < 0,
                "flipped_v": scale_y < 0,
                "scale_x": scale_x,
                "scale_y": scale_y,
                "scene_name": scene_name,
                "item_id": item_id
            }
            self._cached_transform = status
            return status
        except Exception as e:
            logger.debug(f"Error getting transform: {e}")
            return {"flipped_h": False, "flipped_v": False, "error": str(e)}

    def flip_source(self, direction: str = "horizontal", source_name: str = None) -> dict:
        """Toggles horizontal or vertical flip on the target OBS source."""
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return {"success": False, "error": "Not connected to OBS"}

        target = source_name or self.current_media_input or self.find_active_media_input() or "Media"
        scene_name, item_id = self.find_scene_item(target)
        if not scene_name or item_id is None:
            return {"success": False, "error": f"Source '{target}' not found in any OBS scene"}

        try:
            res = self.obs_client.get_scene_item_transform(scene_name, item_id)
            transform = getattr(res, "scene_item_transform", {})
            if not isinstance(transform, dict):
                transform = {
                    "scaleX": getattr(transform, "scale_x", 1.0),
                    "scaleY": getattr(transform, "scale_y", 1.0),
                    "positionX": getattr(transform, "position_x", 0.0),
                    "positionY": getattr(transform, "position_y", 0.0),
                    "alignment": getattr(transform, "alignment", 5),
                    "boundsType": getattr(transform, "bounds_type", "OBS_BOUNDS_NONE"),
                    "width": getattr(transform, "width", 0.0),
                    "height": getattr(transform, "height", 0.0),
                    "sourceWidth": getattr(transform, "source_width", 1920),
                    "sourceHeight": getattr(transform, "source_height", 1080),
                }

            cur_scale_x = float(transform.get("scaleX", 1.0))
            cur_scale_y = float(transform.get("scaleY", 1.0))
            cur_pos_x = float(transform.get("positionX", 0.0))
            cur_pos_y = float(transform.get("positionY", 0.0))
            alignment = int(transform.get("alignment", 5))
            bounds_type = str(transform.get("boundsType", "OBS_BOUNDS_NONE"))

            width = float(transform.get("width", 0.0))
            if width <= 0:
                width = float(transform.get("sourceWidth", 1920)) * abs(cur_scale_x)

            height = float(transform.get("height", 0.0))
            if height <= 0:
                height = float(transform.get("sourceHeight", 1080)) * abs(cur_scale_y)

            update_payload = {}
            dir_lower = direction.lower()

            if "horiz" in dir_lower or dir_lower == "h":
                new_scale_x = -cur_scale_x
                update_payload["scaleX"] = new_scale_x
                if bounds_type == "OBS_BOUNDS_NONE":
                    if alignment & 1:  # Left-aligned anchor
                        delta_x = width if new_scale_x < 0 else -width
                        update_payload["positionX"] = cur_pos_x + delta_x
                    elif alignment & 2:  # Right-aligned anchor
                        delta_x = -width if new_scale_x < 0 else width
                        update_payload["positionX"] = cur_pos_x + delta_x

            elif "vert" in dir_lower or dir_lower == "v":
                new_scale_y = -cur_scale_y
                update_payload["scaleY"] = new_scale_y
                if bounds_type == "OBS_BOUNDS_NONE":
                    if alignment & 4:  # Top-aligned anchor
                        delta_y = height if new_scale_y < 0 else -height
                        update_payload["positionY"] = cur_pos_y + delta_y
                    elif alignment & 8:  # Bottom-aligned anchor
                        delta_y = -height if new_scale_y < 0 else height
                        update_payload["positionY"] = cur_pos_y + delta_y
            else:
                return {"success": False, "error": f"Invalid flip direction: '{direction}'. Use 'horizontal' or 'vertical'"}

            self.obs_client.set_scene_item_transform(scene_name, item_id, update_payload)

            resulting_scale_x = update_payload.get("scaleX", cur_scale_x)
            resulting_scale_y = update_payload.get("scaleY", cur_scale_y)
            status = {
                "success": True,
                "direction": "horizontal" if "horiz" in dir_lower or dir_lower == "h" else "vertical",
                "flipped_h": resulting_scale_x < 0,
                "flipped_v": resulting_scale_y < 0,
                "scale_x": resulting_scale_x,
                "scale_y": resulting_scale_y,
                "source_name": target,
                "scene_name": scene_name
            }
            self._cached_transform = status
            logger.info(f"🔄 Flipped OBS Source '{target}' ({status['direction']}) in scene '{scene_name}' (Flipped H: {status['flipped_h']}, Flipped V: {status['flipped_v']})")
            return status

        except Exception as e:
            logger.error(f"Failed to flip source transform: {e}")
            return {"success": False, "error": str(e)}

    def toggle_obs_preview(self, enable: bool = None) -> Dict:
        """Enables or disables the visual canvas preview in OBS Studio on the VPS."""
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return {"success": False, "error": "Not connected to OBS"}

        try:
            current_state = getattr(self, "obs_preview_enabled", True)
            target_state = (not current_state) if enable is None else bool(enable)

            hotkey = "OBSBasic.EnablePreview" if target_state else "OBSBasic.DisablePreview"
            self.obs_client.trigger_hotkey_by_name(hotkey)

            self.obs_preview_enabled = target_state
            logger.info(f"🖥️ [OBS PREVIEW] Canvas Preview set to: {'ENABLED' if target_state else 'DISABLED'}")
            return {"success": True, "preview_enabled": target_state}
        except Exception as e:
            logger.error(f"Failed toggling OBS preview: {e}")
            return {"success": False, "error": str(e)}

    def get_obs_preview_status(self) -> Dict:
        """Returns the current OBS canvas preview status."""
        return {
            "success": True,
            "preview_enabled": getattr(self, "obs_preview_enabled", True)
        }

    def get_preview_image(self, source_name: str = None, width: int = 960, height: int = 540, quality: int = 85):
        """Captures a real-time JPEG snapshot frame of the active video playback or scene from OBS."""
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return None

        target = source_name or self.current_media_input or self.find_active_media_input() or "Media"

        # 1. Try taking screenshot of the target media input source
        try:
            res = self.obs_client.get_source_screenshot(target, "jpeg", width, height, quality)
            img_data = getattr(res, "image_data", None) or (res.get("imageData") if isinstance(res, dict) else None)
            if img_data:
                if "," in img_data:
                    img_data = img_data.split(",", 1)[1]
                return base64.b64decode(img_data)
        except Exception as e:
            logger.debug(f"Source screenshot note ({target}): {e}")

        # 2. Fallback: Try taking screenshot of the active program scene
        try:
            cur = self.obs_client.get_current_program_scene()
            scene_name = getattr(cur, "current_program_scene_name", None) or getattr(cur, "scene_name", None)
            if scene_name:
                res = self.obs_client.get_source_screenshot(scene_name, "jpeg", width, height, quality)
                img_data = getattr(res, "image_data", None) or (res.get("imageData") if isinstance(res, dict) else None)
                if img_data:
                    if "," in img_data:
                        img_data = img_data.split(",", 1)[1]
                    return base64.b64decode(img_data)
        except Exception as e:
            logger.debug(f"Scene screenshot note: {e}")

        return None

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

            # Periodically refresh transform status every 3 seconds
            now = time.time()
            if (now - getattr(self, "_last_transform_check", 0)) > 3.0:
                self._last_transform_check = now
                self.get_transform_status()

            active_video = self.get_active_video_name(self.current_media_input)
            cached_tr = getattr(self, "_cached_transform", {})
            flipped_h = cached_tr.get("flipped_h", False)
            flipped_v = cached_tr.get("flipped_v", False)

            if duration_ms <= 0:
                return {
                    "input_name": self.current_media_input,
                    "active_video": active_video,
                    "duration_sec": 0.0,
                    "cursor_sec": 0.0,
                    "remaining_sec": 0.0,
                    "state": state,
                    "active_creator": self.active_creator,
                    "is_connected": True,
                    "flipped_h": flipped_h,
                    "flipped_v": flipped_v
                }

            remaining_sec = max(0.0, (duration_ms - cursor_ms) / 1000.0)

            # Detect 5-second remaining boundary
            trigger_sec = self.config.get("pause_trigger_seconds", 5.0)
            if 0 < remaining_sec <= trigger_sec and (now - self.last_triggered_time) > (trigger_sec + 3):
                self.last_triggered_time = now
                self.trigger_video_end_event(remaining_sec)

            # Sync telemetry with central FastAPI server for the Dock UI
            vps_url = self.config.get("vps_server_url", "http://localhost:8000")
            try:
                requests.post(f"{vps_url}/api/obs-telemetry", json={
                    "creator": self.active_creator,
                    "media_name": self.current_media_input,
                    "active_video": active_video,
                    "duration_sec": duration_ms / 1000.0,
                    "remaining_sec": remaining_sec,
                    "state": "PLAYING" if state == "OBS_MEDIA_STATE_PLAYING" or state == 1 else str(state),
                    "flipped_h": flipped_h,
                    "flipped_v": flipped_v
                }, timeout=0.5)
            except Exception:
                pass

            return {
                "input_name": self.current_media_input,
                "active_video": active_video,
                "duration_sec": duration_ms / 1000.0,
                "cursor_sec": cursor_ms / 1000.0,
                "remaining_sec": remaining_sec,
                "state": state,
                "active_creator": self.active_creator,
                "is_connected": True,
                "flipped_h": flipped_h,
                "flipped_v": flipped_v,
                "obs_preview_enabled": getattr(self, "obs_preview_enabled", True)
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

    def get_creator_videos_dir(self) -> str:
        creator = self.config.get("selected_creator", args.creator)
        c_dir = os.path.join(BASE_VIDEOS_DIR, creator)
        os.makedirs(c_dir, exist_ok=True)
        return c_dir

    def list_available_videos(self):
        videos = set()
        # 1. Check creator-specific folder (e.g. videos/xsophiex/)
        c_dir = self.get_creator_videos_dir()
        if os.path.exists(c_dir):
            for f in os.listdir(c_dir):
                if f.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")):
                    videos.add(f)

        # 2. Check shared root folder (videos/) for common clips
        if os.path.exists(BASE_VIDEOS_DIR):
            for f in os.listdir(BASE_VIDEOS_DIR):
                if os.path.isfile(os.path.join(BASE_VIDEOS_DIR, f)) and f.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")):
                    videos.add(f)

        return sorted(list(videos))

    def switch_video(self, video_name: str):
        if not self.is_connected or not self.obs_client:
            self.connect_obs()
            if not self.is_connected:
                return {"success": False, "error": "Not connected to OBS"}

        c_dir = self.get_creator_videos_dir()
        # 1. Search in creator-specific folder
        video_path = os.path.join(c_dir, video_name)
        if not os.path.exists(video_path):
            # 2. Search in shared root folder
            video_path = os.path.join(BASE_VIDEOS_DIR, video_name)

        if not os.path.exists(video_path):
            return {"success": False, "error": f"Video file '{video_name}' not found in {c_dir} or {BASE_VIDEOS_DIR}"}

        try:
            input_name = self.current_media_input or self.find_active_media_input() or "Media"
            self.obs_client.set_input_settings(
                input_name,
                {"local_file": video_path},
                overlay=True
            )
            self.last_triggered_time = time.time()
            self.current_video_file = video_name
            logger.info(f"🎬 Successfully switched OBS Media source '{input_name}' to: {video_name} ({video_path})")
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

    def get_x11_gui_env(self) -> dict:
        """Dynamically inspects the active visible GUI session to extract the true DISPLAY and XAUTHORITY.
        Inspects running OBS Studio and desktop processes first, since OBS is guaranteed to be on the visible screen."""
        env = os.environ.copy()
        display = env.get("DISPLAY")
        xauth = env.get("XAUTHORITY")

        # 1. First priority: Check running GUI processes (OBS Studio, desktop environments, RustDesk, etc.)
        gui_processes = ["obs", "obs64", "xfce4-session", "gnome-shell", "x-session-manager", "rustdesk", "lightdm", "Xorg"]
        import subprocess
        for proc in gui_processes:
            if display and xauth:
                break
            try:
                pids = subprocess.check_output(["pgrep", "-f", proc], text=True, timeout=2).strip().split()
                for pid in pids:
                    environ_file = f"/proc/{pid}/environ"
                    if os.path.exists(environ_file):
                        try:
                            with open(environ_file, "rb") as f:
                                raw = f.read().split(b"\0")
                                p_env = {}
                                for entry in raw:
                                    if b"=" in entry:
                                        k, v = entry.split(b"=", 1)
                                        try:
                                            p_env[k.decode("latin1", errors="ignore")] = v.decode("latin1", errors="ignore")
                                        except Exception:
                                            pass
                                if not display and p_env.get("DISPLAY"):
                                    display = p_env["DISPLAY"]
                                    logger.info(f"🖥️ Detected visible DISPLAY={display} from process '{proc}' (PID {pid})")
                                if not xauth and p_env.get("XAUTHORITY"):
                                    xauth = p_env["XAUTHORITY"]
                                    logger.info(f"🔑 Detected XAUTHORITY={xauth} from process '{proc}' (PID {pid})")
                                if display and xauth:
                                    break
                        except Exception:
                            continue
            except Exception:
                continue

        # 2. If DISPLAY not found from processes, check active X11 sockets in /tmp/.X11-unix/
        if not display:
            try:
                import glob
                sockets = glob.glob("/tmp/.X11-unix/X*")
                if sockets:
                    nums = [s.split("X")[-1] for s in sockets]
                    # Prioritize local display :0 or :1 before XRDP :10
                    if "0" in nums:
                        display = ":0"
                    elif "1" in nums:
                        display = ":1"
                    elif "10" in nums:
                        display = ":10.0"
                    else:
                        display = f":{nums[0]}"
            except Exception:
                pass

        if not display:
            display = ":0"

        # 3. Fallback for XAUTHORITY if still missing
        if not xauth:
            possible_auths = [
                os.path.expanduser("~/.Xauthority"),
                "/root/.Xauthority",
                f"/run/user/{os.getuid()}/gdm/Xauthority" if hasattr(os, "getuid") else ""
            ]
            for p in possible_auths:
                if p and os.path.exists(p):
                    xauth = p
                    break

        env["DISPLAY"] = display
        if xauth:
            env["XAUTHORITY"] = xauth

        # Authorize root on X server if xhost is available
        try:
            subprocess.run(["xhost", "+local:root"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
        except Exception:
            pass

        return env

    def get_active_display(self) -> str:
        """Finds the active X11 display."""
        env = self.get_x11_gui_env()
        return env.get("DISPLAY", ":0")

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
        """Ensures Google Chrome is open and navigated to F2F Live page with dedicated isolated profile per model.
        Uses --user-data-dir and --password-store=basic to guarantee 100% permanent login sessions.
        If Chrome is already running, passes target URL to the active instance and focuses window."""
        try:
            creator = self.active_creator.lower()
            target_url = "https://f2f.com/live/"
            profile_dir = os.path.expanduser(f"~/.config/chrome-profiles/{creator}")
            os.makedirs(profile_dir, exist_ok=True)

            is_running = self._is_chrome_running_for_creator(creator)

            # If not running, clean up any stale lock that might prevent Chrome from starting
            if not is_running:
                lock_file = os.path.join(profile_dir, "SingletonLock")
                if os.path.islink(lock_file) or os.path.exists(lock_file):
                    try:
                        os.unlink(lock_file)
                        logger.info(f"🧹 Cleaned orphaned Chrome SingletonLock for @{creator}")
                    except Exception as e:
                        logger.debug(f"SingletonLock cleanup note: {e}")

            import subprocess
            import platform
            import shutil
            system = platform.system()

            if system == "Linux":
                env = self.get_x11_gui_env()
                display = env.get("DISPLAY", ":0")

                chrome_bin = (
                    shutil.which("google-chrome") or
                    shutil.which("google-chrome-stable") or
                    shutil.which("chromium-browser") or
                    shutil.which("chromium") or
                    "/usr/bin/google-chrome"
                )

                cmd = [
                    chrome_bin,
                    target_url,
                    f"--user-data-dir={profile_dir}",
                    "--password-store=basic",
                    "--disable-features=WebRTCPipeWireCapturer",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-dev-shm-usage",
                    "--enable-gpu-rasterization",
                    "--ignore-gpu-blocklist",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding"
                ]

                # Root execution on Linux strictly requires --no-sandbox
                try:
                    if os.geteuid() == 0:
                        cmd.append("--no-sandbox")
                except AttributeError:
                    cmd.append("--no-sandbox")

                subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

                # If Chrome was already running, attempt to bring the window to front using wmctrl or xdotool
                if is_running:
                    logger.info(f"🌐 Navigated existing Chrome session for @{creator} to {target_url} on DISPLAY={display}")
                    try:
                        subprocess.run(["wmctrl", "-a", "Google Chrome"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
                    except Exception:
                        pass
                else:
                    logger.info(f"🌐 Launched fresh isolated Google Chrome for @{creator} (Dir: {profile_dir}) on DISPLAY={display}")

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

    def close_f2f_browser_tab(self):
        """OS-level safety net: attempts to close the F2F Live Chrome tab if still open."""
        try:
            import subprocess
            import platform
            if platform.system() == "Linux":
                env = self.get_x11_gui_env()
                try:
                    out = subprocess.check_output(
                        ["xdotool", "search", "--onlyvisible", "--name", "Live.*Chrome|F2F.*Chrome|Chrome.*Live|f2f.com/live"],
                        env=env, text=True, timeout=2
                    ).strip()
                    for wid in out.split():
                        subprocess.run(
                            ["xdotool", "windowactivate", "--sync", wid, "key", "--clearmodifiers", "ctrl+w"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
                        )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Note on tab close helper: {e}")

    def trigger_end_stream(self):
        camera_event_state["event_id"] += 1
        camera_event_state["action"] = "end_stream"
        camera_event_state["timestamp"] = time.time()
        incoming_chat_queue.clear()
        broadcast_ws_event({"action": "end_stream", "creator": self.active_creator})

        # Graceful shutdown: give the browser 2.5 seconds to cleanly execute end-stream and close tab BEFORE cutting OBS virtual camera
        import threading
        def delayed_stop_cam():
            time.sleep(2.5)
            self.stop_virtual_cam()
            self.close_f2f_browser_tab()
            logger.info(f"🛑 Cleanly stopped OBS Virtual Cam and closed F2F tab for @{self.active_creator}")

        threading.Thread(target=delayed_stop_cam, daemon=True).start()
        logger.info(f"🛑 Triggered 'End Stream' for @{self.active_creator} — Broadcast closing.")
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
    data = agent.poll_media_status() or {"status": "disconnected", "is_connected": False}
    if isinstance(data, dict) and "is_connected" not in data:
        data["is_connected"] = bool(agent.is_connected)
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

async def handle_open_browser(request):
    agent.ensure_browser_open()
    return web.json_response({"success": True, "action": "open_browser", "creator": agent.active_creator})

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
    global chat_counter, incoming_chat_queue
    try:
        body = await request.json()
        chat_counter += 1
        chat_data = {
            "seq_id": chat_counter,
            "id": body.get("id") or f"obs_{chat_counter}_{int(time.time()*1000)}",
            "username": (body.get("username") or "Fan").strip(),
            "text": (body.get("text") or body.get("content") or "").strip(),
            "type": body.get("type", "chat"),
            "tip_amount": float(body.get("tip_amount", 0) or 0),
            "timestamp": time.time()
        }
        incoming_chat_queue.append(chat_data)
        if len(incoming_chat_queue) > 200:
            incoming_chat_queue = incoming_chat_queue[-200:]
        return web.json_response({"status": "ok", "seq_id": chat_counter, "chat": chat_data}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=400, headers={"Access-Control-Allow-Origin": "*"})

async def handle_get_incoming_chats(request):
    global chat_counter, incoming_chat_queue
    try:
        since_seq = int(request.query.get("since_seq", 0))
    except (ValueError, TypeError):
        since_seq = 0
    chats = [c for c in incoming_chat_queue if c.get("seq_id", 0) > since_seq]
    return web.json_response({"chats": chats, "max_seq": chat_counter, "timestamp": time.time()}, headers={"Access-Control-Allow-Origin": "*"})

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

async def handle_flip_horizontal(request):
    body = await request.json() if request.can_read_body else {}
    source_name = body.get("source_name")
    res = agent.flip_source(direction="horizontal", source_name=source_name)
    return web.json_response(res, headers={"Access-Control-Allow-Origin": "*"})

async def handle_flip_vertical(request):
    body = await request.json() if request.can_read_body else {}
    source_name = body.get("source_name")
    res = agent.flip_source(direction="vertical", source_name=source_name)
    return web.json_response(res, headers={"Access-Control-Allow-Origin": "*"})

async def handle_transform_flip(request):
    body = await request.json() if request.can_read_body else {}
    direction = body.get("direction", "horizontal")
    source_name = body.get("source_name")
    res = agent.flip_source(direction=direction, source_name=source_name)
    return web.json_response(res, headers={"Access-Control-Allow-Origin": "*"})

async def handle_transform_status(request):
    source_name = request.query.get("source_name")
    res = agent.get_transform_status(source_name=source_name)
    return web.json_response(res, headers={"Access-Control-Allow-Origin": "*"})

async def handle_preview_image(request):
    source_name = request.query.get("source_name")
    try:
        w = int(request.query.get("width", 960))
        h = int(request.query.get("height", 540))
        q = int(request.query.get("quality", 85))
    except (ValueError, TypeError):
        w, h, q = 960, 540, 85

    img_bytes = agent.get_preview_image(source_name=source_name, width=w, height=h, quality=q)
    if img_bytes:
        return web.Response(
            body=img_bytes,
            content_type="image/jpeg",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    return web.json_response({"success": False, "error": "Could not capture OBS preview"}, status=503)

async def handle_toggle_obs_preview(request):
    body = await request.json() if request.can_read_body else {}
    enable = body.get("enable")
    res = agent.toggle_obs_preview(enable=enable)
    return web.json_response(res, headers={"Access-Control-Allow-Origin": "*"})

async def handle_obs_preview_status(request):
    res = agent.get_obs_preview_status()
    return web.json_response(res, headers={"Access-Control-Allow-Origin": "*"})

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
    app.router.add_get("/api/preview", handle_preview_image)
    app.router.add_get("/api/preview.jpg", handle_preview_image)
    app.router.add_get("/api/screenshot", handle_preview_image)
    app.router.add_post("/api/obs-preview/toggle", handle_toggle_obs_preview)
    app.router.add_get("/api/obs-preview/status", handle_obs_preview_status)
    app.router.add_post("/api/switch-video", handle_switch_video)
    app.router.add_post("/api/flip-horizontal", handle_flip_horizontal)
    app.router.add_post("/api/flip-vertical", handle_flip_vertical)
    app.router.add_post("/api/transform/flip", handle_transform_flip)
    app.router.add_get("/api/transform/status", handle_transform_status)
    app.router.add_post("/api/stream/open-browser", handle_open_browser)
    app.router.add_get("/api/stream/open-browser", handle_open_browser)
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
