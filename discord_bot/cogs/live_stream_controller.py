"""
Live Stream Controller Cog - ChatBridge & F2F Automation
Built using Discord UI LayoutView (Components V2) Architecture
Provides interactive phone control for Starting/Stopping streams,
switching preloaded videos in real-time, and relaying live chat comments.
"""

import os
import re
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
    },
    "chantalkuyt": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_CHANTALKUYT", "http://159.69.64.80:8082"),
        "fastapi_url": os.getenv("FASTAPI_URL_CHANTALKUYT", "http://77.237.241.68:8000"),
    },
    "aylen": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_AYLEN", "http://159.69.64.80:8083"),
        "fastapi_url": os.getenv("FASTAPI_URL_AYLEN", "http://77.237.241.68:8000"),
    },
    "zoelynn": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_ZOELYNN", "http://159.69.64.80:8084"),
        "fastapi_url": os.getenv("FASTAPI_URL_ZOELYNN", "http://77.237.241.68:8000"),
    },
    "chantalkuytmistress": {
        "obs_agent_url": os.getenv("OBS_AGENT_URL_CHANTALKUYTMISTRESS", "http://159.69.64.80:8085"),
        "fastapi_url": os.getenv("FASTAPI_URL_CHANTALKUYTMISTRESS", "http://77.237.241.68:8000"),
    }
}


class LiveStreamAPIService:
    """Helper to communicate with individual VPS OBS Agents and FastAPI servers."""

    @staticmethod
    def get_endpoints(creator: str) -> Dict[str, str]:
        creator_clean = creator.lower().replace("@", "").strip()
        return DEFAULT_VPS_ENDPOINTS.get(creator_clean, {
            "obs_agent_url": "http://127.0.0.1:8080",
            "fastapi_url": "http://127.0.0.1:8000"
        })

    @classmethod
    async def get_status(cls, creator: str) -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{ep['obs_agent_url']}/api/status", timeout=2) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception as e:
                logger.debug(f"Error fetching status from {ep['obs_agent_url']}: {e}")
        return {"status": "offline", "is_connected": False}

    @classmethod
    async def list_videos(cls, creator: str) -> List[str]:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{ep['obs_agent_url']}/api/videos", timeout=2) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("videos", [])
            except Exception as e:
                logger.debug(f"Error fetching videos: {e}")
        return []

    @classmethod
    async def switch_video(cls, creator: str, video_name: str) -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/switch-video",
                    json={"video_name": video_name},
                    timeout=3
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def flip_horizontal(cls, creator: str, source_name: str = "Media") -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/flip-horizontal",
                    json={"source_name": source_name},
                    timeout=3
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def flip_vertical(cls, creator: str, source_name: str = "Media") -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/flip-vertical",
                    json={"source_name": source_name},
                    timeout=3
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def get_transform_status(cls, creator: str, source_name: str = "Media") -> Dict:
        ep = cls.get_endpoints(creator)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ep['obs_agent_url']}/api/transform/status?source_name={source_name}",
                    timeout=3
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"flipped_h": False, "flipped_v": False, "error": str(e)}

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
        async with aiohttp.ClientSession() as session:
            # 1. Primary: Direct VPS OBS Agent (Runs in active Chrome browser with creator cookies)
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/send-chat",
                    json={"message": message},
                    timeout=4
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            return data
            except Exception as e:
                logger.warning(f"Failed dispatching chat to OBS Agent for {creator}: {e}")

            # 2. Fallback: FastAPI
            fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/chat/send",
                    json={"creator": creator, "message": message},
                    timeout=4
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def delete_live_chat(cls, creator: str, message_id: str = "", text: str = "", username: str = "") -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            # 1. Direct FastAPI Server-to-Server Live Socket
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/chat/delete",
                    json={"creator": creator, "message_id": message_id, "text": text, "username": username},
                    timeout=3
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                pass

            # 2. Fallback to VPS OBS Agent
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/stream/delete-chat",
                    json={"message_id": message_id, "text": text, "username": username},
                    timeout=3
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    @classmethod
    async def block_live_user(cls, creator: str, username: str) -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/chat/block",
                    json={"creator": creator, "username": username},
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

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
    async def get_incoming_chats(cls, creator: str, since_seq: int = 0) -> tuple:
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
                            chats = data.get("chats", [])
                            max_seq = data.get("max_seq", since_seq)
                            return chats, max_seq
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
        dur_sec = status_data.get("duration_sec", 0.0)
        rem_sec = status_data.get("remaining_sec", 0.0)
        state_str = status_data.get("state", "OFFLINE")
        flipped_h = status_data.get("flipped_h", False)
        flipped_v = status_data.get("flipped_v", False)

        # Format timers
        dur_fmt = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}"
        rem_fmt = f"{int(rem_sec // 60):02d}:{int(rem_sec % 60):02d}"
        media_info = f"`{active_video}` ({rem_fmt} left of {dur_fmt})" if dur_sec > 0 else f"`{active_video}`"

        # Format orientation
        if flipped_h and flipped_v:
            orientation_info = "↔️↕️ Mirrored (H+V)"
        elif flipped_h:
            orientation_info = "↔️ Flipped Horizontal"
        elif flipped_v:
            orientation_info = "↕️ Flipped Vertical"
        else:
            orientation_info = "Normal (Default)"

        obs_status = "🟢 Connected" if is_connected else "🔴 Disconnected"
        stream_status = "🟢 Streaming (Live)" if is_connected and dur_sec > 0 else "⚪ Standby"

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
                await interaction.edit_original_response(view=self)
        except Exception as e:
            logger.debug(f"Dashboard edit note: {e}")


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


class LiveChatMessageView(discord.ui.View):
    """Interactive Components V2 View with a Delete button for F2F Live comments."""
    def __init__(self, creator: str, f2f_id: str, text: str, username: str):
        super().__init__(timeout=None)
        self.creator = creator
        self.f2f_id = f2f_id
        self.text = text
        self.username = username

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        res = await LiveStreamAPIService.delete_live_chat(
            creator=self.creator,
            message_id=self.f2f_id,
            text=self.text,
            username=self.username
        )
        try:
            await interaction.message.delete()
        except Exception:
            pass


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
        self.last_rejoin_time = {}
        self.poller_task = None

    async def cog_load(self):
        self.poller_task = self.bot.loop.create_task(self.incoming_chat_poller())

    async def cog_unload(self):
        if self.poller_task and not self.poller_task.done():
            self.poller_task.cancel()

    async def incoming_chat_poller(self):
        """Polls active model VPS agents for incoming live chats/tips and relays them to Discord."""
        await self.bot.wait_until_ready()
        logger.info("💬 Started Two-Way F2F Live Chat background poller.")
        while not self.bot.is_closed():
            try:
                for creator in ["xsophiex", "chantalkuyt", "chantalkuytmistress", "zoelynn", "aylen"]:
                    # Proactive Room Keepalive: Ensure WebSocket room subscription is ALWAYS active on stream restart
                    now = time.time()
                    if now - self.last_rejoin_time.get(creator, 0) > 15:
                        self.last_rejoin_time[creator] = now
                        asyncio.create_task(LiveStreamAPIService.rejoin_live_chat(creator))

                    curr_seq = self.creator_last_seq.get(creator, -1)
                    if curr_seq == -1:
                        # Initial bot boot sync: set pointer to current server head
                        initial_chats, initial_max_seq = await LiveStreamAPIService.get_incoming_chats(creator, since_seq=0)
                        self.creator_last_seq[creator] = initial_max_seq
                        logger.info(f"💬 Live chat synced to server head for @{creator} (seq #{initial_max_seq})")
                        # Dispatch any fresh chats that arrived in the last 60 seconds so nothing is dropped
                        now_ts = time.time()
                        for c in initial_chats:
                            if now_ts - float(c.get("timestamp", 0)) < 60:
                                await self.dispatch_chat_to_discord(creator, c)
                        continue

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
                logger.error(f"Chat poller error: {e}")
            await asyncio.sleep(1.0)

    async def dispatch_chat_to_discord(self, creator: str, chat: Dict):
        """Finds the correct livechat channel for the model and posts the comment with moderation Delete button."""
        username = (chat.get("username") or "Fan").strip()
        text = (chat.get("text") or "").strip()
        c_type = chat.get("type", "chat")
        tip_amount = chat.get("tip_amount", 0)

        # De-duplicate incoming messages across reconnects and restarts
        f2f_id = str(chat.get("id") or f"{creator}:{username}:{text}").strip()
        if f2f_id in self.seen_message_ids:
            return
        self.seen_message_ids.add(f2f_id)
        if len(self.seen_message_ids) > 1000:
            self.seen_message_ids = set(list(self.seen_message_ids)[-500:])

        creator_lower = creator.lower().replace("@", "")
        creator_key = creator_lower.replace("x", "") # e.g. "sophie" for "xsophiex"

        # 1. Strictly filter out joined messages, system alerts, empty content, and creator self-messages
        if (
            c_type in ["joined", "left", "system"] or
            "joined" in text.lower() or
            "joined" in username.lower() or
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
            view = LiveChatMessageView(creator=creator, f2f_id=f2f_id, text=text, username=username)

            # Only format as TIP ALERT if it is a genuine tip with an actual amount
            is_genuine_tip = (c_type == "tip" or tip_amount > 0) and ("€" in text and "/ 0" not in text)

            if is_genuine_tip:
                msg = await target_channel.send(f"💸 **[TIP ALERT] {username}** tipped! `{text}`")
            else:
                msg = await target_channel.send(f"💬 **[{username}]**: {text}")

            # Add clean emoji reaction buttons (🗑️ to delete, 🚫 to block user)
            try:
                await msg.add_reaction("🗑️")
                await msg.add_reaction("🚫")
            except Exception:
                pass

            # Store in cache for 🗑️ / 🚫 reaction handling
            DISCORD_TO_F2F_CHAT_CACHE[msg.id] = {
                "f2f_id": f2f_id,
                "creator": creator,
                "username": username,
                "text": text
            }
            save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)
        except Exception as e:
            logger.error(f"Error dispatching chat to Discord channel: {e}")

    async def resolve_chat_info(self, channel_id: int, message_id: int) -> Optional[Dict]:
        """
        Decade-Proof chat info resolver:
        1. Checks in-memory and persistent JSON disk cache.
        2. If missing (e.g. after bot restart, offline for months/years, or fresh machine),
           fetches the Discord message directly from Discord API and parses:
           - Creator model (from channel name, category, and guild layout)
           - Chatter username & text (from message formatting)
        """
        # 1. Check in-memory / disk cache
        if message_id in DISCORD_TO_F2F_CHAT_CACHE:
            return DISCORD_TO_F2F_CHAT_CACHE.get(message_id)

        # 2. Decade-Proof Fallback: Fetch message directly from Discord
        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None

        if not channel:
            return None

        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return None

        # Determine creator from channel & category
        category_name = (channel.category.name.lower() if channel.category else "")
        channel_name = channel.name.lower().replace("-", "").replace("_", "")
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

        # Check Relayed Chat: 💬 **[username]**: text or 💬 **username**: text
        m_chat = re.search(r"💬\s*\*\*\[?(.*?)\]?\*\*:\s*([\s\S]*)", content)
        if m_chat:
            username = m_chat.group(1).strip("[] ")
            text = m_chat.group(2).strip()
        else:
            # Check Tip Alert: 💸 **[TIP ALERT] username** tipped! `text`
            m_tip = re.search(r"💸\s*\*\*\[TIP ALERT\]\s*(.*?)\*\*\s*tipped!(?:\s*`?(.*?)`?\s*$)?", content)
            if m_tip:
                username = m_tip.group(1).strip("[] ")
                text = (m_tip.group(2) or "").strip("` ")
            else:
                # Direct chatter message typed in Discord
                if not msg.author.bot:
                    username = msg.author.display_name or msg.author.name
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
        view = F2FLiveStreamDashboardView(author=interaction.user, initial_creator=model or "xsophiex")
        await view.render()
        await interaction.followup.send(view=view)

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Auto-relays chatter messages from model channels directly into F2F Live!
        Works with both channel names (#xsophiex) and category layouts (Sophie LIVE -> #💬-livechat).
        """
        if message.author.bot or not message.guild:
            return

        category_name = (message.channel.category.name.lower() if message.channel.category else "")
        channel_name = message.channel.name.lower().replace("-", "").replace("_", "")
        combined = f"{category_name} {channel_name}"

        # Match model by category or channel name
        target_model = None
        if "sophie" in combined:
            target_model = "xsophiex"
        elif "chantalkuytmistress" in combined or "mistress" in combined:
            target_model = "chantalkuytmistress"
        elif "chantal" in combined:
            target_model = "chantalkuyt"
        elif "zoelynn" in combined or "zoe" in combined:
            target_model = "zoelynn"
        elif "aylen" in combined:
            target_model = "aylen"

        # Direct in-channel !unban command support (Works in ANY channel!)
        content_stripped = message.content.strip()
        content_lower = content_stripped.lower()
        if content_lower.startswith(("!unban", ".unban", "unban ")):
            parts = content_stripped.split()
            if len(parts) >= 2:
                unban_target = parts[1].lstrip("@")
                model_to_unban = parts[2].lstrip("@").lower() if len(parts) >= 3 else (target_model or "xsophiex")
                res = await LiveStreamAPIService.unban_live_user(creator=model_to_unban, username=unban_target)
                if res.get("success"):
                    await message.channel.send(f"✅ **@{unban_target} has been unbanned and unmuted for @{model_to_unban}!**")
                else:
                    await message.channel.send(f"⚠️ Failed to unban @{unban_target}: {res.get('error', 'error')}")
            else:
                await message.channel.send("⚠️ Usage: `!unban <username> [model]` (e.g. `!unban cipher` or `!unban cipher xsophiex`)")
            return

        # Only relay if typed in a livechat / model channel and not a bot command
        if not target_model:
            return

        is_livechat_channel = "livechat" in channel_name or "chat" in channel_name or target_model in channel_name
        if is_livechat_channel and not message.content.startswith(("/", "!", ".")):
            res = await LiveStreamAPIService.send_live_chat(target_model, message.content)
            if res.get("success"):
                try:
                    await message.add_reaction("📡")
                    # Store mapping so chatters can delete their own message if they make a typo!
                    DISCORD_TO_F2F_CHAT_CACHE[message.id] = {
                        "f2f_id": "",
                        "creator": target_model,
                        "username": target_model,
                        "text": message.content
                    }
                    save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)
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
        if emoji_name in ["🗑️", "🗑", "❌"]:
            chat_info = await self.resolve_chat_info(payload.channel_id, payload.message_id)
            DISCORD_TO_F2F_CHAT_CACHE.pop(payload.message_id, None)
            save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)

            if chat_info:
                creator = chat_info.get("creator", "xsophiex")
                f2f_id = chat_info.get("f2f_id", "")
                text = chat_info.get("text", "")
                username = chat_info.get("username", "")

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
        elif emoji_name in ["🚫", "⛔", "🔨"]:
            chat_info = await self.resolve_chat_info(payload.channel_id, payload.message_id)
            DISCORD_TO_F2F_CHAT_CACHE.pop(payload.message_id, None)
            save_chat_cache(DISCORD_TO_F2F_CHAT_CACHE)

            if chat_info:
                creator = chat_info.get("creator", "xsophiex")
                f2f_id = chat_info.get("f2f_id", "")
                text = chat_info.get("text", "")
                username = chat_info.get("username", "")

                # 1. Ban user on F2F Live
                res = await LiveStreamAPIService.block_live_user(
                    creator=creator,
                    username=username
                )

                # 2. Delete the offending comment on F2F
                try:
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
