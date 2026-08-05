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


class F2FConfigDashboardView(discord.ui.LayoutView):
    def __init__(self, campaign_service: CampaignService, author: discord.User | discord.Member):
        super().__init__(timeout=86400)
        self.campaign_service = campaign_service
        self.author = author

    async def build_dashboard_container(self) -> discord.ui.Container:
        gap = await self.campaign_service.get_followup_gap()
        followup_txt = await self.campaign_service.get_followup_text()
        test_ids = await self.campaign_service.get_test_chat_ids()
        has_session = bool(self.campaign_service.f2f_client.session_id)
        has_totp = bool(self.campaign_service.f2f_client.totp_secret)

        session_str = f"`{self.campaign_service.f2f_client.session_id[:10]}...`" if has_session else "❌ None"
        totp_str = "✅ Configured" if has_totp else "❌ Not Configured"

        test_ids_formatted = ", ".join([f"`{tid[:8]}...`" for tid in test_ids]) if test_ids else "❌ None"

        text = (
            "## ⚙️ F2F Automation Settings & Status\n"
            f"• **Session Status**: {session_str}\n"
            f"• **Autonomous 2FA (pyotp)**: {totp_str}\n"
            f"• **Follow-Up Gap Interval**: `{gap} minute(s)`\n"
            f"• **Active Test Target UUIDs**: {test_ids_formatted}\n"
            f"• **Follow-Up Template**:\n> {followup_txt}\n\n"
            "Use the buttons below to edit configuration parameters anytime."
        )

        container = discord.ui.Container(accent_color=discord.Color.blue())
        container.add_item(discord.ui.TextDisplay(content=text))

        row1 = discord.ui.ActionRow()
        btn_gap = discord.ui.Button(label="⏱️ Edit Follow-Up Gap", style=discord.ButtonStyle.primary, custom_id="cfg_gap")
        btn_text = discord.ui.Button(label="📝 Edit Template Text", style=discord.ButtonStyle.primary, custom_id="cfg_text")
        btn_test_ids = discord.ui.Button(label="🎯 Edit Test Target UUIDs", style=discord.ButtonStyle.secondary, custom_id="cfg_test_ids")
        btn_refresh = discord.ui.Button(label="🔄 Refresh Dashboard", style=discord.ButtonStyle.secondary, custom_id="cfg_refresh")

        btn_gap.callback = self.edit_gap_callback
        btn_text.callback = self.edit_text_callback
        btn_test_ids.callback = self.edit_test_ids_callback
        btn_refresh.callback = self.refresh_callback

        row1.add_item(btn_gap)
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
            discord.SelectOption(label=f"@{c}", value=c, description=f"Manage outreach campaigns for creator @{c}")
            for c in creator_options
        ]
        if not options:
            options = [discord.SelectOption(label="No active creators", value="none")]
        super().__init__(placeholder="Select a Creator Model to cancel...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class F2FCampaignsDashboardView(discord.ui.LayoutView):
    """Clean Components V2 Dashboard for managing and cancelling active creator campaigns."""
    def __init__(self, campaign_service: CampaignService, author: discord.User | discord.Member):
        super().__init__(timeout=86400)
        self.campaign_service = campaign_service
        self.author = author
        self.creator_select: CreatorSelect | None = None

    async def build_campaigns_container(self) -> discord.ui.Container:
        active_cmp = await self.campaign_service.get_active_campaigns()
        
        if not active_cmp:
            text = (
                "## 🌐 F2F Active Campaigns Manager\n"
                "No active outreach campaigns running right now.\n\n"
                "All follow-up loops are stored persistently in **Cloud MongoDB Atlas** and survive bot & Discord restarts!"
            )
            container = discord.ui.Container(accent_color=discord.Color.blue())
            container.add_item(discord.ui.TextDisplay(content=text))

            action_row = discord.ui.ActionRow()
            btn_refresh = discord.ui.Button(label="🔄 Refresh Active Campaigns", style=discord.ButtonStyle.secondary, custom_id="cmp_refresh")
            btn_refresh.callback = self.refresh_callback
            action_row.add_item(btn_refresh)

            container.add_item(action_row)
            return container

        # Group active campaigns by creator handle for clean summary!
        creator_summary = {}
        for cmp in active_cmp:
            creator = cmp.get("creator", "unknown")
            pending = cmp.get("pending_users_count", 0)
            if creator not in creator_summary:
                creator_summary[creator] = {"loops": 0, "pending_fans": 0, "latest_template": cmp.get("raw_message", "")}
            creator_summary[creator]["loops"] += 1
            creator_summary[creator]["pending_fans"] += pending

        lines = ["## 🌐 F2F Active Campaigns Manager\n*Stored in Cloud MongoDB Atlas — Persists across restarts!*\n"]
        for creator, info in creator_summary.items():
            tpl = info["latest_template"]
            snippet = f"\"{tpl[:40]}...\"" if len(tpl) > 40 else f"\"{tpl}\""
            lines.append(
                f"• **Creator @{creator}**: **{info['loops']}** active campaign loop(s) | "
                f"Pending Fans: **{info['pending_fans']}**\n  > Prompt: *{snippet}*"
            )

        lines.append("\nSelect a creator model from the dropdown below to cancel running outreach loops.")
        dashboard_text = "\n".join(lines)

        container = discord.ui.Container(accent_color=discord.Color.green())
        container.add_item(discord.ui.TextDisplay(content=dashboard_text))

        # Dropdown Action Row
        dropdown_row = discord.ui.ActionRow()
        self.creator_select = CreatorSelect(list(creator_summary.keys()))
        dropdown_row.add_item(self.creator_select)
        container.add_item(dropdown_row)

        # Buttons Action Row
        btn_row = discord.ui.ActionRow()
        btn_cancel_sel = discord.ui.Button(label="🛑 Cancel Selected Creator", style=discord.ButtonStyle.danger, custom_id="cmp_cancel_sel")
        btn_cancel_all = discord.ui.Button(label="🛑 Cancel ALL Campaigns", style=discord.ButtonStyle.secondary, custom_id="cmp_cancel_all")
        btn_refresh = discord.ui.Button(label="🔄 Refresh Dashboard", style=discord.ButtonStyle.secondary, custom_id="cmp_refresh")

        btn_cancel_sel.callback = self.cancel_selected_callback
        btn_cancel_all.callback = self.cancel_all_callback
        btn_refresh.callback = self.refresh_callback

        btn_row.add_item(btn_cancel_sel)
        btn_row.add_item(btn_cancel_all)
        btn_row.add_item(btn_refresh)

        container.add_item(btn_row)
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

        self.container = discord.ui.Container(accent_color=discord.Color.blue())
        prompt_text = (
            f"## ⚡ F2F Outreach Campaign Prompt (@{self.creator_name})\n"
            f"Creator **@{self.creator_name}** verified on F2F ✅\n\n"
            f"**Raw Template Message:**\n> {self.raw_message}\n\n"
            f"*Select an outreach action below to dispatch message.*"
        )
        self.container.add_item(discord.ui.TextDisplay(content=prompt_text))

        row1 = discord.ui.ActionRow()
        row2 = discord.ui.ActionRow()

        btn_prod = discord.ui.Button(label="🚀 Start Continuous Outreach Loop", style=discord.ButtonStyle.success, custom_id="f2f_forward_prod")
        btn_test_init = discord.ui.Button(label="🧪 Test Initial Message", style=discord.ButtonStyle.primary, custom_id="f2f_test_init")
        btn_test_cooldown = discord.ui.Button(label="🛡️ Test 4h Cooldown Guard", style=discord.ButtonStyle.secondary, custom_id="f2f_test_cooldown")
        btn_test_follow = discord.ui.Button(label="🔁 Test Follow-Up Message", style=discord.ButtonStyle.secondary, custom_id="f2f_test_follow")
        btn_cancel = discord.ui.Button(label="❌ Cancel Prompt", style=discord.ButtonStyle.danger, custom_id="f2f_cancel_prompt")

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

        await interaction.followup.send(
            f"🚀 **Continuous Outreach Loop Active for @{self.creator_name}**!\n"
            f"- 🆔 Campaign ID: `{cmp_id}`\n"
            f"- 🔄 Rescanning for newly online fans every **15 seconds**.\n"
            f"- 🛡️ Enforcing **4-Hour Cooldown Guard** (No fan receives duplicate initial messages).\n"
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
