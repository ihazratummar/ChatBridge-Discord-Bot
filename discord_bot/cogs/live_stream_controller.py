"""
Live Stream Controller Cog - ChatBridge & F2F Automation
Built using Discord UI LayoutView (Components V2) Architecture
Provides interactive phone control for Starting/Stopping streams,
switching preloaded videos in real-time, and relaying live chat comments.
"""

import os
import re
import io
import json
import time
import logging
import aiohttp
import asyncio
from typing import List, Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger("LiveStreamController")

# Mapping of creator model handles to their respective VPS / agent URLs
DEFAULT_VPS_ENDPOINTS = {
    "xsophiex": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_XSOPHIEX", "http://159.69.64.80:8081"),
        "fastapi_url": os.getenv("FASTAPI_URL_XSOPHIEX", "http://77.237.241.68:8000"),
        "obs_ws_port": int(os.getenv("OBS_WS_PORT_XSOPHIEX", "4455")),
    },
    "chantalkuyt": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_CHANTALKUYT", "http://159.69.64.80:8082"),
        "fastapi_url": os.getenv("FASTAPI_URL_CHANTALKUYT", "http://77.237.241.68:8000"),
        "obs_ws_port": int(os.getenv("OBS_WS_PORT_CHANTALKUYT", "4456")),
    },
    "aylen": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_AYLEN", "http://159.69.64.80:8083"),
        "fastapi_url": os.getenv("FASTAPI_URL_AYLEN", "http://77.237.241.68:8000"),
        "obs_ws_port": int(os.getenv("OBS_WS_PORT_AYLEN", "4457")),
    },
    "zoelynn": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_ZOELYNN", "http://159.69.64.80:8084"),
        "fastapi_url": os.getenv("FASTAPI_URL_ZOELYNN", "http://77.237.241.68:8000"),
        "obs_ws_port": int(os.getenv("OBS_WS_PORT_ZOELYNN", "4458")),
    },
    "chantalkuytmistress": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_CHANTALKUYTMISTRESS", "http://159.69.64.80:8085"),
        "fastapi_url": os.getenv("FASTAPI_URL_CHANTALKUYTMISTRESS", "http://77.237.241.68:8000"),
        "obs_ws_port": int(os.getenv("OBS_WS_PORT_CHANTALKUYTMISTRESS", "4459")),
    }
}


class LiveStreamAPIService:
    """Helper to communicate with individual VPS OBS Agents and FastAPI servers."""

    VIDEOS_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "videos_cache.json")
    _cached_videos: Dict[str, List[str]] = {}
    _obs_preview_xsophiex: bool = True
    _obs_preview_chantalkuyt: bool = True
    _obs_preview_aylen: bool = True
    _obs_preview_zoelynn: bool = True
    _obs_preview_chantalkuytmistress: bool = True

    @classmethod
    def _load_cached_videos(cls) -> Dict[str, List[str]]:
        try:
            if os.path.exists(cls.VIDEOS_CACHE_PATH):
                with open(cls.VIDEOS_CACHE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        cls._cached_videos = {k: list(v) for k, v in data.items() if isinstance(v, list)}
        except Exception as e:
            logger.debug(f"Error loading videos cache: {e}")
        return cls._cached_videos

    @classmethod
    def _save_cached_videos(cls):
        try:
            os.makedirs(os.path.dirname(cls.VIDEOS_CACHE_PATH), exist_ok=True)
            with open(cls.VIDEOS_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cls._cached_videos, f, indent=2)
        except Exception as e:
            logger.debug(f"Error saving videos cache: {e}")

    @classmethod
    def add_video_to_cache(cls, creator: str, video_name: str) -> List[str]:
        if not video_name or video_name in ["No Media Active", "Media"]:
            return cls._cached_videos.get(creator.lower().replace("@", "").strip(), [])
        creator_clean = creator.lower().replace("@", "").strip()
        cls._load_cached_videos()
        vids = cls._cached_videos.setdefault(creator_clean, [])
        if video_name not in vids:
            vids.append(video_name)
            vids.sort()
            cls._save_cached_videos()
        return vids

    @staticmethod
    def get_endpoints(creator: str) -> Dict[str, str]:
        creator_clean = creator.lower().replace("@", "").strip()
        return DEFAULT_VPS_ENDPOINTS.get(creator_clean, {
            "obs_agent_url": "http://127.0.0.1:8080",
            "fastapi_url": "http://127.0.0.1:8000"
        })

    @classmethod
    async def _send_obs_ws_request(cls, host: str, port: int, request_type: str, request_data: Optional[Dict] = None, timeout: float = 6.0) -> Dict:
        """Direct pure aiohttp WebSocket call to OBS Studio (port 4455), requiring NO external libraries."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"ws://{host}:{port}", timeout=timeout) as ws:
                    await ws.receive_json()
                    await ws.send_json({"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 0}})
                    await ws.receive_json()

                    req_id = f"req_{int(time.time()*1000)}"
                    req_payload = {
                        "op": 6,
                        "d": {
                            "requestType": request_type,
                            "requestId": req_id,
                            "requestData": request_data or {}
                        }
                    }
                    await ws.send_json(req_payload)
                    for _ in range(15):
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        if msg.get("op") == 7 and msg.get("d", {}).get("requestId") == req_id:
                            d = msg.get("d", {})
                            if d.get("requestStatus", {}).get("result"):
                                return {"success": True, "data": d.get("responseData", {})}
                            else:
                                return {"success": False, "error": d.get("requestStatus", {}).get("comment", "Request failed")}
                    return {"success": False, "error": "Timeout waiting for OBS response"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    async def _get_obs_status_direct(cls, host: str, port: int = 4455, creator: str = "xsophiex", timeout: float = 3.0) -> Dict:
        """Direct OBS WebSocket status fetcher using pure aiohttp. Zero external dependencies."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"ws://{host}:{port}", timeout=timeout) as ws:
                    await ws.receive_json()
                    await ws.send_json({"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 0}})
                    await ws.receive_json()

                    # 1. Media Input Status
                    await ws.send_json({
                        "op": 6,
                        "d": {"requestType": "GetMediaInputStatus", "requestId": "media_stat", "requestData": {"inputName": "Media"}}
                    })
                    r1 = await ws.receive_json()
                    media_data = r1.get("d", {}).get("responseData", {})

                    # 2. Media Input Settings
                    await ws.send_json({
                        "op": 6,
                        "d": {"requestType": "GetInputSettings", "requestId": "media_settings", "requestData": {"inputName": "Media"}}
                    })
                    r2 = await ws.receive_json()
                    settings_data = r2.get("d", {}).get("responseData", {})

                    # 3. Scene items & Transform
                    flipped_h = False
                    flipped_v = False
                    try:
                        await ws.send_json({"op": 6, "d": {"requestType": "GetCurrentProgramScene", "requestId": "scene_cur"}})
                        r3 = await ws.receive_json()
                        scene_name = r3.get("d", {}).get("responseData", {}).get("currentProgramSceneName", "Scene")

                        await ws.send_json({
                            "op": 6,
                            "d": {"requestType": "GetSceneItemList", "requestId": "scene_items", "requestData": {"sceneName": scene_name}}
                        })
                        r4 = await ws.receive_json()
                        items = r4.get("d", {}).get("responseData", {}).get("sceneItems", [])
                        for item in items:
                            if item.get("sourceName") == "Media":
                                t = item.get("sceneItemTransform", {})
                                flipped_h = t.get("scaleX", 1.0) < 0
                                flipped_v = t.get("scaleY", 1.0) < 0
                                break
                    except Exception:
                        pass

                    # 4. Stream status
                    is_streaming = False
                    try:
                        await ws.send_json({"op": 6, "d": {"requestType": "GetStreamStatus", "requestId": "stream_stat"}})
                        r5 = await ws.receive_json()
                        is_streaming = r5.get("d", {}).get("responseData", {}).get("outputActive", False)
                    except Exception:
                        pass

                    local_file = settings_data.get("inputSettings", {}).get("local_file", "")
                    filename = os.path.basename(local_file) if local_file else "No Media Active"
                    if filename and filename not in ["No Media Active", "Media"]:
                        cls.add_video_to_cache(creator, filename)
                    dur_sec = float(media_data.get("mediaDuration", 0) or 0) / 1000.0
                    cur_sec = float(media_data.get("mediaCursor", 0) or 0) / 1000.0
                    rem_sec = max(0.0, dur_sec - cur_sec)
                    obs_preview_enabled = getattr(cls, f"_obs_preview_{creator}", True)

                    return {
                        "input_name": "Media",
                        "active_video": filename,
                        "duration_sec": dur_sec,
                        "cursor_sec": cur_sec,
                        "remaining_sec": rem_sec,
                        "state": media_data.get("mediaState", "OBS_MEDIA_STATE_PLAYING" if dur_sec > 0 else "OBS_MEDIA_STATE_STOPPED"),
                        "flipped_h": flipped_h,
                        "flipped_v": flipped_v,
                        "obs_preview_enabled": obs_preview_enabled,
                        "is_streaming": is_streaming,
                        "is_connected": True,
                        "status": "online"
                    }
        except Exception as e:
            logger.debug(f"Direct OBS WS status fetch failed for {host}:{port}: {e}")
            return {"status": "offline", "is_connected": False, "error": str(e)}

    @classmethod
    async def get_status(cls, creator: str) -> Dict:
        ep = cls.get_endpoints(creator)
        creator_clean = creator.lower().replace("@", "").strip()
        obs_port = ep.get("obs_ws_port", 4455)
        # 1. Primary: Try OBS Agent HTTP server on that model's dedicated port
        try:
            to = aiohttp.ClientTimeout(total=0.8, connect=0.5)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.get(f"{ep['obs_agent_url']}/api/status") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, dict) and "is_connected" not in data:
                            data["is_connected"] = (data.get("status") not in ("disconnected", "offline", "no_media_source"))
                        return data
        except Exception as e:
            logger.debug(f"Error fetching status from {ep['obs_agent_url']}: {e}")

        # 2. Resilient Direct Fallback: Native OBS WebSocket on that model's dedicated port
        import urllib.parse
        parsed = urllib.parse.urlparse(ep['obs_agent_url'])
        host = parsed.hostname or "159.69.64.80"
        return await cls._get_obs_status_direct(host, obs_port, creator_clean)

    @classmethod
    async def list_videos(cls, creator: str) -> List[str]:
        ep = cls.get_endpoints(creator)
        creator_clean = creator.lower().replace("@", "").strip()
        cls._load_cached_videos()
        try:
            to = aiohttp.ClientTimeout(total=2.0, connect=1.0)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.get(f"{ep['obs_agent_url']}/api/videos") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        vids = data.get("videos", [])
                        cls._cached_videos[creator_clean] = vids
                        cls._save_cached_videos()
                        return vids
        except Exception as e:
            logger.debug(f"Error fetching videos from agent for {creator_clean}: {e}")
        return cls._cached_videos.get(creator_clean, [])

    @classmethod
    async def switch_video(cls, creator: str, video_name: str) -> Dict:
        ep = cls.get_endpoints(creator)
        creator_clean = creator.lower().replace("@", "").strip()
        obs_port = ep.get("obs_ws_port", 4455)
        # 1. Try OBS Agent HTTP server
        try:
            to = aiohttp.ClientTimeout(total=3.0, connect=2.0)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/switch-video",
                    json={"video_name": video_name}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass

        # 2. Resilient Direct Fallback: Native OBS WebSocket on that model's dedicated port
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(ep['obs_agent_url'])
            host = parsed.hostname or "159.69.64.80"
            target_path = f"/root/Desktop/obs_agent/videos/{creator_clean}/{video_name}"
            res = await cls._send_obs_ws_request(host, obs_port, "SetInputSettings", {
                "inputName": "Media",
                "inputSettings": {"local_file": target_path}
            })
            if res.get("success"):
                return {"success": True, "video": video_name}
            return {"success": False, "error": res.get("error", "Switch failed")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    async def _flip_source_obs_ws(cls, host: str, port: int, direction: str = "horizontal", source_name: str = "Media") -> Dict:
        """Flips source horizontally or vertically directly via OBS WebSocket."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"ws://{host}:{port}", timeout=3.0) as ws:
                    await ws.receive_json()
                    await ws.send_json({"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 0}})
                    await ws.receive_json()

                    await ws.send_json({"op": 6, "d": {"requestType": "GetCurrentProgramScene", "requestId": "scene_cur"}})
                    r1 = await ws.receive_json()
                    scene_name = r1.get("d", {}).get("responseData", {}).get("currentProgramSceneName", "Scene")

                    await ws.send_json({"op": 6, "d": {"requestType": "GetSceneItemList", "requestId": "scene_items", "requestData": {"sceneName": scene_name}}})
                    r2 = await ws.receive_json()
                    items = r2.get("d", {}).get("responseData", {}).get("sceneItems", [])
                    
                    target_item = None
                    for item in items:
                        if item.get("sourceName") == source_name:
                            target_item = item
                            break
                    if not target_item:
                        return {"success": False, "error": f"Source '{source_name}' not found"}

                    item_id = target_item.get("sceneItemId")
                    t = target_item.get("sceneItemTransform", {})
                    scale_x = float(t.get("scaleX", 1.0))
                    scale_y = float(t.get("scaleY", 1.0))

                    new_transform = {}
                    if "horiz" in direction.lower() or direction.lower() == "h":
                        new_scale_x = -scale_x
                        new_transform["scaleX"] = new_scale_x
                        flipped_h = new_scale_x < 0
                        flipped_v = scale_y < 0
                    else:
                        new_scale_y = -scale_y
                        new_transform["scaleY"] = new_scale_y
                        flipped_h = scale_x < 0
                        flipped_v = new_scale_y < 0

                    await ws.send_json({
                        "op": 6,
                        "d": {
                            "requestType": "SetSceneItemTransform",
                            "requestId": "set_transform",
                            "requestData": {
                                "sceneName": scene_name,
                                "sceneItemId": item_id,
                                "sceneItemTransform": new_transform
                            }
                        }
                    })
                    r3 = await ws.receive_json()
                    status = r3.get("d", {}).get("requestStatus", {})
                    if status.get("result"):
                        return {"success": True, "flipped_h": flipped_h, "flipped_v": flipped_v}
                    return {"success": False, "error": status.get("comment", "Transform update failed")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    async def flip_horizontal(cls, creator: str, source_name: str = "Media") -> Dict:
        ep = cls.get_endpoints(creator)
        try:
            to = aiohttp.ClientTimeout(total=0.6, connect=0.4)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/flip-horizontal",
                    json={"source_name": source_name}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass

        # Fallback to direct OBS WebSocket
        import urllib.parse
        parsed = urllib.parse.urlparse(ep['obs_agent_url'])
        host = parsed.hostname or "159.69.64.80"
        obs_port = ep.get("obs_ws_port", 4455)
        return await cls._flip_source_obs_ws(host, obs_port, direction="horizontal", source_name=source_name)

    @classmethod
    async def flip_vertical(cls, creator: str, source_name: str = "Media") -> Dict:
        ep = cls.get_endpoints(creator)
        try:
            to = aiohttp.ClientTimeout(total=0.6, connect=0.4)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/flip-vertical",
                    json={"source_name": source_name}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass

        # Fallback to direct OBS WebSocket
        import urllib.parse
        parsed = urllib.parse.urlparse(ep['obs_agent_url'])
        host = parsed.hostname or "159.69.64.80"
        obs_port = ep.get("obs_ws_port", 4455)
        return await cls._flip_source_obs_ws(host, obs_port, direction="vertical", source_name=source_name)

    @classmethod
    async def get_transform_status(cls, creator: str, source_name: str = "Media") -> Dict:
        ep = cls.get_endpoints(creator)
        creator_clean = creator.lower().replace("@", "").strip()
        obs_port = ep.get("obs_ws_port", 4455)
        try:
            to = aiohttp.ClientTimeout(total=0.6, connect=0.4)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.get(
                    f"{ep['obs_agent_url']}/api/transform/status?source_name={source_name}"
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass

        # Fallback via direct OBS WS status
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(ep['obs_agent_url'])
            host = parsed.hostname or "159.69.64.80"
            st = await cls._get_obs_status_direct(host, obs_port, creator_clean)
            if st.get("is_connected"):
                return {"flipped_h": st.get("flipped_h", False), "flipped_v": st.get("flipped_v", False)}
        except Exception:
            pass
        return {"flipped_h": False, "flipped_v": False}

    @classmethod
    async def get_preview_image(cls, creator: str, source_name: str = "Media") -> Optional[bytes]:
        ep = cls.get_endpoints(creator)
        try:
            to = aiohttp.ClientTimeout(total=0.8, connect=0.4)
            async with aiohttp.ClientSession(timeout=to) as session:
                ts = int(time.time() * 1000)
                async with session.get(
                    f"{ep['obs_agent_url']}/api/preview.jpg?source_name={source_name}&t={ts}"
                ) as resp:
                    if resp.status == 200 and resp.headers.get("content-type", "").startswith("image/"):
                        return await resp.read()
        except Exception as e:
            logger.debug(f"Error fetching preview image for {creator}: {e}")
        return None

    @classmethod
    async def toggle_obs_preview(cls, creator: str, enable: Optional[bool] = None) -> Dict:
        """Enables or disables the visual canvas preview in OBS Studio on the VPS."""
        ep = cls.get_endpoints(creator)
        creator_clean = creator.lower().replace("@", "").strip()
        # 1. Primary: Try OBS Agent HTTP endpoint (8081)
        try:
            to = aiohttp.ClientTimeout(total=0.6, connect=0.4)
            async with aiohttp.ClientSession(timeout=to) as session:
                payload = {}
                if enable is not None:
                    payload["enable"] = enable
                async with session.post(
                    f"{ep['obs_agent_url']}/api/obs-preview/toggle",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        setattr(cls, f"_obs_preview_{creator_clean}", data.get("preview_enabled", True))
                        return data
        except Exception:
            pass

        # 2. Resilient Direct Fallback: Direct OBS WebSocket using pure aiohttp
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(ep['obs_agent_url'])
            host = parsed.hostname or "159.69.64.80"
            port = ep.get("obs_ws_port", 4455)
            current_state = getattr(cls, f"_obs_preview_{creator_clean}", True)
            target_state = (not current_state) if enable is None else bool(enable)
            hotkey = "OBSBasic.EnablePreview" if target_state else "OBSBasic.DisablePreview"
            res = await cls._send_obs_ws_request(host, port, "TriggerHotkeyByName", {"hotkeyName": hotkey})

            if res.get("success"):
                setattr(cls, f"_obs_preview_{creator_clean}", target_state)
                return {"success": True, "preview_enabled": target_state}
            else:
                err = res.get("error") or "OBS hotkey request failed or timed out"
                return {"success": False, "error": err}
        except Exception as e:
            return {"success": False, "error": str(e) or type(e).__name__ or "Unknown error"}

    @classmethod
    async def get_obs_preview_status(cls, creator: str) -> bool:
        ep = cls.get_endpoints(creator)
        creator_clean = creator.lower().replace("@", "").strip()
        try:
            to = aiohttp.ClientTimeout(total=0.6, connect=0.4)
            async with aiohttp.ClientSession(timeout=to) as session:
                async with session.get(
                    f"{ep['obs_agent_url']}/api/obs-preview/status"
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("preview_enabled", True)
        except Exception:
            pass
        return getattr(cls, f"_obs_preview_{creator_clean}", True)

    @classmethod
    async def toggle_virtual_cam(cls, creator: str, start: bool = True) -> Dict:
        ep = cls.get_endpoints(creator)
        action = "start" if start else "stop"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{ep['obs_agent_url']}/api/virtual-cam/{action}", timeout=3) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def toggle_camera(cls, creator: str) -> Dict:
        """Toggles the camera ON/OFF on F2F Live via the OBS Agent."""
        ep = cls.get_endpoints(creator)
        obs_agent_url = ep.get('obs_agent_url')
        if obs_agent_url:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(f"{obs_agent_url}/api/stream/toggle-camera", timeout=3) as resp:
                        if resp.status == 200:
                            return await resp.json()
                except Exception as e:
                    logger.debug(f"Failed to toggle camera via OBS Agent: {e}")
        return {"success": False, "error": "OBS Agent unavailable"}

    @classmethod
    async def toggle_fyp_loop(cls, creator: str) -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{ep['fastapi_url']}/api/start-loop", timeout=3) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def send_live_chat(cls, creator: str, message: str) -> Dict:
        ep = cls.get_endpoints(creator)
        obs_agent_url = ep.get('obs_agent_url')
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')

        async with aiohttp.ClientSession() as session:
            # 1. Primary: Direct VPS OBS Agent -> Browser Userscript (works for camera on/off, e.g. Sophie and Aylen)
            if obs_agent_url:
                try:
                    async with session.post(
                        f"{obs_agent_url}/api/send-chat",
                        json={"message": message},
                        timeout=4
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                return data
                except Exception as e:
                    logger.warning(f"Failed dispatching chat to OBS Agent for {creator}: {e}")

            # 2. Fallback: FastAPI Live API
            urls = [fastapi_url]
            if "127.0.0.1" not in fastapi_url and "localhost" not in fastapi_url:
                urls.append("http://127.0.0.1:8000")

            for u in urls:
                try:
                    async with session.post(
                        f"{u}/api/live/chat/send",
                        json={"creator": creator, "message": message},
                        timeout=4
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                except Exception:
                    continue

        return {"success": False, "error": "All live chat dispatch backends failed"}

    @classmethod
    async def delete_live_chat(cls, creator: str, message_id: str = "", text: str = "", username: str = "") -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        obs_agent_url = ep.get('obs_agent_url')

        async with aiohttp.ClientSession() as session:
            # 1. Primary for active streams: Try VPS OBS Agent (authoritative for browser DOM & live WebSocket)
            if obs_agent_url:
                try:
                    async with session.post(
                        f"{obs_agent_url}/api/stream/delete-chat",
                        json={"message_id": message_id, "text": text, "username": username},
                        timeout=3
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                logger.info(f"🗑️ [@{creator}] Deleted live chat via OBS Agent: '{text}'")
                                return data
                except Exception as e:
                    logger.debug(f"OBS Agent delete attempt failed: {e}")

            # 2. Server-to-Server Fallback: FastAPI Live Socket
            urls = [fastapi_url]
            if "127.0.0.1" not in fastapi_url and "localhost" not in fastapi_url:
                urls.append("http://127.0.0.1:8000")

            for u in urls:
                try:
                    async with session.post(
                        f"{u}/api/live/chat/delete",
                        json={"creator": creator, "message_id": message_id, "text": text, "username": username},
                        timeout=3
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                logger.info(f"🗑️ [@{creator}] Deleted live chat via FastAPI: '{text}'")
                                return data
                except Exception:
                    continue

        return {"success": False, "error": "All delete backends failed"}

    @classmethod
    async def block_live_user(cls, creator: str, username: str, text: str = "") -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        obs_agent_url = ep.get('obs_agent_url')

        clean_user = re.sub(r'(?i)\b(follower|subscriber|vip|moderator)\b', '', username).strip().lstrip("@")
        clean_user = clean_user.split("\n")[0].strip()

        results = []
        async with aiohttp.ClientSession() as session:
            # 1. Primary for active streams: Try VPS OBS Agent (browser DOM & WebSocket block)
            if obs_agent_url:
                try:
                    async with session.post(
                        f"{obs_agent_url}/api/stream/block-user",
                        json={"creator": creator, "username": clean_user, "text": text},
                        timeout=3
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                logger.info(f"🚫 [@{creator}] Blocked live user via OBS Agent: @{clean_user}")
                                results.append(data)
                except Exception as e:
                    logger.debug(f"OBS Agent block attempt note: {e}")

            # 2. Dual-Layer: Also dispatch to FastAPI (for creator account settings ban & stream viewer ban)
            urls = [fastapi_url]
            if "127.0.0.1" not in fastapi_url and "localhost" not in fastapi_url:
                urls.append("http://127.0.0.1:8000")

            for u in urls:
                try:
                    async with session.post(
                        f"{u}/api/live/chat/block",
                        json={"creator": creator, "username": clean_user},
                        timeout=4
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("success"):
                                logger.info(f"🚫 [@{creator}] Blocked live user via FastAPI: @{clean_user}")
                                results.append(data)
                                break
                except Exception:
                    continue

        if results:
            return {"success": True, "creator": creator, "username": clean_user}
        return {"success": False, "error": "All block backends failed"}

    @classmethod
    async def unban_live_user(cls, creator: str, username: str) -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/chat/unban",
                    json={"creator": creator, "username": username},
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def set_audience(cls, creator: str, target: str) -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/audience",
                    json={"creator": creator, "target": target},
                    timeout=5
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def set_tip_goal(cls, creator: str, tip_goal: int) -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/tipgoal",
                    json={"creator": creator, "tip_goal": tip_goal},
                    timeout=5
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def rejoin_live_chat(cls, creator: str) -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        urls = [fastapi_url]
        if "127.0.0.1" not in fastapi_url and "localhost" not in fastapi_url:
            urls.append("http://127.0.0.1:8000")

        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.post(
                        f"{url}/api/live/chat/rejoin",
                        json={"creator": creator},
                        timeout=4
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                except Exception:
                    continue
        return {"success": False}

    @classmethod
    async def get_obs_incoming_chats(cls, creator: str, since_seq: int = 0) -> tuple:
        """Fetches incoming chats from the VPS OBS Agent (authoritative for OBS streams)."""
        ep = cls.get_endpoints(creator)
        obs_agent_url = ep.get('obs_agent_url')
        if not obs_agent_url:
            return [], since_seq

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{obs_agent_url}/api/stream/incoming-chats?since_seq={since_seq}",
                    timeout=3
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("chats", []), data.get("max_seq", since_seq)
            except Exception:
                pass
        return [], since_seq

    @classmethod
    async def get_fastapi_incoming_chats(cls, creator: str, since_seq: int = 0) -> tuple:
        """Fetches incoming chats from FastAPI (authoritative for non-OBS creators like Aylen)."""
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        urls = [fastapi_url]
        if "127.0.0.1" not in fastapi_url and "localhost" not in fastapi_url:
            urls.append("http://127.0.0.1:8000")

        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(
                        f"{url}/api/live/chat/incoming?creator={creator}&since_seq={since_seq}",
                        timeout=3
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get("chats", []), data.get("max_seq", since_seq)
                except Exception:
                    continue
        return [], since_seq

    @classmethod
    async def get_incoming_chats(cls, creator: str, since_seq: int = 0) -> tuple:
        """Authoritative live chat poller: queries VPS OBS Agent first (sub-second userscript WebSocket relay), falls back to FastAPI."""
        ep = cls.get_endpoints(creator)
        obs_agent_url = ep.get('obs_agent_url')

        # 1. Primary: VPS OBS Agent (direct browser userscript WebSocket interceptor on VPS)
        if obs_agent_url:
            try:
                to = aiohttp.ClientTimeout(total=2.5, connect=1.2)
                async with aiohttp.ClientSession(timeout=to) as session:
                    async with session.get(
                        f"{obs_agent_url}/api/stream/incoming-chats?since_seq={since_seq}"
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get("chats", []), data.get("max_seq", since_seq)
            except Exception:
                pass

        # 2. Fallback: Central FastAPI Live Socket Relay
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        urls = [fastapi_url]
        if "127.0.0.1" not in fastapi_url and "localhost" not in fastapi_url:
            urls.append("http://127.0.0.1:8000")

        to = aiohttp.ClientTimeout(total=2.5, connect=1.2)
        async with aiohttp.ClientSession(timeout=to) as session:
            for url in urls:
                try:
                    async with session.get(
                        f"{url}/api/live/chat/incoming?creator={creator}&since_seq={since_seq}"
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get("chats", []), data.get("max_seq", since_seq)
                except Exception:
                    continue

        return [], since_seq


    @classmethod
    async def go_live(cls, creator: str, title: str, message: str = "", tip_goal: str = "") -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/stream/go-live",
                    json={"title": title, "message": message, "tip_goal": tip_goal},
                    timeout=5
                ) as resp:
                    # Also launch FYP loop
                    try:
                        await session.post(f"{ep['fastapi_url']}/api/start-loop", timeout=2)
                    except Exception:
                        pass
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def end_stream(cls, creator: str) -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{ep['obs_agent_url']}/api/stream/end", timeout=5) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def open_browser(cls, creator: str) -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{ep['obs_agent_url']}/api/stream/open-browser", timeout=5) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def focus_workspace(cls, creator: str, workspace: Optional[int] = None) -> Dict:
        """Requests VPS OBS Agent to switch Linux XFCE desktop workspace and focus the model's screen."""
        clean_creator = creator.lower().replace("@", "").strip()
        ep = cls.get_endpoints(clean_creator)
        base_url = ep.get("obs_agent_url", "http://159.69.64.80:8080")

        urls = [f"{base_url}/api/focus", f"http://127.0.0.1:8080/api/focus"]
        payload = {"creator": clean_creator}
        if workspace is not None:
            payload["workspace"] = workspace

        for url in urls:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            return await resp.json()
            except Exception:
                continue
        return {"success": False, "error": f"Could not contact OBS Agent for @{clean_creator}"}


class GoLiveModal(discord.ui.Modal):
    def __init__(self, creator: str, on_success_callback):
        super().__init__(title=f"Go Live on F2F — @{creator}")
        self.creator = creator
        self.on_success_callback = on_success_callback

        self.title_input = discord.ui.TextInput(
            label="Live Stream Title",
            placeholder="e.g. In mijn DM ben ik stouter... 😈",
            default="In mijn DM ben ik stouter... 😈",
            required=True,
            max_length=120
        )
        self.add_item(self.title_input)

        self.message_input = discord.ui.TextInput(
            label="Live Description / Message",
            placeholder="e.g. Tip 50 coins for special show! 💕",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.message_input)

        self.goal_input = discord.ui.TextInput(
            label="Tip Goal (€)",
            placeholder="e.g. 50 (Leave blank if none)",
            required=False,
            max_length=10
        )
        self.add_item(self.goal_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        title = self.title_input.value.strip()
        msg = self.message_input.value.strip()
        goal = self.goal_input.value.strip()

        res = await LiveStreamAPIService.go_live(self.creator, title, msg, goal)
        if res.get("success"):
            await interaction.followup.send(
                f"🚀 **Successfully started Live Stream for @{self.creator}!**\n"
                f"**Title**: *\"{title}\"*\n"
                f"• OBS Virtual Camera: 🟢 Started\n"
                f"• F2F Live Broadcast: 🟢 Live\n"
                f"• FYP Audience Switcher: 🟢 Active",
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"❌ Failed to start live stream: {res.get('error')}", ephemeral=True)
        await self.on_success_callback(interaction)


class LiveSettingsModal(discord.ui.Modal):
    def __init__(self, creator: str, on_success_callback):
        super().__init__(title=f"Live Settings — @{creator}")
        self.creator = creator
        self.on_success_callback = on_success_callback

        self.audience_input = discord.ui.TextInput(
            label="Audience Target (public/followers/fans)",
            placeholder="Type: public, followers, or fans",
            default="public",
            required=False,
            max_length=30
        )
        self.add_item(self.audience_input)

        self.tip_goal_input = discord.ui.TextInput(
            label="Tip Goal (€)",
            placeholder="e.g. 50 (Leave blank if unchanged)",
            required=False,
            max_length=10
        )
        self.add_item(self.tip_goal_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        aud_raw = self.audience_input.value.strip().lower()
        tip_raw = self.tip_goal_input.value.strip()

        updates = []
        if aud_raw:
            target_map = {
                "public": "public",
                "global": "public",
                "fyp": "public",
                "followers": "fans-and-followers",
                "fans-and-followers": "fans-and-followers",
                "follower": "fans-and-followers",
                "fans": "fans-only",
                "fans-only": "fans-only",
                "subscribers": "fans-only"
            }
            target = target_map.get(aud_raw)
            if target:
                res_aud = await LiveStreamAPIService.set_audience(self.creator, target)
                if res_aud.get("success"):
                    updates.append(f"Audience set to `{target.upper()}`")
                else:
                    updates.append(f"Audience update: {res_aud.get('error', 'error')}")

        if tip_raw and tip_raw.isdigit():
            res_tip = await LiveStreamAPIService.set_tip_goal(self.creator, int(tip_raw))
            if res_tip.get("success"):
                updates.append(f"Tip Goal set to `€{tip_raw}`")
            else:
                updates.append(f"Tip Goal update: {res_tip.get('error', 'error')}")

        msg = " | ".join(updates) if updates else "No settings modified."
        await interaction.followup.send(f"⚙️ **Live Settings for @{self.creator}:** {msg}", ephemeral=True)
        await self.on_success_callback(interaction)


class F2FLiveStreamDashboardView(discord.ui.LayoutView):
    """
    State-of-the-Art Components V2 Live Stream Control Dashboard.
    Provides phone-friendly buttons and video switching dropdowns.
    """

    def __init__(self, author: discord.User | discord.Member, initial_creator: str = "xsophiex"):
        super().__init__(timeout=86400)
        self.author = author
        self.selected_creator = initial_creator
        self.available_creators = ["xsophiex", "chantalkuyt", "aylen", "zoelynn"]

    async def build_dashboard_container(self) -> discord.ui.Container:
        status_data = await LiveStreamAPIService.get_status(self.selected_creator)
        videos = await LiveStreamAPIService.list_videos(self.selected_creator)

        is_connected = status_data.get("is_connected", False)
        active_video = status_data.get("active_video") or status_data.get("input_name", "No Media Active")
        
        # Strictly isolate models: Only cache and include active_video if OBS is connected for this creator
        if is_connected and active_video and active_video not in ["No Media Active", "Media"]:
            LiveStreamAPIService.add_video_to_cache(self.selected_creator, active_video)
            if active_video not in videos:
                videos.insert(0, active_video)
        elif not is_connected:
            active_video = "No Media Active"

        dur_sec = float(status_data.get("duration_sec", 0.0) or 0.0) if is_connected else 0.0
        rem_sec = float(status_data.get("remaining_sec", 0.0) or 0.0) if is_connected else 0.0
        state_str = status_data.get("state", "OFFLINE")
        flipped_h = status_data.get("flipped_h", False) if is_connected else False
        flipped_v = status_data.get("flipped_v", False) if is_connected else False
        obs_preview_enabled = status_data.get("obs_preview_enabled", getattr(LiveStreamAPIService, f"_obs_preview_{self.selected_creator}", True))

        # Format timers
        dur_fmt = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}"
        rem_fmt = f"{int(rem_sec // 60):02d}:{int(rem_sec % 60):02d}"
        if is_connected and dur_sec > 0:
            media_info = f"`{active_video}` ({rem_fmt} left of {dur_fmt})"
        elif is_connected:
            media_info = f"`{active_video}`"
        else:
            media_info = "`No Media Active`"

        # Format orientation
        if not is_connected:
            orientation_info = "N/A (OBS Offline)"
        elif flipped_h and flipped_v:
            orientation_info = "↔️↕️ Mirrored (H+V)"
        elif flipped_h:
            orientation_info = "↔️ Flipped Horizontal"
        elif flipped_v:
            orientation_info = "↕️ Flipped Vertical"
        else:
            orientation_info = "Normal (Default)"

        obs_status = "🟢 Connected" if is_connected else "🔴 Disconnected"
        stream_status = "🟢 Streaming (Live)" if is_connected and dur_sec > 0 else "⚪ Standby"
        preview_text = "🟢 Enabled (Rendering)" if (is_connected and obs_preview_enabled) else ("⚫ Disabled (CPU Saver)" if is_connected else "⚪ Standby")

        # Build V2 Container
        container = discord.ui.Container(accent_color=discord.Color.from_str("#FF0080"))

        # Header
        container.add_item(discord.ui.TextDisplay(
            content=f"# 🔴 Live Stream Control — @{self.selected_creator}"
        ))
        container.add_item(discord.ui.TextDisplay(
            content="-# Real-time Video Switching, Camera Loops & Live Chat Controller"
        ))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Status Display
        container.add_item(discord.ui.TextDisplay(
            content=(
                f"### 📊 Stream Telemetry\n"
                f"**Creator**  ›  `@{self.selected_creator}`\n"
                f"**OBS Node**  ›  {obs_status}\n"
                f"**Live Status**  ›  {stream_status}\n"
                f"**Selected Video**  ›  {media_info}\n"
                f"**Orientation**  ›  `{orientation_info}`\n"
                f"**VPS Preview**  ›  `{preview_text}`\n"
                f"**Auto-Loop Reset**  ›  `10.0s` (Triggers at 5s remaining)"
            )
        ))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Model Switcher ActionRow ──
        model_row = discord.ui.ActionRow()
        for c in self.available_creators:
            is_active = (c == self.selected_creator)
            btn = discord.ui.Button(
                label=f"@{c}",
                style=discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary,
                custom_id=f"select_model_{c}",
                disabled=is_active
            )

            async def make_model_callback(creator_name=c):
                async def cb(interaction: discord.Interaction):
                    await interaction.response.defer()
                    self.selected_creator = creator_name
                    await self.refresh_dashboard(interaction)
                return cb

            btn.callback = await make_model_callback(c)
            model_row.add_item(btn)

        container.add_item(model_row)

        # ── Video Selection Dropdown ──
        if videos:
            video_row = discord.ui.ActionRow()
            options = []
            for v in videos[:25]:  # Discord select max 25 items
                is_current = (v.lower() == active_video.lower())
                options.append(discord.SelectOption(
                    label=v[:100],
                    value=v,
                    description=f"{'▶️ Currently Playing' if is_current else f'Switch OBS playback to {v[:35]}'}"[:100],
                    emoji="▶️" if is_current else "🎬",
                    default=is_current
                ))

            video_select = discord.ui.Select(
                placeholder=f"🎬 Selected: {active_video[:50]}",
                options=options,
                custom_id="video_select_dropdown"
            )

            async def on_video_selected(interaction: discord.Interaction):
                selected_v = video_select.values[0]
                await interaction.response.defer(ephemeral=True)
                res = await LiveStreamAPIService.switch_video(self.selected_creator, selected_v)
                if res.get("success"):
                    await interaction.followup.send(f"✅ **Switched OBS Media to `{selected_v}` for @{self.selected_creator}!**", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Failed to switch video: {res.get('error')}", ephemeral=True)
                await self.refresh_dashboard(interaction)

            video_select.callback = on_video_selected
            video_row.add_item(video_select)
            container.add_item(video_row)
        else:
            container.add_item(discord.ui.TextDisplay(
                content=f"-# 📁 *No video clips found in `videos/{self.selected_creator}/` on VPS.*"
            ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Stream Actions ActionRow ──
        actions_row = discord.ui.ActionRow()

        # [ 🚀 Go Live on F2F ] Button (Opens Modal with Title & Message)
        go_live_btn = discord.ui.Button(
            label="Go Live on F2F",
            style=discord.ButtonStyle.success,
            emoji="🚀",
            custom_id="btn_go_live_modal"
        )
        async def on_go_live(interaction: discord.Interaction):
            modal = GoLiveModal(self.selected_creator, self.refresh_dashboard)
            await interaction.response.send_modal(modal)
        go_live_btn.callback = on_go_live
        actions_row.add_item(go_live_btn)

        # [ 🛑 End Live Stream ] Button
        end_btn = discord.ui.Button(
            label="End Live Stream",
            style=discord.ButtonStyle.danger,
            emoji="🛑",
            custom_id="btn_end_live_stream"
        )
        async def on_end(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.end_stream(self.selected_creator)
            await interaction.followup.send(f"🛑 **Live Stream Ended for @{self.selected_creator}!**", ephemeral=True)
            await self.refresh_dashboard(interaction)
        end_btn.callback = on_end
        actions_row.add_item(end_btn)

        # Toggle FYP Loop
        fyp_btn = discord.ui.Button(
            label="Toggle FYP",
            style=discord.ButtonStyle.primary,
            emoji="🔄",
            custom_id="btn_toggle_fyp"
        )
        async def on_fyp(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.toggle_fyp_loop(self.selected_creator)
            await interaction.followup.send(f"🔄 **FYP Audience Switcher toggled for @{self.selected_creator}!**", ephemeral=True)
            await self.refresh_dashboard(interaction)
        fyp_btn.callback = on_fyp
        actions_row.add_item(fyp_btn)

        # [ ⚙️ Live Settings ] Button
        settings_btn = discord.ui.Button(
            label="Live Settings",
            style=discord.ButtonStyle.secondary,
            emoji="⚙️",
            custom_id="btn_live_settings"
        )
        async def on_settings(interaction: discord.Interaction):
            modal = LiveSettingsModal(self.selected_creator, self.refresh_dashboard)
            await interaction.response.send_modal(modal)
        settings_btn.callback = on_settings
        actions_row.add_item(settings_btn)

        # [ 🎯 Focus Screen ] Button (Switches Linux desktop workspace for Discord stream)
        focus_btn = discord.ui.Button(
            label="Focus Screen",
            style=discord.ButtonStyle.primary,
            emoji="🎯",
            custom_id="btn_focus_workspace"
        )
        async def on_focus(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.focus_workspace(self.selected_creator)
            if res.get("success"):
                ws_num = res.get("workspace", "?")
                await interaction.followup.send(
                    f"🎯 **Switched Linux Screen & Focused @{self.selected_creator} (Workspace {ws_num})!**\n"
                    f"-# Discord full-screen stream will now display @{self.selected_creator}'s active desktop.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"❌ Failed to focus screen: {res.get('error')}", ephemeral=True)
        focus_btn.callback = on_focus
        actions_row.add_item(focus_btn)

        # ── OBS Controls ActionRow ──
        obs_row = discord.ui.ActionRow()

        # [ ↔️ Flip Horizontal ] Button
        flip_h_label = "Unflip Horizontal" if flipped_h else "Flip Horizontal"
        flip_h_btn = discord.ui.Button(
            label=flip_h_label,
            style=discord.ButtonStyle.primary if flipped_h else discord.ButtonStyle.secondary,
            emoji="↔️",
            custom_id="btn_flip_horizontal"
        )
        async def on_flip_h(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.flip_horizontal(self.selected_creator)
            if res.get("success"):
                mode = "Mirrored" if res.get("flipped_h") else "Normal"
                await interaction.followup.send(f"↔️ **Horizontal Flip toggled ({mode}) for @{self.selected_creator}!**", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to flip horizontal: {res.get('error', 'Unknown error')}", ephemeral=True)
            await self.refresh_dashboard(interaction)
        flip_h_btn.callback = on_flip_h
        obs_row.add_item(flip_h_btn)

        # [ ↕️ Flip Vertical ] Button
        flip_v_label = "Unflip Vertical" if flipped_v else "Flip Vertical"
        flip_v_btn = discord.ui.Button(
            label=flip_v_label,
            style=discord.ButtonStyle.primary if flipped_v else discord.ButtonStyle.secondary,
            emoji="↕️",
            custom_id="btn_flip_vertical"
        )
        async def on_flip_v(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.flip_vertical(self.selected_creator)
            if res.get("success"):
                mode = "Flipped" if res.get("flipped_v") else "Normal"
                await interaction.followup.send(f"↕️ **Vertical Flip toggled ({mode}) for @{self.selected_creator}!**", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to flip vertical: {res.get('error', 'Unknown error')}", ephemeral=True)
            await self.refresh_dashboard(interaction)
        flip_v_btn.callback = on_flip_v
        obs_row.add_item(flip_v_btn)

        # [ 🖥️ OBS Preview ] Toggle Button (Enables / Disables canvas preview in VPS OBS)
        preview_label = "Disable Preview" if obs_preview_enabled else "Enable Preview"
        preview_btn = discord.ui.Button(
            label=preview_label,
            style=discord.ButtonStyle.secondary if obs_preview_enabled else discord.ButtonStyle.success,
            emoji="🖥️",
            custom_id="btn_toggle_obs_preview"
        )
        async def on_toggle_preview(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.toggle_obs_preview(self.selected_creator)
            if res.get("success"):
                mode = "Enabled (Rendering)" if res.get("preview_enabled") else "Disabled (CPU Saver)"
                await interaction.followup.send(f"🖥️ **VPS OBS Canvas Preview set to `{mode}` for @{self.selected_creator}!**", ephemeral=True)
            else:
                err_msg = res.get("error") or "Request failed or timed out. Please verify OBS window is not in a modal menu."
                await interaction.followup.send(f"❌ Failed to toggle OBS preview: {err_msg}", ephemeral=True)
            await self.refresh_dashboard(interaction)
        preview_btn.callback = on_toggle_preview
        obs_row.add_item(preview_btn)

        # [ 📷 Toggle Camera ] Button (Turns camera OFF / ON on F2F Live)
        cam_toggle_btn = discord.ui.Button(
            label="Toggle Camera",
            style=discord.ButtonStyle.secondary,
            emoji="📷",
            custom_id="btn_toggle_camera"
        )
        async def on_toggle_camera(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            res = await LiveStreamAPIService.toggle_camera(self.selected_creator)
            if res.get("success"):
                await interaction.followup.send(f"📷 **Toggled Camera (ON/OFF) on F2F Live for @{self.selected_creator}!**", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to toggle camera: {res.get('error')}", ephemeral=True)
        cam_toggle_btn.callback = on_toggle_camera
        obs_row.add_item(cam_toggle_btn)

        # Refresh Dashboard Button
        refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            emoji="🔃",
            custom_id="btn_refresh_dash"
        )
        async def on_refresh(interaction: discord.Interaction):
            await self.refresh_dashboard(interaction)
        refresh_btn.callback = on_refresh
        obs_row.add_item(refresh_btn)

        container.add_item(actions_row)
        container.add_item(obs_row)
        return container

    async def render(self) -> None:
        self.clear_items()
        container = await self.build_dashboard_container()
        self.add_item(container)

    async def refresh_dashboard(self, interaction: discord.Interaction):
        await self.render()
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            else:
                try:
                    await interaction.edit_original_response(view=self)
                except Exception:
                    if interaction.message:
                        await interaction.message.edit(view=self)
        except Exception as e:
            logger.warning(f"Dashboard edit note: {e}")


# Persistent cache to map Discord message IDs to F2F live chat message items
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "live_chat_cache.json")

def load_chat_cache() -> Dict[int, Dict]:
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return {int(k): v for k, v in raw.items()}
    except Exception as e:
        logger.debug(f"Cache load note: {e}")
    return {}

def save_chat_cache(cache: Dict[int, Dict]):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        items = list(cache.items())[-5000:]
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in items}, f)
    except Exception as e:
        logger.debug(f"Cache save note: {e}")

DISCORD_TO_F2F_CHAT_CACHE: Dict[int, Dict] = load_chat_cache()



class UnbanButtonView(discord.ui.View):
    """One-click Unban button displayed when a user is blocked from F2F Live."""
    def __init__(self, creator: str, username: str):
        super().__init__(timeout=600)
        self.creator = creator
        self.username = username

    @discord.ui.button(label="Unban User", style=discord.ButtonStyle.secondary, emoji="🔓")
    async def unban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        res = await LiveStreamAPIService.unban_live_user(creator=self.creator, username=self.username)
        if res.get("success"):
            button.disabled = True
            button.label = "Unbanned"
            button.style = discord.ButtonStyle.success
            button.emoji = "✅"
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
            await interaction.followup.send(f"✅ **@{self.username} has been unbanned and unmuted for @{self.creator}!**", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ Failed to unban @{self.username}: {res.get('error', 'error')}", ephemeral=True)


class LiveStreamControllerCog(commands.Cog, name="Live Stream Controller"):
    """Discord Controller for F2F Live Streams, Video Switching & Two-Way Live Chat Dispatch."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.creator_last_seq = {
            "xsophiex": -1,
            "chantalkuyt": -1,
            "chantalkuytmistress": -1,
            "zoelynn": -1,
            "aylen": -1
        }
        self.seen_message_ids = set()
        self.seen_content_hashes = {}
        self.last_rejoin_time = {}
        self.poller_task = None

    async def cog_load(self):
        self.poller_task = self.bot.loop.create_task(self.incoming_chat_poller())

    async def cog_unload(self):
        if self.poller_task and not self.poller_task.done():
            self.poller_task.cancel()

    async def _poll_single_creator(self, creator: str):
        try:
            # Proactive Room Keepalive: Only rejoin on initial boot or if polling errored out
            now = time.time()
            if self.last_rejoin_time.get(creator, 0) == 0:
                self.last_rejoin_time[creator] = now
                asyncio.create_task(LiveStreamAPIService.rejoin_live_chat(creator))

            curr_seq = self.creator_last_seq.get(creator, -1)
            if curr_seq == -1:
                # Initial bot boot sync: set pointer to current server head
                initial_chats, initial_max_seq = await LiveStreamAPIService.get_incoming_chats(creator, since_seq=0)
                self.creator_last_seq[creator] = initial_max_seq
                logger.info(f"💬 Live chat synced to server head for @{creator} (seq #{initial_max_seq})")
                now_ts = time.time()
                for c in initial_chats:
                    if now_ts - float(c.get("timestamp", 0)) < 300:
                        await self.dispatch_chat_to_discord(creator, c)
                return

            chats, max_seq = await LiveStreamAPIService.get_incoming_chats(creator, since_seq=curr_seq)
            if max_seq < curr_seq:
                # Server restarted or counter reset: auto-resync immediately and fetch any new messages
                logger.info(f"🔄 Live chat sequence reset for @{creator} ({curr_seq} -> {max_seq}). Auto-resynced.")
                self.creator_last_seq[creator] = max_seq
                chats, _ = await LiveStreamAPIService.get_incoming_chats(creator, since_seq=0)
            elif max_seq > curr_seq:
                self.creator_last_seq[creator] = max_seq

            if chats:
                for chat in chats:
                    await self.dispatch_chat_to_discord(creator, chat)
        except Exception as e:
            logger.debug(f"Poller tick note for @{creator}: {e}")

    async def incoming_chat_poller(self):
        """Polls active model agents concurrently for incoming live chats/tips and relays them to Discord."""
        await self.bot.wait_until_ready()
        logger.info("💬 Started Two-Way F2F Live Chat background poller (Concurrent Sub-Second Engine).")
        creators = ["xsophiex", "chantalkuyt", "chantalkuytmistress", "zoelynn", "aylen"]
        while not self.bot.is_closed():
            try:
                await asyncio.gather(*(self._poll_single_creator(c) for c in creators), return_exceptions=True)
            except Exception as e:
                logger.error(f"Chat poller error: {e}")
            await asyncio.sleep(0.5)

    async def dispatch_chat_to_discord(self, creator: str, chat: Dict):
        """Finds the correct livechat channel for the model and posts the comment with moderation Delete button."""
        username = (chat.get("display_name") or chat.get("name") or chat.get("username") or "Fan").strip()
        username = username.split("\n")[0].strip()
        username = re.sub(r'(?i)\b(follower|subscriber|vip|moderator)\b', '', username).strip().lstrip("@")
        if not username:
            username = "Fan"
        text = (chat.get("text") or "").strip()
        c_type = chat.get("type", "chat")
        tip_amount = chat.get("tip_amount", 0)

        # 1. De-duplicate incoming messages by unique message ID
        f2f_id = str(chat.get("id") or "").strip()
        if f2f_id and f2f_id in self.seen_message_ids:
            return
        if f2f_id:
            self.seen_message_ids.add(f2f_id)
            if len(self.seen_message_ids) > 1000:
                self.seen_message_ids = set(list(self.seen_message_ids)[-500:])

        creator_lower = creator.lower().replace("@", "")
        creator_key = creator_lower.replace("x", "") # e.g. "sophie" for "xsophiex"

        # 2. Sliding window content deduplication (prevents duplicate messages from reconnects/dual-endpoints)
        now_ts = time.time()
        content_hash = f"{creator_lower}:{username.lower()}:{text.strip().lower()}"
        if content_hash in self.seen_content_hashes:
            if now_ts - self.seen_content_hashes[content_hash] < 15.0:
                logger.info(f"🛡️ Deduplicated duplicate livechat from @{username}: '{text}'")
                return
        self.seen_content_hashes[content_hash] = now_ts
        if len(self.seen_content_hashes) > 500:
            self.seen_content_hashes = {k: v for k, v in self.seen_content_hashes.items() if now_ts - v < 60.0}

        # 1. Strictly filter out creator self-messages, joined alerts, and multi-line garbage
        u_clean = username.lower().replace("@", "").replace("❤️", "").strip()
        creator_names = {
            "xsophiex": ["xsophiex", "sophie", "sophie ❤️", "sophiex"],
            "chantalkuyt": ["chantalkuyt", "chantal", "chantal kuyt"],
            "chantalkuytmistress": ["chantalkuytmistress", "chantal mistress", "mistress"],
            "zoelynn": ["zoelynn", "zoe", "zoe lynn"],
            "aylen": ["aylen"]
        }
        known_aliases = creator_names.get(creator_lower, [creator_lower])
        is_creator_msg = any(alias in u_clean or u_clean in alias for alias in known_aliases)
        recent_discord_sent = f"{creator_lower}:{text.strip().lower()}" in self.seen_content_hashes

        if (
            is_creator_msg or
            recent_discord_sent or
            c_type in ["joined", "left", "system", "log"] or
            "joined" in text.lower() or
            "joined" in username.lower() or
            "new messages" in text.lower() or
            "tipmenu" in text.lower() or
            len(text.split("\n")) > 2 or
            not text or
            len(text) < 1 or
            username.lower() == creator_lower or
            username in ["€0", "Follower", "Subscriber", "system", "Chat"] or
            username.isdigit() or
            ":" in username or
            "/ 0" in text or
            text.isdigit() or
            (len(text) <= 5 and ":" in text)
        ):
            return

        # 2. Find model livechat channel (Strictly targets #💬-livechat in Model's LIVE category!)
        target_channel = None
        CHANNEL_MODEL_TO_ID = {
            "xsophiex": 1544005198710575136,
            "chantalkuyt": 1544075241762852874,
            "chantalkuytmistress": 1544075999635836999,
            "zoelynn": 1544075668793327758,
            "aylen": 1544076264053407835,
        }
        known_id = CHANNEL_MODEL_TO_ID.get(creator_lower)
        if known_id:
            target_channel = self.bot.get_channel(known_id)

        if not target_channel:
            model_keys = {
                "xsophiex": ["sophie"],
                "chantalkuyt": ["chantal"],
                "chantalkuytmistress": ["mistress"],
                "zoelynn": ["zoe"],
                "aylen": ["aylen"]
            }.get(creator_lower, [creator_key])

            for guild in self.bot.guilds:
                # Pass 1: Strict match - 'livechat' in channel name AND model in category (excludes Sniper Bot)
                for channel in guild.text_channels:
                    cat_name = (channel.category.name.lower() if channel.category else "")
                    ch_name = channel.name.lower()

                    if "sniper" in cat_name:
                        continue

                    if "livechat" in ch_name:
                        if creator_lower == "chantalkuytmistress" and "mistress" in cat_name:
                            target_channel = channel
                            break
                        elif creator_lower == "chantalkuyt" and "chantal" in cat_name and "mistress" not in cat_name:
                            target_channel = channel
                            break
                        elif any(k in cat_name for k in model_keys):
                            target_channel = channel
                            break
                if target_channel:
                    break

                # Pass 2: Fallback to any channel with livechat and model
                if not target_channel:
                    for channel in guild.text_channels:
                        cat_name = (channel.category.name.lower() if channel.category else "")
                        ch_name = channel.name.lower()
                        if "sniper" in cat_name:
                            continue
                        if "livechat" in ch_name and any(k in f"{cat_name} {ch_name}" for k in model_keys):
                            target_channel = channel
                            break
                    if target_channel:
                        break

        if not target_channel:
            logger.warning(f"⚠️ Could not find Discord livechat channel for creator: @{creator}")
            return

        try:
            logger.info(f"📨 [@{creator}] Relaying F2F chat from '{username}' into Discord #{target_channel.name}: '{text}'")
            f2f_id = chat.get("id", "")

            # Only format as TIP ALERT if it is a genuine tip with an actual amount
            is_genuine_tip = (c_type == "tip" or tip_amount > 0) and ("€" in text and "/ 0" not in text)

            if is_genuine_tip:
                embed = discord.Embed(
                    title=f"💸 Tip Alert (€{tip_amount})",
                    description=f"**{username}** tipped **€{tip_amount}**!\n> {text}",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                msg_obj = await target_channel.send(embed=embed)
            else:
                msg_obj = await target_channel.send(f"💬 **[{username}]**: {text}")

            # Add moderation reaction emojis: 🗑️ (Delete comment) & 🚫 (Ban user)
            if msg_obj:
                try:
                    await msg_obj.add_reaction("🗑️")
                    await msg_obj.add_reaction("🚫")
                except Exception:
                    pass

            # Save mapping in global cache
            if msg_obj:
                DISCORD_TO_F2F_CHAT_CACHE[msg_obj.id] = {
                    "f2f_id": f2f_id,
                    "creator": creator,
                    "username": username,
                    "text": text
                }
                save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)
        except Exception as e:
            logger.error(f"Failed to post incoming livechat to #{target_channel.name}: {e}")

    async def resolve_chat_info(self, channel_id: int, message_id: int) -> Optional[Dict]:
        """Resolves chat metadata for reaction moderation. Rejects sniper channels."""
        cached = DISCORD_TO_F2F_CHAT_CACHE.get(message_id)
        if cached:
            return cached

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None

        if not channel:
            return None

        # Ignore anything in sniper category or channel
        category_name = (channel.category.name.lower() if channel.category else "")
        channel_name = channel.name.lower().replace("-", "").replace("_", "")
        if "sniper" in category_name or "sniper" in channel_name:
            return None

        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return None

        # Determine creator from channel & category
        combined = f"{category_name} {channel_name}"

        creator = "xsophiex"
        if "chantalkuytmistress" in combined or "mistress" in combined:
            creator = "chantalkuytmistress"
        elif "chantal" in combined:
            creator = "chantalkuyt"
        elif "zoelynn" in combined or "zoe" in combined:
            creator = "zoelynn"
        elif "aylen" in combined:
            creator = "aylen"
        elif "sophie" in combined:
            creator = "xsophiex"

        # Extract username and text from content
        content = msg.content or ""
        username = ""
        text = ""

        # Check Relayed Chat: 💬 **[username]**: text or 💬 [username]: text or 💬 username: text
        m_chat = re.search(r"💬\s*\*?\*?\[?(.*?)\]?\*?\*?:\s*([\s\S]*)", content)
        if m_chat:
            username = m_chat.group(1).strip("[]* ")
            username = re.sub(r'(?i)\b(follower|subscriber|vip|moderator)\b', '', username).strip().lstrip("@")
            text = m_chat.group(2).strip()
        else:
            # Check Tip Alert: 💸 **[TIP ALERT] username** tipped! `text`
            m_tip = re.search(r"💸\s*\*\*\[TIP ALERT\]\s*(.*?)\*\*\s*tipped!(?:\s*`?(.*?)`?\s*$)?", content)
            if m_tip:
                username = m_tip.group(1).strip("[] ")
                username = re.sub(r'(?i)\b(follower|subscriber|vip|moderator)\b', '', username).strip().lstrip("@")
                text = (m_tip.group(2) or "").strip("` ")
            else:
                # Direct chatter message typed in Discord
                if not msg.author.bot:
                    username = msg.author.display_name or msg.author.name
                    username = re.sub(r'(?i)\b(follower|subscriber|vip|moderator)\b', '', username).strip().lstrip("@")
                    text = content
                else:
                    text = content

        if not username and not text:
            return None

        resolved = {
            "f2f_id": "",
            "creator": creator,
            "username": username,
            "text": text
        }
        # Populate cache & save to disk
        DISCORD_TO_F2F_CHAT_CACHE[message_id] = resolved
        save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)
        return resolved

    @app_commands.command(name="stream", description="Open the F2F Live Stream & Video Switcher Dashboard")
    async def stream_dashboard(self, interaction: discord.Interaction, model: Optional[str] = "xsophiex"):
        """Displays the interactive Components V2 Live Stream Control Dashboard."""
        await interaction.response.defer()
        try:
            view = F2FLiveStreamDashboardView(author=interaction.user, initial_creator=model or "xsophiex")
            await view.render()
            await interaction.followup.send(view=view)
        except Exception as e:
            logger.exception(f"Error opening stream dashboard: {e}")
            await interaction.followup.send(f"❌ Failed to load stream dashboard: {e}", ephemeral=True)

    @app_commands.command(name="stream-video", description="Switch the active video clip playing in OBS for a model")
    @app_commands.describe(model="Creator model name (e.g. xsophiex)", video_name="Exact filename (e.g. video1.mp4)")
    async def stream_switch_video(self, interaction: discord.Interaction, model: str, video_name: str):
        """Switches the active video file in OBS Studio on the model's VPS."""
        await interaction.response.defer(ephemeral=True)
        res = await LiveStreamAPIService.switch_video(model, video_name)
        if res.get("success"):
            await interaction.followup.send(f"🎬 **Successfully switched OBS video to `{video_name}` for @{model}!**", ephemeral=True)

    @app_commands.command(name="unban", description="Unban / unmute a user from F2F Live Stream")
    @app_commands.describe(username="Chatter username to unban", model="Creator model name (default: xsophiex)")
    async def unban_user(self, interaction: discord.Interaction, username: str, model: Optional[str] = "xsophiex"):
        """Unbans a previously blocked user on F2F Live."""
        await interaction.response.defer(ephemeral=True)
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.unban_live_user(creator=creator_clean, username=username)
        if res.get("success"):
            await interaction.followup.send(f"✅ **@{username} has been unbanned for @{creator_clean}!**", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ Failed to unban @{username}: {res.get('error', 'Unknown error')}", ephemeral=True)

    @commands.command(name="unban")
    async def prefix_unban(self, ctx: commands.Context, username: str, model: Optional[str] = "xsophiex"):
        """Prefix command to unban a user: !unban <username> [model]"""
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.unban_live_user(creator=creator_clean, username=username)
        if res.get("success"):
            await ctx.send(f"✅ **@{username} has been unbanned for @{creator_clean}!**")
        else:
            await ctx.send(f"⚠️ Failed to unban @{username}: {res.get('error', 'Unknown error')}")

    @app_commands.command(name="flip-horizontal", description="Toggle Horizontal Flip (Mirror) in OBS Studio for a model")
    @app_commands.describe(model="Creator model name (default: xsophiex)")
    async def cmd_flip_horizontal(self, interaction: discord.Interaction, model: Optional[str] = "xsophiex"):
        """Toggles horizontal flip on OBS video media source."""
        await interaction.response.defer(ephemeral=True)
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.flip_horizontal(creator=creator_clean)
        if res.get("success"):
            state = "Mirrored" if res.get("flipped_h") else "Normal"
            await interaction.followup.send(f"↔️ **OBS Horizontal Flip toggled ({state}) for @{creator_clean}!**", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to flip horizontal: {res.get('error', 'Unknown error')}", ephemeral=True)

    @app_commands.command(name="flip-vertical", description="Toggle Vertical Flip in OBS Studio for a model")
    @app_commands.describe(model="Creator model name (default: xsophiex)")
    async def cmd_flip_vertical(self, interaction: discord.Interaction, model: Optional[str] = "xsophiex"):
        """Toggles vertical flip on OBS video media source."""
        await interaction.response.defer(ephemeral=True)
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.flip_vertical(creator=creator_clean)
        if res.get("success"):
            state = "Flipped" if res.get("flipped_v") else "Normal"
            await interaction.followup.send(f"↕️ **OBS Vertical Flip toggled ({state}) for @{creator_clean}!**", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to flip vertical: {res.get('error', 'Unknown error')}", ephemeral=True)

    @commands.command(name="fliph")
    async def prefix_flip_h(self, ctx: commands.Context, model: Optional[str] = "xsophiex"):
        """Prefix command: !fliph [model]"""
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.flip_horizontal(creator=creator_clean)
        if res.get("success"):
            state = "Mirrored" if res.get("flipped_h") else "Normal"
            await ctx.send(f"↔️ **OBS Horizontal Flip toggled ({state}) for @{creator_clean}!**")
        else:
            await ctx.send(f"❌ Failed to flip horizontal: {res.get('error', 'Unknown error')}")

    @commands.command(name="flipv")
    async def prefix_flip_v(self, ctx: commands.Context, model: Optional[str] = "xsophiex"):
        """Prefix command: !flipv [model]"""
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.flip_vertical(creator=creator_clean)
        if res.get("success"):
            state = "Flipped" if res.get("flipped_v") else "Normal"
            await ctx.send(f"↕️ **OBS Vertical Flip toggled ({state}) for @{creator_clean}!**")
        else:
            await ctx.send(f"❌ Failed to flip vertical: {res.get('error', 'Unknown error')}")

    @app_commands.command(name="obs-preview", description="Toggle OBS Canvas Preview on the VPS (saves CPU when disabled)")
    @app_commands.describe(model="Creator model name (default: xsophiex)")
    async def cmd_obs_preview(self, interaction: discord.Interaction, model: Optional[str] = "xsophiex"):
        """Toggles the visual preview display in OBS Studio on the VPS."""
        await interaction.response.defer(ephemeral=True)
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.toggle_obs_preview(creator=creator_clean)
        if res.get("success"):
            state = "Enabled (Rendering)" if res.get("preview_enabled") else "Disabled (CPU Saver)"
            await interaction.followup.send(f"🖥️ **VPS OBS Canvas Preview is now `{state}` for @{creator_clean}!**", ephemeral=True)
        else:
            err_msg = res.get("error") or "Request failed or timed out. Please verify OBS window is not in a modal menu."
            await interaction.followup.send(f"❌ Failed to toggle OBS preview: {err_msg}", ephemeral=True)

    @commands.command(name="preview")
    async def prefix_preview(self, ctx: commands.Context, model: Optional[str] = "xsophiex"):
        """Prefix command: !preview [model]"""
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.toggle_obs_preview(creator=creator_clean)
        if res.get("success"):
            state = "Enabled (Rendering)" if res.get("preview_enabled") else "Disabled (CPU Saver)"
            await ctx.send(f"🖥️ **VPS OBS Canvas Preview is now `{state}` for @{creator_clean}!**")
        else:
            err_msg = res.get("error") or "Request failed or timed out. Please verify OBS window is not in a modal menu."
            await ctx.send(f"❌ Failed to toggle OBS preview: {err_msg}")

    @app_commands.command(name="stream-add-video", description="Register a video filename to the model's video dropdown menu")
    @app_commands.describe(video_name="Exact filename (e.g. clip1.mp4)", model="Creator model name (default: xsophiex)")
    async def cmd_add_video(self, interaction: discord.Interaction, video_name: str, model: Optional[str] = "xsophiex"):
        """Adds a video filename to the model's video selection dropdown."""
        await interaction.response.defer(ephemeral=True)
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        vids = LiveStreamAPIService.add_video_to_cache(creator_clean, video_name.strip())
        await interaction.followup.send(f"✅ Added `{video_name.strip()}` to **@{creator_clean}**'s video dropdown! (Total registered: {len(vids)})", ephemeral=True)

    @commands.command(name="addvideo")
    async def prefix_add_video(self, ctx: commands.Context, video_name: str, model: Optional[str] = "xsophiex"):
        """Prefix command: !addvideo <filename.mp4> [model]"""
        creator_clean = (model or "xsophiex").lower().replace("@", "").strip()
        vids = LiveStreamAPIService.add_video_to_cache(creator_clean, video_name.strip())
        await ctx.send(f"✅ Added `{video_name.strip()}` to **@{creator_clean}**'s video dropdown! (Total registered: {len(vids)})")

    @commands.command(name="browser", aliases=["openbrowser"])
    async def prefix_open_browser(self, ctx: commands.Context, model: Optional[str] = None):
        """Prefix command: !browser [model] - Launches / navigates Google Chrome to F2F Live page"""
        creator_clean = (model or self.selected_creator or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.open_browser(creator=creator_clean)
        if res.get("success"):
            await ctx.send(f"🌐 **Opened / Navigated Google Chrome to F2F Live page for @{creator_clean}!**")
        else:
            await ctx.send(f"❌ Failed to open browser: {res.get('error', 'Unknown error')}")

    @commands.command(name="cam", aliases=["camera", "camoff", "togglecam"])
    async def prefix_toggle_camera(self, ctx: commands.Context, model: Optional[str] = None):
        """Prefix command: !cam [model] - Toggles the camera ON/OFF in F2F Live"""
        creator_clean = (model or self.selected_creator or "xsophiex").lower().replace("@", "").strip()
        res = await LiveStreamAPIService.toggle_camera(creator=creator_clean)
        if res.get("success"):
            await ctx.send(f"📷 **Toggled Camera (ON/OFF) on F2F Live for @{creator_clean}!**")
        else:
            await ctx.send(f"❌ Failed to toggle camera: {res.get('error', 'Unknown error')}")

    @commands.command(name="focus", aliases=["workspace", "ws", "screen"])
    async def prefix_focus_workspace(self, ctx: commands.Context, target: Optional[str] = None):
        """
        Prefix command: !focus [model or workspace 1-4]
        Switches the Linux desktop workspace and focuses the creator's screen for Discord screen share.
        Examples:
          !focus chantalkuyt  -> Switch to Chantal's workspace (Workspace 2)
          !focus sophie       -> Switch to Sophie's workspace (Workspace 1)
          !focus aylen        -> Switch to Aylen's workspace (Workspace 3)
          !focus zoelynn      -> Switch to Zoe Lynn's workspace (Workspace 4)
          !focus 1            -> Switch directly to Workspace 1
          !focus 2            -> Switch directly to Workspace 2
        """
        target_str = (target or self.selected_creator or "xsophiex").lower().replace("@", "").strip()
        workspace_num = None
        creator = target_str

        # If user passed a number (e.g. !focus 2 or !ws 1)
        if target_str.isdigit():
            workspace_num = int(target_str)
            num_to_creator = {1: "xsophiex", 2: "zoelynn", 3: "chantalkuyt", 4: "aylen"}
            creator = num_to_creator.get(workspace_num, self.selected_creator)
        else:
            creator_aliases = {
                "sophie": "xsophiex",
                "chantal": "chantalkuyt",
                "zoe": "zoelynn",
                "mistress": "chantalkuytmistress"
            }
            creator = creator_aliases.get(target_str, target_str)

        res = await LiveStreamAPIService.focus_workspace(creator=creator, workspace=workspace_num)
        if res.get("success"):
            ws = res.get("workspace", "?")
            await ctx.send(
                f"🎯 **Switched Linux Screen & Focused @{creator} (Workspace {ws})!**\n"
                f"-# Discord screen share will now broadcast @{creator}'s workspace."
            )
        else:
            await ctx.send(f"❌ Failed to focus workspace: {res.get('error', 'Unknown error')}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Auto-relays chatter messages from model channels directly into F2F Live!
        Strictly restricted to #💬-livechat under each model's LIVE category.
        Completely ignores all channels under Sniper Bot.
        """
        if message.author.bot or not message.guild:
            return

        category_name = (message.channel.category.name.lower() if message.channel.category else "")
        channel_name = message.channel.name.lower().replace("-", "").replace("_", "")
        combined = f"{category_name} {channel_name}"

        # 🛑 STRICT GUARD: Ignore ALL messages from Sniper Bot category or sniper channels!
        # Sniper Bot channels (e.g. #xsophiex, #aylen under Sniper Bot) must NEVER relay to F2F Live.
        if "sniper" in category_name or "sniper" in channel_name:
            return

        # Direct in-channel !unban command support (Works in ANY channel!)
        content_stripped = message.content.strip()
        content_lower = content_stripped.lower()
        if content_lower.startswith(("!unban", ".unban", "unban ")):
            parts = content_stripped.split()
            if len(parts) >= 2:
                unban_target = parts[1].lstrip("@")
                model_to_unban = parts[2].lstrip("@").lower() if len(parts) >= 3 else None
                if not model_to_unban:
                    if "mistress" in combined:
                        model_to_unban = "chantalkuytmistress"
                    elif "chantal" in combined:
                        model_to_unban = "chantalkuyt"
                    elif "sophie" in combined:
                        model_to_unban = "xsophiex"
                    elif "zoe" in combined:
                        model_to_unban = "zoelynn"
                    elif "aylen" in combined:
                        model_to_unban = "aylen"
                    else:
                        model_to_unban = "xsophiex"
                res = await LiveStreamAPIService.unban_live_user(creator=model_to_unban, username=unban_target)
                if res.get("success"):
                    await message.channel.send(f"✅ **@{unban_target} has been unbanned and unmuted for @{model_to_unban}!**")
                else:
                    await message.channel.send(f"⚠️ Failed to unban @{unban_target}: {res.get('error', 'error')}")
            else:
                await message.channel.send("⚠️ Usage: `!unban <username> [model]` (e.g. `!unban cipher` or `!unban cipher xsophiex`)")
            return

        # STRICT TARGET CHANNEL VERIFICATION FOR LIVE CHAT RELAY:
        # Outgoing chat MUST only dispatch from dedicated #💬-livechat under Model's LIVE category
        CHANNEL_ID_TO_MODEL = {
            1544005198710575136: "xsophiex",
            1544075241762852874: "chantalkuyt",
            1544075999635836999: "chantalkuytmistress",
            1544075668793327758: "zoelynn",
            1544076264053407835: "aylen",
        }

        target_model = CHANNEL_ID_TO_MODEL.get(message.channel.id)

        if not target_model:
            # Fallback by name: Channel MUST be a livechat channel AND category MUST be a LIVE category
            is_livechat_name = "livechat" in channel_name
            is_live_category = "live" in category_name or "stream" in category_name

            if is_livechat_name and is_live_category:
                if "mistress" in combined:
                    target_model = "chantalkuytmistress"
                elif "chantal" in combined:
                    target_model = "chantalkuyt"
                elif "sophie" in combined:
                    target_model = "xsophiex"
                elif "zoe" in combined:
                    target_model = "zoelynn"
                elif "aylen" in combined:
                    target_model = "aylen"

        # If not a verified livechat channel, DO NOT relay to F2F Live!
        if not target_model:
            return

        # Only relay ordinary chatter messages (not bot commands)
        if not message.content.startswith(("/", "!", ".")):
            res = await LiveStreamAPIService.send_live_chat(target_model, message.content)
            if res.get("success"):
                try:
                    await message.add_reaction("📡")
                    await message.add_reaction("🗑️")
                    # Store mapping so chatters can delete their own message if they make a typo!
                    DISCORD_TO_F2F_CHAT_CACHE[message.id] = {
                        "f2f_id": "",
                        "creator": target_model,
                        "username": target_model,
                        "text": message.content
                    }
                    save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)
                    # Register sent content hash so incoming echoes are immediately suppressed
                    self.seen_content_hashes[f"{target_model.lower()}:{message.content.strip().lower()}"] = time.time()
                except Exception:
                    pass
            else:
                try:
                    await message.add_reaction("❌")
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Listens for 🗑️ or ❌ reactions to delete messages directly on F2F Live!
        Works even across bot restarts or years later via resolve_chat_info fallback.
        """
        if payload.user_id == self.bot.user.id:
            return

        emoji_name = str(payload.emoji.name)
        
        # 1. DELETE MESSAGE ON F2F & DISCORD
        if "🗑" in emoji_name or emoji_name in ["❌", "\U0001f5d1"]:
            chat_info = await self.resolve_chat_info(payload.channel_id, payload.message_id)
            DISCORD_TO_F2F_CHAT_CACHE.pop(payload.message_id, None)
            save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)

            if chat_info:
                creator = chat_info.get("creator", "xsophiex")
                f2f_id = chat_info.get("f2f_id", "")
                text = (chat_info.get("text", "") or "").split("\n")[0].strip()
                username = (chat_info.get("username", "") or "").strip().lstrip("@")

                await LiveStreamAPIService.delete_live_chat(
                    creator=creator,
                    message_id=f2f_id,
                    text=text,
                    username=username
                )

            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(payload.channel_id)
                except Exception:
                    channel = None
            if channel:
                try:
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.delete()
                except Exception:
                    pass

        # 2. BLOCK / BAN USER FROM F2F LIVE STREAM
        elif "🚫" in emoji_name or emoji_name in ["⛔", "🔨", "\U0001f6ab"]:
            chat_info = await self.resolve_chat_info(payload.channel_id, payload.message_id)
            DISCORD_TO_F2F_CHAT_CACHE.pop(payload.message_id, None)
            save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)

            if chat_info:
                creator = chat_info.get("creator", "xsophiex")
                f2f_id = chat_info.get("f2f_id", "")
                text = (chat_info.get("text", "") or "").split("\n")[0].strip()
                username = (chat_info.get("username", "") or "").strip().lstrip("@")

                # 1. Ban user on F2F Live
                res = await LiveStreamAPIService.block_live_user(
                    creator=creator,
                    username=username,
                    text=text
                )

                # 2. Delete the offending comment on F2F (with grace delay to avoid DOM modal collision)
                try:
                    await asyncio.sleep(1.5)
                    await LiveStreamAPIService.delete_live_chat(
                        creator=creator,
                        message_id=f2f_id,
                        text=text,
                        username=username
                    )
                except Exception:
                    pass

                # 3. Delete from Discord & notify
                channel = self.bot.get_channel(payload.channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(payload.channel_id)
                    except Exception:
                        channel = None
                if channel:
                    try:
                        msg = await channel.fetch_message(payload.message_id)
                        await msg.delete()
                    except Exception:
                        pass

                    try:
                        if res.get("success"):
                            view = UnbanButtonView(creator=creator, username=username)
                            await channel.send(
                                f"🚫 **@{username} has been blocked & removed from F2F Live!**\n*To unban at any time, click the button below or type `!unban {username}`.*",
                                view=view
                            )
                        else:
                            alert = await channel.send(f"⚠️ Failed to block @{username}: {res.get('error', 'Unknown error')}")
                            await asyncio.sleep(5)
                            await alert.delete()
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """
        If a chatter deletes their message in Discord #💬-livechat, also delete it on F2F Live!
        """
        chat_info = DISCORD_TO_F2F_CHAT_CACHE.pop(payload.message_id, None)
        if chat_info:
            save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)
            await LiveStreamAPIService.delete_live_chat(
                creator=chat_info["creator"],
                message_id=chat_info.get("f2f_id", ""),
                text=chat_info.get("text", ""),
                username=chat_info.get("username", "")
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveStreamControllerCog(bot))
