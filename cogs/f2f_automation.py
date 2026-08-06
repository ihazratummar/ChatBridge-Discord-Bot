import logging
import asyncio
import random
import re
import discord
from discord import app_commands
from discord.ext import commands
from services.campaign_service import CampaignService

from datetime import datetime

logger = logging.getLogger("ChatBridge.F2FAutomationCog")

async def get_or_create_f2f_logs_channel(bot: commands.Bot) -> discord.TextChannel | None:
    """
    Finds or automatically creates a dedicated #f2f_logs channel in Discord servers.
    Uses fuzzy matching so it matches names with emojis/unicode (e.g. #📜f2f_logs, #f2f-logs, #f2flogs).
    """
    if not bot or not bot.guilds:
        return None

    # Step 1: Fuzzy search across all connected guilds
    for guild in bot.guilds:
        for ch in guild.text_channels:
            normalized = re.sub(r'[^a-zA-Z0-9]', '', ch.name.lower())
            if ("f2f" in normalized and ("log" in normalized or "audit" in normalized)) or "f2flog" in normalized:
                return ch

    # Step 2: If not found, attempt auto-creating #f2f_logs in available guilds
    for guild in bot.guilds:
        try:
            new_channel = await guild.create_text_channel(
                name="f2f_logs",
                topic="F2F Automation Creator Audit Logs & System Error Alerts"
            )
            logger.info(f"✨ Auto-created dedicated log channel '#f2f_logs' in guild '{guild.name}'.")
            return new_channel
        except Exception as e:
            logger.warning(f"Could not auto-create #f2f_logs channel in guild '{guild.name}': {e}")

    return None

async def send_f2f_log(bot: commands.Bot, title: str, description: str, level: str = "info"):
    """
    Finds or creates dedicated #f2f_logs text channel in connected Discord servers and posts a clean event log.
    Only logs Creator-level events and system/auth errors (No per-user fan dispatches).
    """
    channel = await get_or_create_f2f_logs_channel(bot)
    if not channel:
        logger.warning(f"Could not find or create #f2f_logs channel to post event: '{title}'")
        return

    color_map = {
        "info": discord.Color.blue(),
        "success": discord.Color.green(),
        "warning": discord.Color.gold(),
        "error": discord.Color.red()
    }
    emoji_map = {
        "info": "ℹ️",
        "success": "🚀",
        "warning": "🛑",
        "error": "❌"
    }

    color = color_map.get(level, discord.Color.blue())
    emoji = emoji_map.get(level, "ℹ️")

    text = f"### {emoji} {title}\n{description}\n\n*Logged at <t:{int(datetime.utcnow().timestamp())}:F>*"

    try:
        container = discord.ui.Container(accent_color=color)
        container.add_item(discord.ui.TextDisplay(content=text))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await channel.send(view=view)
        logger.info(f"📢 Logged Creator Event to #{channel.name}: {title}")
    except Exception as e:
        logger.warning(f"LayoutView log dispatch error: {e}")
        try:
            await channel.send(f"**{emoji} {title}**\n{description}")
            logger.info(f"📢 Logged Creator Event (fallback text) to #{channel.name}: {title}")
        except Exception as e2:
            logger.error(f"Failed to post log message to #{channel.name}: {e2}")

class FollowupGapModal(discord.ui.Modal, title="Edit Follow-Up Gap Interval"):
    gap_input = discord.ui.TextInput(
        label="Follow-up Gap Interval (in minutes)",
        placeholder="e.g. 60",
        default="60",
        min_length=1,
        max_length=5,
        required=True
    )

    def __init__(self, campaign_service: CampaignService, refresh_callback):
        super().__init__()
        self.campaign_service = campaign_service
        self.refresh_callback = refresh_callback

    async def on_submit(self, interaction: discord.Interaction):
        val = self.gap_input.value.strip()
        if not val.isdigit() or int(val) < 1:
            await interaction.response.send_message("❌ Interval must be a positive integer (e.g. 15).", ephemeral=True)
            return

        await self.campaign_service.set_followup_gap(int(val))
        await interaction.response.send_message(f"✅ **Follow-up Gap updated to {val} minute(s)!**", ephemeral=True)
        await self.refresh_callback(interaction)


class FollowupTextModal(discord.ui.Modal, title="Edit Follow-Up Message Template"):
    text_input = discord.ui.TextInput(
        label="Follow-Up Message Template",
        style=discord.TextStyle.paragraph,
        placeholder="Hey (name), subtle bump! Are you free? 😊",
        min_length=3,
        max_length=1000,
        required=True
    )

    def __init__(self, campaign_service: CampaignService, refresh_callback):
        super().__init__()
        self.campaign_service = campaign_service
        self.refresh_callback = refresh_callback

    async def on_submit(self, interaction: discord.Interaction):
        val = self.text_input.value.strip()
        await self.campaign_service.set_followup_text(val)
        await interaction.response.send_message(f"✅ **Follow-up Message Template updated!**", ephemeral=True)
        await self.refresh_callback(interaction)


class TestChatIDsModal(discord.ui.Modal, title="Edit Test Target Chat UUIDs"):
    chat_ids_input = discord.ui.TextInput(
        label="Test Chat UUIDs (comma or line separated)",
        style=discord.TextStyle.paragraph,
        placeholder="e85d76cb-ff3b-4f3d-a6ff-cfad7b1f6b57, 1e25a5ad-ad38-4071-a2b4-6664109c7a34",
        min_length=10,
        max_length=2000,
        required=True
    )

    def __init__(self, campaign_service: CampaignService, refresh_callback):
        super().__init__()
        self.campaign_service = campaign_service
        self.refresh_callback = refresh_callback

    async def on_submit(self, interaction: discord.Interaction):
        val = self.chat_ids_input.value
        updated_ids = await self.campaign_service.set_test_chat_ids(val)
        await interaction.response.send_message(
            f"✅ **Updated Test Chat IDs! ({len(updated_ids)} active test target(s))**",
            ephemeral=True
        )
        await self.refresh_callback(interaction)


class CooldownHoursModal(discord.ui.Modal, title="Edit Active Cooldown Window"):
    hours_input = discord.ui.TextInput(
        label="Cooldown Window (in hours)",
        placeholder="e.g. 4",
        default="4",
        min_length=1,
        max_length=4,
        required=True
    )

    def __init__(self, campaign_service: CampaignService, refresh_callback):
        super().__init__()
        self.campaign_service = campaign_service
        self.refresh_callback = refresh_callback

    async def on_submit(self, interaction: discord.Interaction):
        val = self.hours_input.value.strip()
        if not val.isdigit() or int(val) < 1:
            await interaction.response.send_message("❌ Cooldown must be a positive integer (e.g. 4).", ephemeral=True)
            return

        await self.campaign_service.set_cooldown_hours(int(val))
        await interaction.response.send_message(f"✅ **Active Cooldown Window updated to {val} hour(s)!**", ephemeral=True)
        await self.refresh_callback(interaction)


class F2FConfigDashboardView(discord.ui.LayoutView):
    def __init__(self, campaign_service: CampaignService, author: discord.User | discord.Member):
        super().__init__(timeout=86400)
        self.campaign_service = campaign_service
        self.author = author

    async def build_dashboard_container(self) -> discord.ui.Container:
        gap = await self.campaign_service.get_followup_gap()
        cooldown = await self.campaign_service.get_cooldown_hours()
        followup_txt = await self.campaign_service.get_followup_text()
        test_ids = await self.campaign_service.get_test_chat_ids()
        has_session = bool(self.campaign_service.f2f_client.session_id)
        has_totp = bool(self.campaign_service.f2f_client.totp_secret)

        session_str = f"🟢 Active (`{self.campaign_service.f2f_client.session_id[:10]}...`)" if has_session else "🔴 Disconnected"
        totp_str = "🟢 Configured" if has_totp else "🔴 Missing"

        test_ids_formatted = "\n".join([f"╰ `{tid}`" for tid in test_ids]) if test_ids else "╰ *None configured*"

        # ── Header ──
        container = discord.ui.Container(accent_color=discord.Color.from_str("#5865F2"))

        container.add_item(discord.ui.TextDisplay(
            content="# ⚙️ Control Panel"
        ))
        container.add_item(discord.ui.TextDisplay(
            content="-# F2F Automation Configuration & System Status"
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Connection Status Section ──
        container.add_item(discord.ui.TextDisplay(
            content=(
                "### 🔐 Connection Status\n"
                f"**Session**  ›  {session_str}\n"
                f"**2FA TOTP**  ›  {totp_str}"
            )
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Campaign Parameters ──
        container.add_item(discord.ui.TextDisplay(
            content=(
                "### 🎛️ Campaign Parameters\n"
                f"╭ ⏱️ **Follow-Up Gap**  ›  `{gap}` min\n"
                f"╰ 🛡️ **Cooldown Window**  ›  `{cooldown}` hr"
            )
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Follow-Up Template ──
        snippet = followup_txt[:120] + "..." if len(followup_txt) > 120 else followup_txt
        container.add_item(discord.ui.TextDisplay(
            content=(
                "### 💬 Follow-Up Template\n"
                f"> *{snippet}*"
            )
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Test Targets ──
        container.add_item(discord.ui.TextDisplay(
            content=(
                f"### 🎯 Test Targets ({len(test_ids)})\n"
                f"{test_ids_formatted}"
            )
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Action Buttons ──
        row1 = discord.ui.ActionRow()
        btn_gap = discord.ui.Button(label="⏱️ Follow-Up Gap", style=discord.ButtonStyle.primary, custom_id="cfg_gap")
        btn_cooldown = discord.ui.Button(label="🛡️ Cooldown", style=discord.ButtonStyle.primary, custom_id="cfg_cooldown")
        btn_text = discord.ui.Button(label="💬 Template", style=discord.ButtonStyle.primary, custom_id="cfg_text")
        btn_test_ids = discord.ui.Button(label="🎯 Test IDs", style=discord.ButtonStyle.secondary, custom_id="cfg_test_ids")
        btn_refresh = discord.ui.Button(label="🔄", style=discord.ButtonStyle.secondary, custom_id="cfg_refresh")

        btn_gap.callback = self.edit_gap_callback
        btn_cooldown.callback = self.edit_cooldown_callback
        btn_text.callback = self.edit_text_callback
        btn_test_ids.callback = self.edit_test_ids_callback
        btn_refresh.callback = self.refresh_callback

        row1.add_item(btn_gap)
        row1.add_item(btn_cooldown)
        row1.add_item(btn_text)
        row1.add_item(btn_test_ids)
        row1.add_item(btn_refresh)

        container.add_item(row1)
        return container

    async def initialize(self):
        self.clear_items()
        container = await self.build_dashboard_container()
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the user who opened `/f2f_config` can use these controls.", ephemeral=True)
            return False
        return True

    async def refresh_dashboard(self, interaction: discord.Interaction):
        await self.initialize()
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            logger.warning(f"Dashboard refresh notification: {e}")

    async def edit_gap_callback(self, interaction: discord.Interaction):
        gap = await self.campaign_service.get_followup_gap()
        modal = FollowupGapModal(self.campaign_service, self.refresh_dashboard)
        modal.gap_input.default = str(gap)
        await interaction.response.send_modal(modal)

    async def edit_cooldown_callback(self, interaction: discord.Interaction):
        cooldown = await self.campaign_service.get_cooldown_hours()
        modal = CooldownHoursModal(self.campaign_service, self.refresh_dashboard)
        modal.hours_input.default = str(cooldown)
        await interaction.response.send_modal(modal)

    async def edit_text_callback(self, interaction: discord.Interaction):
        txt = await self.campaign_service.get_followup_text()
        modal = FollowupTextModal(self.campaign_service, self.refresh_dashboard)
        modal.text_input.default = txt
        await interaction.response.send_modal(modal)

    async def edit_test_ids_callback(self, interaction: discord.Interaction):
        test_ids = await self.campaign_service.get_test_chat_ids()
        modal = TestChatIDsModal(self.campaign_service, self.refresh_dashboard)
        modal.chat_ids_input.default = ",\n".join(test_ids)
        await interaction.response.send_modal(modal)

    async def refresh_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await self.refresh_dashboard(interaction)


class CreatorSelect(discord.ui.Select):
    """Dropdown select menu for picking active creator models to cancel."""
    def __init__(self, creator_options: list[str]):
        options = [
            discord.SelectOption(label=f"@{c}", value=c, emoji="👤", description=f"Manage campaigns for @{c}")
            for c in creator_options
        ]
        if not options:
            options = [discord.SelectOption(label="No active creators", value="none")]
        super().__init__(placeholder="👤  Select a creator to manage...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class F2FCampaignsDashboardView(discord.ui.LayoutView):
    """Premium Components V2 Dashboard for managing and cancelling active creator campaigns."""
    def __init__(self, campaign_service: CampaignService, author: discord.User | discord.Member):
        super().__init__(timeout=86400)
        self.campaign_service = campaign_service
        self.author = author
        self.creator_select: CreatorSelect | None = None

    def _make_bar(self, value: int, max_val: int, length: int = 10) -> str:
        """Creates a clean Unicode progress bar."""
        if max_val <= 0:
            fill = 0
        else:
            fill = min(int((value / max_val) * length), length)
        return "▓" * fill + "░" * (length - fill)

    async def build_campaigns_container(self) -> discord.ui.Container:
        active_cmp = await self.campaign_service.get_active_campaigns()
        global_stats = await self.campaign_service.get_campaign_stats()

        sent_hour = global_stats['sent_this_hour']
        sent_today = global_stats['sent_today']
        replied = global_stats['replied_stop']
        total_sent = global_stats['total_sent']

        if not active_cmp:
            # ── Empty State ──
            container = discord.ui.Container(accent_color=discord.Color.from_str("#5865F2"))

            container.add_item(discord.ui.TextDisplay(
                content="# 📊 Campaign Dashboard"
            ))
            container.add_item(discord.ui.TextDisplay(
                content="-# Real-time outreach monitoring & management"
            ))

            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

            # Stats even when no campaigns
            container.add_item(discord.ui.TextDisplay(
                content=(
                    "### 📈 Lifetime Statistics\n"
                    f"╭ 📨 **Total Sent**  ›  `{total_sent:,}`\n"
                    f"╰ 💬 **Fan Replies**  ›  `{replied:,}`"
                )
            ))

            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

            container.add_item(discord.ui.TextDisplay(
                content=(
                    "### 💤 No Active Campaigns\n"
                    "*All outreach loops are currently idle.*\n"
                    "-# Data persists in MongoDB Atlas across restarts"
                )
            ))

            action_row = discord.ui.ActionRow()
            btn_refresh = discord.ui.Button(label="🔄 Refresh", style=discord.ButtonStyle.primary, custom_id="cmp_refresh")
            btn_refresh.callback = self.refresh_callback
            action_row.add_item(btn_refresh)
            container.add_item(action_row)
            return container

        # ── Active Dashboard ──
        # Group active campaigns by creator
        creator_summary = {}
        for cmp in active_cmp:
            creator = cmp.get("creator", "unknown")
            pending = cmp.get("pending_users_count", 0)
            if creator not in creator_summary:
                creator_summary[creator] = {"loops": 0, "pending_fans": 0, "latest_template": cmp.get("raw_message", "")}
            creator_summary[creator]["loops"] += 1
            creator_summary[creator]["pending_fans"] += pending

        total_pending = sum(info["pending_fans"] for info in creator_summary.values())
        total_creators = len(creator_summary)

        container = discord.ui.Container(accent_color=discord.Color.from_str("#57F287"))

        # ── Header ──
        container.add_item(discord.ui.TextDisplay(
            content="# 📊 Campaign Dashboard"
        ))
        container.add_item(discord.ui.TextDisplay(
            content=f"-# {total_creators} active creator{'s' if total_creators != 1 else ''}  •  {total_pending:,} fans in queue  •  Updated <t:{int(datetime.utcnow().timestamp())}:R>"
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Live Stats Panel ──
        # Build stat bars
        bar_hour = self._make_bar(sent_hour, max(sent_today, 1))
        bar_today = self._make_bar(sent_today, max(total_sent, 1))

        container.add_item(discord.ui.TextDisplay(
            content=(
                "### 📈 Live Statistics\n"
                f"**This Hour**   `{sent_hour:>5,}`  {bar_hour}\n"
                f"**Today**       `{sent_today:>5,}`  {bar_today}\n"
                f"**Replies**     `{replied:>5,}`  🛑\n"
                f"**All Time**    `{total_sent:>5,}`  📦"
            )
        ))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Creator Cards ──
        container.add_item(discord.ui.TextDisplay(
            content="### 👥 Active Creators"
        ))

        for creator, info in creator_summary.items():
            tpl = info["latest_template"]
            snippet = f"{tpl[:60]}..." if len(tpl) > 60 else tpl
            loops = info["loops"]
            pending = info["pending_fans"]

            status_dot = "🟢" if pending > 0 else "🟡"
            creator_card = (
                f"{status_dot} **@{creator}**\n"
                f"╭ 🔄 **Loops**: `{loops}`  ·  📬 **Queue**: `{pending:,}` fans\n"
                f"╰ 💬 *\"{snippet}\"*"
            )
            container.add_item(discord.ui.TextDisplay(content=creator_card))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        # ── Dropdown ──
        dropdown_row = discord.ui.ActionRow()
        self.creator_select = CreatorSelect(list(creator_summary.keys()))
        dropdown_row.add_item(self.creator_select)
        container.add_item(dropdown_row)

        # ── Action Buttons ──
        btn_row = discord.ui.ActionRow()
        btn_cancel_sel = discord.ui.Button(label="⏹️ Stop Selected", style=discord.ButtonStyle.danger, custom_id="cmp_cancel_sel")
        btn_cancel_all = discord.ui.Button(label="⏹️ Stop All", style=discord.ButtonStyle.secondary, custom_id="cmp_cancel_all")
        btn_refresh = discord.ui.Button(label="🔄 Refresh", style=discord.ButtonStyle.primary, custom_id="cmp_refresh")

        btn_cancel_sel.callback = self.cancel_selected_callback
        btn_cancel_all.callback = self.cancel_all_callback
        btn_refresh.callback = self.refresh_callback

        btn_row.add_item(btn_cancel_sel)
        btn_row.add_item(btn_cancel_all)
        btn_row.add_item(btn_refresh)

        container.add_item(btn_row)

        # ── Footer ──
        container.add_item(discord.ui.TextDisplay(
            content="-# 🗄️ Persistent storage via MongoDB Atlas  •  Survives restarts"
        ))

        return container

    async def initialize(self):
        self.clear_items()
        container = await self.build_campaigns_container()
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the user who opened `/campaigns` can use these controls.", ephemeral=True)
            return False
        return True

    async def cancel_selected_callback(self, interaction: discord.Interaction):
        if not self.creator_select or not self.creator_select.values or self.creator_select.values[0] == "none":
            await interaction.response.send_message("❌ Please select a creator model from the dropdown first.", ephemeral=True)
            return

        selected_creator = self.creator_select.values[0]
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        count = await self.campaign_service.cancel_creator_campaigns(selected_creator)
        await interaction.followup.send(f"🛑 **Cancelled all active campaigns for creator @{selected_creator} in Cloud MongoDB Atlas!**", ephemeral=True)
        await self.refresh_dashboard(interaction)

    async def cancel_all_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        count = await self.campaign_service.cancel_all_campaigns()
        await interaction.followup.send(f"🛑 **Cancelled {count} active campaign(s) in Cloud MongoDB Atlas!**", ephemeral=True)
        await self.refresh_dashboard(interaction)

    async def refresh_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await self.refresh_dashboard(interaction)

    async def refresh_dashboard(self, interaction: discord.Interaction):
        await self.initialize()
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            logger.warning(f"Campaigns dashboard refresh exception: {e}")


class F2FForwardViewV2(discord.ui.LayoutView):
    """Pure Components V2 Prompt View for Outreach Campaigns (NO EMBEDS!)."""
    def __init__(self, campaign_service: CampaignService, creator_name: str, raw_message: str, author: discord.User | discord.Member):
        super().__init__(timeout=300)
        self.campaign_service = campaign_service
        self.creator_name = creator_name
        self.raw_message = raw_message
        self.author = author

        self.container = discord.ui.Container(accent_color=discord.Color.from_str("#EB459E"))

        self.container.add_item(discord.ui.TextDisplay(
            content=f"# ⚡ Outreach Prompt"
        ))
        self.container.add_item(discord.ui.TextDisplay(
            content=f"-# Target Model: **@{creator_name}**  •  Verified on F2F ✅"
        ))

        self.container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        self.container.add_item(discord.ui.TextDisplay(
            content=(
                "### 💬 Raw Template Message\n"
                f"> *\"{raw_message}\"*"
            )
        ))

        self.container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        self.container.add_item(discord.ui.TextDisplay(
            content="-# Select an action below to test or launch the continuous outreach campaign:"
        ))

        row1 = discord.ui.ActionRow()
        row2 = discord.ui.ActionRow()

        btn_prod = discord.ui.Button(label="🚀 Start Continuous Loop", style=discord.ButtonStyle.success, custom_id="f2f_forward_prod")
        btn_test_init = discord.ui.Button(label="🧪 Test Initial", style=discord.ButtonStyle.primary, custom_id="f2f_test_init")
        btn_test_cooldown = discord.ui.Button(label="🛡️ Test Cooldown", style=discord.ButtonStyle.secondary, custom_id="f2f_test_cooldown")
        btn_test_follow = discord.ui.Button(label="🔁 Test Follow-Up", style=discord.ButtonStyle.secondary, custom_id="f2f_test_follow")
        btn_cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="f2f_cancel_prompt")

        btn_prod.callback = self.forward_prod_callback
        btn_test_init.callback = self.test_init_callback
        btn_test_cooldown.callback = self.test_cooldown_callback
        btn_test_follow.callback = self.test_followup_callback
        btn_cancel.callback = self.cancel_callback

        row1.add_item(btn_prod)
        row1.add_item(btn_test_init)
        row1.add_item(btn_test_cooldown)

        row2.add_item(btn_test_follow)
        row2.add_item(btn_cancel)

        self.container.add_item(row1)
        self.container.add_item(row2)
        self.add_item(self.container)

        self._is_processing = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the manager who clicked this command can use these controls.", ephemeral=True)
            return False
        if self._is_processing:
            await interaction.response.send_message("⏳ Action already processing, please wait a moment...", ephemeral=True)
            return False
        return True

    async def forward_prod_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cmp_id = await self.campaign_service.start_auto_rescan(
            creator=self.creator_name,
            raw_message=self.raw_message
        )

        cooldown_h = await self.campaign_service.get_cooldown_hours()
        await interaction.followup.send(
            f"🚀 **Continuous Outreach Loop Active for @{self.creator_name}**!\n"
            f"- 🆔 Campaign ID: `{cmp_id}`\n"
            f"- 🔄 Rescanning for newly online fans every **15 seconds**.\n"
            f"- 🛡️ Enforcing **{cooldown_h}-Hour Cooldown Guard** (No fan receives duplicate initial messages).\n"
            f"- 👁️ Follow-ups dispatched ONLY to fans who **have opened & seen (`read: true`)** the initial message!",
            ephemeral=True
        )

    async def test_cooldown_callback(self, interaction: discord.Interaction):
        self._is_processing = True
        try:
            await interaction.response.defer(ephemeral=True)
            test_ids = await self.campaign_service.get_test_chat_ids()

            results = []
            for idx, tid in enumerate(test_ids, 1):
                res = await self.campaign_service.execute_outreach_campaign(
                    creator=self.creator_name,
                    raw_message=self.raw_message,
                    test_chat_id=tid,
                    enforce_cooldown=True
                )
                fan_name = res.get("target_fan_name", "Fan")
                status = res.get("status")

                if status == "success":
                    personalized = res.get("personalized_text", "")
                    results.append(f"• ✅ **{fan_name}** (`{tid[:8]}...`): Initial Message Sent! (*\"{personalized}\"*)")
                elif status == "cooldown_blocked":
                    reason = res.get("reason", "")
                    results.append(f"• 🛡️ **{fan_name}** (`{tid[:8]}...`): **COOLDOWN TRIGGERED** — {reason}")
                else:
                    err = res.get("reason", "Unknown error")
                    results.append(f"• ❌ `{tid[:8]}...`: {err}")

                if idx < len(test_ids):
                    delay = random.uniform(3.0, 4.5)
                    await asyncio.sleep(delay)

            out_lines = [f"🛡️ **TEST 4H COOLDOWN GUARD for @{self.creator_name}**:\n"]
            out_lines.extend(results)
            await interaction.followup.send("\n".join(out_lines), ephemeral=True)
        finally:
            self._is_processing = False

    async def test_init_callback(self, interaction: discord.Interaction):
        self._is_processing = True
        try:
            await interaction.response.defer(ephemeral=True)
            test_ids = await self.campaign_service.get_test_chat_ids()
            
            success_results = []
            error_results = []

            for idx, tid in enumerate(test_ids, 1):
                res = await self.campaign_service.execute_outreach_campaign(
                    creator=self.creator_name,
                    raw_message=self.raw_message,
                    test_chat_id=tid
                )
                if res.get("status") == "success":
                    fan_name = res.get("target_fan_name", "Fan")
                    personalized = res.get("personalized_text", "")
                    success_results.append(f"• **{fan_name}** (`{tid[:8]}...`): *\"{personalized}\"*")
                else:
                    err = res.get("reason", "Unknown error")
                    error_results.append(f"• `{tid[:8]}...`: {err}")

                if idx < len(test_ids):
                    delay = random.uniform(3.0, 4.5)
                    await asyncio.sleep(delay)

            out_lines = [f"🧪 **TEST INITIAL DISPATCH for @{self.creator_name} ({len(success_results)}/{len(test_ids)} Successful)**:\n"]
            if success_results:
                out_lines.extend(success_results)
            if error_results:
                out_lines.append("\n**Failures:**")
                out_lines.extend(error_results)

            await interaction.followup.send("\n".join(out_lines), ephemeral=True)
        finally:
            self._is_processing = False

    async def test_followup_callback(self, interaction: discord.Interaction):
        self._is_processing = True
        try:
            await interaction.response.defer(ephemeral=True)
            test_ids = await self.campaign_service.get_test_chat_ids()

            out_lines = [f"🔁 **TEST FOLLOW-UP DISPATCH for @{self.creator_name} ({len(test_ids)} target(s))**:\n"]

            for idx, tid in enumerate(test_ids, 1):
                res = await self.campaign_service.execute_test_followup(
                    creator=self.creator_name,
                    test_chat_id=tid
                )
                status = res.get("status")
                if status == "success":
                    fan_name = res.get("fan_name", "Fan")
                    personalized = res.get("sent_text", "")
                    out_lines.append(f"• ✅ **{fan_name}** (`{tid[:8]}...`): *\"{personalized}\"*")
                elif status == "stopped":
                    reason = res.get("reason", "")
                    out_lines.append(f"• 🛑 (`{tid[:8]}...`): {reason}")
                else:
                    reason = res.get("reason", "Unknown error")
                    out_lines.append(f"• ❌ (`{tid[:8]}...`): {reason}")

                if idx < len(test_ids):
                    delay = random.uniform(3.0, 4.5)
                    await asyncio.sleep(delay)

            await interaction.followup.send("\n".join(out_lines), ephemeral=True)
        finally:
            self._is_processing = False

    async def cancel_callback(self, interaction: discord.Interaction):
        await self.campaign_service.cancel_creator_campaigns(self.creator_name)
        self.clear_items()
        c = discord.ui.Container(accent_color=discord.Color.red())
        c.add_item(discord.ui.TextDisplay(content=f"❌ **Campaign Prompt Cancelled for @{self.creator_name}**."))
        self.add_item(c)
        await interaction.response.edit_message(view=self)


class F2FAutomation(commands.Cog):
    def __init__(self, bot: commands.Bot, campaign_service: CampaignService):
        self.bot = bot
        self.campaign_service = campaign_service
        self.campaign_service.event_callback = self.dispatch_log_event
        if self.campaign_service.f2f_client:
            self.campaign_service.f2f_client.event_callback = self.dispatch_log_event

        self.ctx_menu = app_commands.ContextMenu(
            name="Send as F2F Campaign",
            callback=self.send_f2f_campaign_ctx
        )
        self.bot.tree.add_command(self.ctx_menu)

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensures dedicated #f2f_logs channel is verified or created immediately on bot startup."""
        logger.info(f"Checking for dedicated audit log channel across {len(self.bot.guilds)} connected server(s)...")
        ch = await get_or_create_f2f_logs_channel(self.bot)
        if ch:
            logger.info(f"✅ Verified dedicated audit log channel '#{ch.name}' in guild '{ch.guild.name}' (ID: {ch.id}).")
        else:
            logger.warning("Could not locate or auto-create #f2f_logs channel. Please check server permissions or create #f2f_logs manually.")

    async def dispatch_log_event(self, title: str, description: str, level: str = "info"):
        """Dispatches creator-level event notifications to private #f2f_logs channel."""
        await send_f2f_log(self.bot, title, description, level)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def send_f2f_campaign_ctx(self, interaction: discord.Interaction, message: discord.Message):
        """Context menu action to forward a Discord message to creator's online F2F fans."""
        if not message.content:
            await interaction.response.send_message("❌ **No Text Found**: The selected message does not contain text. Please select a message with text content to launch a campaign prompt.", ephemeral=True)
            return

        creator_handle = re.sub(r'[^\x00-\x7F]+', '', interaction.channel.name).lower().replace("#", "").strip()
        if not creator_handle:
            await interaction.response.send_message("❌ **Channel Error**: Could not detect a creator handle from this channel name. Please make sure the channel is named after the creator handle (e.g. `#aylen`).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        is_valid = await self.campaign_service.f2f_client.validate_creator_exists(creator_handle)
        if not is_valid:
            await interaction.followup.send(
                f"❌ **Creator Not Found on F2F**: Creator **@{creator_handle}** was not found or is unauthorized on your F2F agency account.\n"
                f"Please check that the channel name **#{interaction.channel.name}** matches the exact F2F model handle.",
                ephemeral=True
            )
            return

        view = F2FForwardViewV2(
            campaign_service=self.campaign_service,
            creator_name=creator_handle,
            raw_message=message.content,
            author=interaction.user
        )
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="f2f_config", description="View & Configure F2F Automation Settings (Owner only)")
    async def f2f_config_cmd(self, interaction: discord.Interaction):
        view = F2FConfigDashboardView(self.campaign_service, interaction.user)
        await view.initialize()
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="campaigns", description="View and manage active F2F outreach campaigns")
    async def campaigns_cmd(self, interaction: discord.Interaction):
        view = F2FCampaignsDashboardView(self.campaign_service, interaction.user)
        await view.initialize()
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    pass
