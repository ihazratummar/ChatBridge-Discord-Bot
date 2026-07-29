import logging
import discord
from discord import app_commands
from discord.ext import commands
from bridge_service import BridgeService

logger = logging.getLogger("ChatBridge.OwnerCommands")

def is_owner_or_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used inside a server channel.", ephemeral=True)
            return False
        is_owner = interaction.user.id == interaction.guild.owner_id
        is_admin = interaction.user.guild_permissions.administrator
        if is_owner or is_admin:
            return True
        await interaction.response.send_message("❌ Only the Server Owner or Administrators can configure bot sync settings.", ephemeral=True)
        return False
    return app_commands.check(predicate)

class OwnerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, bridge_service: BridgeService):
        self.bot = bot
        self.bridge_service = bridge_service

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global exception handler for owner commands cog."""
        if isinstance(error, app_commands.CheckFailure):
            # Handled in predicate
            return
        logger.error(f"Error executing command {interaction.command.name if interaction.command else 'Unknown'}: {error}", exc_info=True)
        msg = f"❌ An unexpected error occurred while executing the command: `{error}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    @app_commands.command(name="setup-sync", description="Bridge the current channel with a channel in another server (Owner/Admin only).")
    @app_commands.describe(
        target_channel_id="The numerical ID of the channel in the second server to sync with",
        bot_name_for_target="Display name when messages post in the target channel (Default: Forgotten Names)",
        bot_name_for_here="Display name when messages post in this channel (Default: Message Notifier)"
    )
    @is_owner_or_admin()
    async def setup_sync(self, interaction: discord.Interaction, target_channel_id: str,
                         bot_name_for_target: str = "Forgotten Names",
                         bot_name_for_here: str = "Message Notifier"):
        await interaction.response.defer(ephemeral=True)

        try:
            target_id = int(target_channel_id.strip())
        except ValueError:
            await interaction.followup.send("❌ Invalid target channel ID. Please provide a valid numerical channel ID.")
            return

        current_channel_id = interaction.channel_id
        if current_channel_id == target_id:
            await interaction.followup.send("❌ You cannot sync a channel with itself.")
            return

        # Register bridge pair in DB & Service Cache
        bridge_data = await self.bridge_service.setup_bridge(
            channel_a_id=current_channel_id,
            channel_b_id=target_id,
            name_a_to_b=bot_name_for_target,
            name_b_to_a=bot_name_for_here
        )

        embed = discord.Embed(
            title="✅ 2-Way Sync Configured Successfully!",
            color=discord.Color.green(),
            description=f"**Channel 1 (Here):** <#{current_channel_id}>\n"
                        f"**Channel 2 (Partner):** <#{target_id}>\n\n"
                        f"**Identity when posting in Partner Channel:** `{bot_name_for_target}`\n"
                        f"**Identity when posting in This Channel:** `{bot_name_for_here}`"
        )
        embed.set_footer(text="Use /set-role or /set-name to customize notifications and identity names anytime.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set-name", description="Set the display name for messages coming into a channel.")
    @app_commands.describe(
        custom_name="The name to show on relayed messages in this channel",
        channel_id="Optional target channel ID (defaults to current channel)"
    )
    @is_owner_or_admin()
    async def set_name(self, interaction: discord.Interaction, custom_name: str, channel_id: str = None):
        target_ch_id = interaction.channel_id
        if channel_id:
            try:
                target_ch_id = int(channel_id.strip())
            except ValueError:
                await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
                return

        success = await self.bridge_service.update_bot_name(target_ch_id, custom_name.strip())
        if success:
            await interaction.response.send_message(
                f"✅ Display name for messages posted into <#{target_ch_id}> updated to **{custom_name.strip()}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Channel <#{target_ch_id}> is not currently part of an active sync bridge. Run `/setup-sync` first.",
                ephemeral=True
            )

    @app_commands.command(name="set-role", description="Set the role to ping when messages arrive in a channel.")
    @app_commands.describe(
        role="Select a role to ping when a new message arrives",
        ping_everyone="Set to True to ping @everyone instead",
        channel_id="Optional target channel ID (defaults to current channel)"
    )
    @is_owner_or_admin()
    async def set_role(self, interaction: discord.Interaction, role: discord.Role = None, ping_everyone: bool = False, channel_id: str = None):
        target_ch_id = interaction.channel_id
        if channel_id:
            try:
                target_ch_id = int(channel_id.strip())
            except ValueError:
                await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
                return

        if ping_everyone:
            role_val = "everyone"
            disp = "@everyone"
        elif role:
            role_val = str(role.id)
            disp = role.mention
        else:
            role_val = None
            disp = "None (Disabled)"

        success = await self.bridge_service.update_role_ping(target_ch_id, role_val)
        if success:
            await interaction.response.send_message(
                f"✅ Notification ping for messages posted into <#{target_ch_id}> updated to **{disp}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Channel <#{target_ch_id}> is not currently part of an active sync bridge.",
                ephemeral=True
            )

    @app_commands.command(name="sync-status", description="Check current 2-way sync bridge settings.")
    @is_owner_or_admin()
    async def sync_status(self, interaction: discord.Interaction):
        ch_id = interaction.channel_id
        route = self.bridge_service.get_route(ch_id)

        if not route:
            await interaction.response.send_message("ℹ️ This channel is not currently bridged. Use `/setup-sync` to pair it.", ephemeral=True)
            return

        partner_id = route["target_channel_id"]
        partner_route = self.bridge_service.get_route(partner_id)

        this_cfg = partner_route["config"] if partner_route else {}  # config for messages posted into HERE
        partner_cfg = route["config"]  # config for messages posted into PARTNER

        role_ping = this_cfg.get("role_id")
        if role_ping == "everyone":
            role_disp = "@everyone"
        elif role_ping:
            role_disp = f"<@&{role_ping}>"
        else:
            role_disp = "None"

        embed = discord.Embed(title="🔗 ChatBridge Sync Status", color=discord.Color.blue())
        embed.add_field(name="Current Channel", value=f"<#{ch_id}> (`{ch_id}`)", inline=False)
        embed.add_field(name="Partner Channel", value=f"<#{partner_id}> (`{partner_id}`)", inline=False)
        embed.add_field(name="Name when posting HERE", value=this_cfg.get("bot_name", "N/A"), inline=True)
        embed.add_field(name="Name when posting in PARTNER", value=partner_cfg.get("bot_name", "N/A"), inline=True)
        embed.add_field(name="Role Notification HERE", value=role_disp, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unlink-sync", description="Remove 2-way sync bridge for a channel.")
    @is_owner_or_admin()
    async def unlink_sync(self, interaction: discord.Interaction):
        ch_id = interaction.channel_id
        success = await self.bridge_service.remove_bridge(ch_id)
        if success:
            await interaction.response.send_message(f"✅ Unlinked channel <#{ch_id}> from sync bridge.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ This channel is not in an active sync bridge.", ephemeral=True)

async def setup(bot: commands.Bot):
    pass
