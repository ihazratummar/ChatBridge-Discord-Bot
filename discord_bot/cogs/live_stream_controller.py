"""
Live Stream Controller Cog - ChatBridge & F2F Automation
Built using Discord UI LayoutView (Components V2) Architecture
Provides interactive phone control for Starting/Stopping streams,
switching preloaded videos in real-time, and relaying live chat comments.
"""

import os
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
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/send-chat",
                    json={"message": message},
                    timeout=3
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}


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


class F2FLiveStreamDashboardView(discord.ui.LayoutView):
    """
    State-of-the-Art Components V2 Live Stream Control Dashboard.
    Provides phone-friendly buttons and video switching dropdowns.
    """

    def __init__(self, author: discord.User | discord.Member, initial_creator: str = "xsophiex"):
        super().__init__(timeout=86400)
        self.author = author
        self.selected_creator = initial_creator
        self.available_creators = ["xsophiex", "chantalkuyt", "aylen", "sophie"]

    async def build_dashboard_container(self) -> discord.ui.Container:
        status_data = await LiveStreamAPIService.get_status(self.selected_creator)
        videos = await LiveStreamAPIService.list_videos(self.selected_creator)

        is_connected = status_data.get("is_connected", False)
        active_video = status_data.get("input_name", "No Media Active")
        dur_sec = status_data.get("duration_sec", 0.0)
        rem_sec = status_data.get("remaining_sec", 0.0)
        state_str = status_data.get("state", "OFFLINE")

        # Format timers
        dur_fmt = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}"
        rem_fmt = f"{int(rem_sec // 60):02d}:{int(rem_sec % 60):02d}"
        media_info = f"`{active_video}` ({rem_fmt} left of {dur_fmt})" if dur_sec > 0 else f"`{active_video}`"

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
                f"**Active Clip**  ›  {media_info}\n"
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
                options.append(discord.SelectOption(
                    label=v[:100],
                    value=v,
                    description=f"Switch OBS playback to {v[:40]}",
                    emoji="🎬"
                ))

            video_select = discord.ui.Select(
                placeholder="🎬 Choose Video Clip to Play in OBS...",
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
            # Prune ephemeral chat memory for this creator
            keys_to_del = [k for k, v in DISCORD_TO_F2F_CHAT_CACHE.items() if v.get("creator") == self.selected_creator]
            for k in keys_to_del:
                DISCORD_TO_F2F_CHAT_CACHE.pop(k, None)
            await interaction.followup.send(f"🛑 **Live Stream Ended for @{self.selected_creator}! (Chat memory wiped)**", ephemeral=True)
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

        # Refresh Dashboard
        refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            emoji="🔃",
            custom_id="btn_refresh_dash"
        )
        async def on_refresh(interaction: discord.Interaction):
            await self.refresh_dashboard(interaction)
        refresh_btn.callback = on_refresh
        actions_row.add_item(refresh_btn)

        container.add_item(actions_row)
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

    @classmethod
    async def send_live_chat(cls, creator: str, message: str) -> Dict:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            # 1. Direct FastAPI Server-to-Server Live Socket
            try:
                async with session.post(
                    f"{fastapi_url}/api/live/chat/send",
                    json={"creator": creator, "message": message},
                    timeout=3
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                pass

            # 2. Fallback to VPS OBS Agent
            try:
                async with session.post(
                    f"{ep['obs_agent_url']}/api/send-chat",
                    json={"message": message},
                    timeout=3
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
                    json={"creator": creator, "message_id": message_id},
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
    async def get_incoming_chats(cls, creator: str, since_seq: int = 0) -> tuple:
        ep = cls.get_endpoints(creator)
        fastapi_url = ep.get('fastapi_url', 'http://127.0.0.1:8000')
        async with aiohttp.ClientSession() as session:
            # 1. Direct FastAPI Server-to-Server Live Socket
            try:
                async with session.get(
                    f"{fastapi_url}/api/live/chat/incoming?creator={creator}&since_seq={since_seq}",
                    timeout=2
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("chats", []), data.get("max_seq", since_seq)
            except Exception:
                pass

            # 2. Fallback to VPS OBS Agent
            try:
                async with session.get(
                    f"{ep['obs_agent_url']}/api/stream/incoming-chats?since_seq={since_seq}",
                    timeout=2
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("chats", []), data.get("max_seq", since_seq)
            except Exception:
                pass
        return [], since_seq

# Cache to map Discord message IDs to F2F live chat message items: { discord_msg_id: { f2f_id, creator, text, username } }
DISCORD_TO_F2F_CHAT_CACHE = {}


class LiveStreamControllerCog(commands.Cog, name="Live Stream Controller"):
    """Discord Controller for F2F Live Streams, Video Switching & Two-Way Live Chat Dispatch."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.creator_last_seq = {
            "xsophiex": 0,
            "chantalkuyt": 0,
            "chantalkuytmistress": 0,
            "zoelynn": 0,
            "aylen": 0
        }
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
                    curr_seq = self.creator_last_seq.get(creator, 0)
                    chats, max_seq = await LiveStreamAPIService.get_incoming_chats(creator, since_seq=curr_seq)
                    if max_seq > curr_seq:
                        self.creator_last_seq[creator] = max_seq
                    if chats:
                        for chat in chats:
                            await self.dispatch_chat_to_discord(creator, chat)
            except Exception as e:
                logger.debug(f"Chat poller note: {e}")
            await asyncio.sleep(1.0)

    async def dispatch_chat_to_discord(self, creator: str, chat: Dict):
        """Finds the correct livechat channel for the model and posts the comment with moderation hook."""
        username = chat.get("username", "Fan")
        text = chat.get("text", "")
        c_type = chat.get("type", "chat")
        tip_amount = chat.get("tip_amount", 0)

        creator_lower = creator.lower().replace("@", "")
        creator_key = creator_lower.replace("x", "") # e.g. "sophie" for "xsophiex"

        # Find model livechat channel
        target_channel = None
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                cat_name = (channel.category.name.lower() if channel.category else "").replace("-", " ")
                ch_name = channel.name.lower().replace("-", " ")
                combined = f"{cat_name} {ch_name}"

                is_model_match = (
                    (creator_lower in combined) or 
                    (creator_key in combined) or 
                    ("sophie" in combined and "sophie" in creator_lower) or 
                    ("chantal" in combined and "chantal" in creator_lower) or
                    ("zoe" in combined and "zoe" in creator_lower) or
                    ("aylen" in combined and "aylen" in creator_lower)
                )
                is_livechat_channel = ("livechat" in ch_name or "chat" in ch_name or "live" in ch_name)

                if is_model_match and is_livechat_channel:
                    target_channel = channel
                    break
            if target_channel:
                break

        if not target_channel:
            logger.warning(f"⚠️ Could not find Discord livechat channel for creator: @{creator}")
            return

        try:
            if c_type == "tip" or tip_amount > 0 or "€" in text:
                msg = await target_channel.send(f"💸 **[TIP ALERT] {username}** tipped! `{text}`")
            else:
                msg = await target_channel.send(f"💬 **[{username}]**: {text}")

            # Store in cache for 🗑️ reaction deletion
            DISCORD_TO_F2F_CHAT_CACHE[msg.id] = {
                "f2f_id": chat.get("id", ""),
                "creator": creator,
                "username": username,
                "text": text
            }
        except Exception as e:
            logger.debug(f"Error dispatching chat to Discord channel: {e}")

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

        # Only relay if typed in a livechat / model channel and not a bot command
        is_livechat_channel = "livechat" in channel_name or "chat" in channel_name or target_model in channel_name
        if target_model and is_livechat_channel and not message.content.startswith(("/", "!", ".")):
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
        """
        if payload.user_id == self.bot.user.id:
            return

        emoji_name = str(payload.emoji.name)
        if emoji_name in ["🗑️", "🗑", "❌", "🚫"]:
            chat_info = DISCORD_TO_F2F_CHAT_CACHE.get(payload.message_id)
            if chat_info:
                creator = chat_info["creator"]
                f2f_id = chat_info.get("f2f_id", "")
                text = chat_info.get("text", "")
                username = chat_info.get("username", "")

                res = await LiveStreamAPIService.delete_live_chat(
                    creator=creator,
                    message_id=f2f_id,
                    text=text,
                    username=username
                )

                if res.get("success"):
                    channel = self.bot.get_channel(payload.channel_id)
                    if channel:
                        try:
                            msg = await channel.fetch_message(payload.message_id)
                            await msg.add_reaction("🗑️")
                        except Exception:
                            pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """
        If a chatter deletes their message in Discord #💬-livechat, also delete it on F2F Live!
        """
        chat_info = DISCORD_TO_F2F_CHAT_CACHE.pop(payload.message_id, None)
        if chat_info:
            await LiveStreamAPIService.delete_live_chat(
                creator=chat_info["creator"],
                message_id=chat_info.get("f2f_id", ""),
                text=chat_info.get("text", ""),
                username=chat_info.get("username", "")
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveStreamControllerCog(bot))
