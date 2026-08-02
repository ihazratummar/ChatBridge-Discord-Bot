import logging
import discord
from discord import app_commands
from discord.ext import commands
from services.campaign_service import CampaignService

logger = logging.getLogger("ChatBridge.F2FAutomationCog")

TEST_CHAT_ID = "e85d76cb-ff3b-4f3d-a6ff-cfad7b1f6b57"

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


class F2FConfigDashboardView(discord.ui.LayoutView):
    def __init__(self, campaign_service: CampaignService, author: discord.User | discord.Member):
        super().__init__(timeout=600)
        self.campaign_service = campaign_service
        self.author = author

    async def build_dashboard_container(self) -> discord.ui.Container:
        gap = await self.campaign_service.get_followup_gap()
        followup_txt = await self.campaign_service.get_followup_text()
        has_session = bool(self.campaign_service.f2f_client.session_id)
        has_totp = bool(self.campaign_service.f2f_client.totp_secret)

        session_str = f"`{self.campaign_service.f2f_client.session_id[:10]}...`" if has_session else "❌ None"
        totp_str = "✅ Configured" if has_totp else "❌ Not Configured"

        dashboard_text = (
            "## ⚡ F2F Automation Config & Status Dashboard\n"
            "Manage your F2F automation parameters, follow-up gap interval, and template message below.\n\n"
            f"- 🔑 **Active Session ID**: {session_str}\n"
            f"- 🔐 **Autonomous 2FA (pyotp)**: {totp_str}\n"
            f"- ⏱️ **Follow-up Gap Time**: **{gap} minute(s)**\n"
            f"- 💬 **Follow-up Message Template**:\n> {followup_txt}\n\n"
            f"*Supports `(name)`, `[name]`, `{{name}}`, `<name>` and leading `Schatje,`*\n\n"
            f"- 🎯 **Test Target Chat ID**: `{TEST_CHAT_ID}`"
        )

        container = discord.ui.Container(accent_color=discord.Color.green() if has_session else discord.Color.gold())
        container.add_item(discord.ui.TextDisplay(content=dashboard_text))

        # ActionRow (type 1) inside Container (type 17) to house buttons (type 2) per Discord V2 spec
        action_row = discord.ui.ActionRow()

        btn_gap = discord.ui.Button(label="⏱️ Edit Follow-Up Gap", style=discord.ButtonStyle.primary, custom_id="f2f_edit_gap")
        btn_text = discord.ui.Button(label="💬 Edit Follow-Up Message", style=discord.ButtonStyle.primary, custom_id="f2f_edit_text")
        btn_refresh = discord.ui.Button(label="🔄 Refresh Dashboard", style=discord.ButtonStyle.secondary, custom_id="f2f_refresh_dashboard")

        btn_gap.callback = self.edit_gap_callback
        btn_text.callback = self.edit_text_callback
        btn_refresh.callback = self.refresh_callback

        action_row.add_item(btn_gap)
        action_row.add_item(btn_text)
        action_row.add_item(btn_refresh)

        container.add_item(action_row)
        return container

    async def initialize(self):
        self.clear_items()
        container = await self.build_dashboard_container()
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the owner who ran `/f2f-config` can edit settings.", ephemeral=True)
            return False
        return True

    async def refresh_dashboard(self, interaction: discord.Interaction):
        await self.initialize()
        try:
            if interaction.response.is_done():
                await interaction.message.edit(view=self)
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

    async def refresh_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.refresh_dashboard(interaction)


class F2FForwardView(discord.ui.View):
    def __init__(self, campaign_service: CampaignService, creator_name: str, raw_message: str, author: discord.User | discord.Member):
        super().__init__(timeout=300)
        self.campaign_service = campaign_service
        self.creator_name = creator_name
        self.raw_message = raw_message
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the manager who posted this message can click these controls.", ephemeral=True)
            return False
        return True

    # Main Production Forward Button temporarily disabled for testing safety
    # @discord.ui.button(label="🚀 Forward to F2F Online Chats", style=discord.ButtonStyle.success, custom_id="f2f_forward_prod")
    # async def forward_prod(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     await interaction.response.defer(ephemeral=False)
    #     for child in self.children:
    #         child.disabled = True
    #     await interaction.edit_original_response(content=f"⏳ **Dispatching Production Campaign** for @{self.creator_name} to online fans...", view=self)
    #
    #     res = await self.campaign_service.execute_outreach_campaign(
    #         creator=self.creator_name,
    #         raw_message=self.raw_message
    #     )
    #
    #     sent = res.get("sent_count", 0)
    #     skipped = res.get("skipped_replied", 0)
    #     cmp_id = res.get("campaign_id", "")
    #     await interaction.followup.send(
    #         f"✅ **Production Campaign Executed for @{self.creator_name}**!\n"
    #         f"- 🆔 Campaign ID: `{cmp_id}`\n"
    #         f"- 📨 Messages Sent: **{sent}**\n"
    #         f"- 🛑 Skipped (Already Replied): **{skipped}**\n"
    #         f"- ⏱️ Scheduled follow-up worker loop active!"
    #     )

    @discord.ui.button(label="🧪 Test Initial Message", style=discord.ButtonStyle.primary, custom_id="f2f_forward_test")
    async def forward_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        await interaction.edit_original_response(content=f"🧪 **Testing Initial Dispatch** for @{self.creator_name} to test chat `...{TEST_CHAT_ID[-8:]}`...", view=self)

        res = await self.campaign_service.execute_outreach_campaign(
            creator=self.creator_name,
            raw_message=self.raw_message,
            test_chat_id=TEST_CHAT_ID
        )

        if res.get("status") == "success":
            personalized = res.get("personalized_text", "")
            fan_name = res.get("target_fan_name", "Fan")
            await interaction.followup.send(
                f"🎉 **INITIAL TEST SUCCESSFUL for @{self.creator_name}**!\n"
                f"- 👤 Recipient Fan Name: **{fan_name}**\n"
                f"- 🎯 Target Chat ID: `{TEST_CHAT_ID}`\n"
                f"- 💬 Sent Text: *\"{personalized}\"*"
            )
        else:
            err = res.get("error", "Unknown error")
            await interaction.followup.send(f"❌ **INITIAL TEST FAILED**: {err}")

    @discord.ui.button(label="🔁 Test Follow-Up Message", style=discord.ButtonStyle.secondary, custom_id="f2f_test_followup")
    async def test_followup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        await interaction.edit_original_response(content=f"🔁 **Testing Follow-Up Dispatch** for @{self.creator_name} to test chat `...{TEST_CHAT_ID[-8:]}`...", view=self)

        res = await self.campaign_service.execute_test_followup(
            creator=self.creator_name,
            test_chat_id=TEST_CHAT_ID
        )

        status = res.get("status")
        if status == "success":
            personalized = res.get("sent_text", "")
            fan_name = res.get("fan_name", "Fan")
            await interaction.followup.send(
                f"🎉 **FOLLOW-UP TEST SUCCESSFUL for @{self.creator_name}**!\n"
                f"- 👤 Recipient Fan Name: **{fan_name}**\n"
                f"- 💬 Sent Follow-Up: *\"{personalized}\"*"
            )
        elif status == "stopped":
            reason = res.get("reason", "")
            await interaction.followup.send(f"🛑 **FOLLOW-UP SKIPPED (REPLY SAFETY CHECK)**:\n> {reason}")
        else:
            reason = res.get("reason", "Unknown error")
            await interaction.followup.send(f"❌ **FOLLOW-UP TEST FAILED**: {reason}")

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="f2f_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ **Campaign Forwarding Cancelled**.", view=self)


class F2FAutomation(commands.Cog):
    def __init__(self, bot: commands.Bot, campaign_service: CampaignService):
        self.bot = bot
        self.campaign_service = campaign_service
        self.campaign_service.start_worker()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id is not None:
            return

        channel_name = message.channel.name.lower()
        
        is_sniper_channel = (
            channel_name.startswith("xsophiex") or
            channel_name.startswith("aylen") or
            channel_name.startswith("sophie") or
            channel_name.startswith("chantal") or
            channel_name.startswith("taier") or
            (message.channel.category and "sniper" in message.channel.category.name.lower())
        )

        if not is_sniper_channel:
            return

        creator_handle = channel_name
        for prefix in ["👧", "👩", "👱‍♀️", "👩‍🦰", "🔔"]:
            creator_handle = creator_handle.replace(prefix, "")
        creator_handle = creator_handle.strip()

        view = F2FForwardView(
            campaign_service=self.campaign_service,
            creator_name=creator_handle,
            raw_message=message.content,
            author=message.author
        )

        embed = discord.Embed(
            title=f"F2F Outreach Forward Prompt (@{creator_handle})",
            description=f"Select an action to test forwarding message for **@{creator_handle}**:\n\n"
                        f"**Raw Message:**\n> {message.content}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Production forwarding is disabled. Use Test Chat buttons for safe testing.")

        await message.reply(embed=embed, view=view)

    @app_commands.command(name="f2f-config", description="[OWNER ONLY] Open interactive F2F Automation Config & Status Dashboard.")
    @app_commands.checks.has_permissions(administrator=True)
    async def f2f_config(self, interaction: discord.Interaction):
        """Single consolidated slash command to view and edit all F2F automation parameters via pure Components V2 LayoutView dashboard (No Embed)."""
        view = F2FConfigDashboardView(self.campaign_service, interaction.user)
        await view.initialize()
        await interaction.response.send_message(view=view)
