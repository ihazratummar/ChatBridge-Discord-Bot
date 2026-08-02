import logging
import discord
from discord import app_commands
from discord.ext import commands
from core.bridge_service import BridgeService

logger = logging.getLogger("ChatBridge.OwnerCommands")

class OwnerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, bridge_service: BridgeService):
        self.bot = bot
        self.bridge_service = bridge_service

    @app_commands.command(name="setup-sync", description="Quick 2-way sync setup between 2 Discord channels.")
    @app_commands.describe(channel1="First Discord Channel", channel2="Second Discord Channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_sync(self, interaction: discord.Interaction, channel1: discord.TextChannel, channel2: discord.TextChannel):
        await interaction.response.defer(ephemeral=False)
        if channel1.id == channel2.id:
            await interaction.followup.send("❌ Cannot sync a channel with itself!")
            return

        grp_id = f"grp_{channel1.id}_{channel2.id}"
        await self.bridge_service.db.create_group(grp_id, f"1:1 Pair {channel1.id}-{channel2.id}")
        await self.bridge_service.db.add_or_update_member(grp_id, channel1.id, mode="bidirectional")
        await self.bridge_service.db.add_or_update_member(grp_id, channel2.id, mode="bidirectional")

        await self.bridge_service.reload_cache()
        await interaction.followup.send(f"✅ **2-Way Sync Created** between {channel1.mention} and {channel2.mention}!")

    @app_commands.command(name="bridge-create", description="Create a new named multi-channel bridge group.")
    @app_commands.describe(group_name="Name for the bridge group (e.g. Creator-Mesh)")
    @app_commands.checks.has_permissions(administrator=True)
    async def bridge_create(self, interaction: discord.Interaction, group_name: str):
        await interaction.response.defer(ephemeral=False)
        grp_id = await self.bridge_service.db.create_group(name=group_name)
        await self.bridge_service.reload_cache()
        await interaction.followup.send(f"✅ **Created Bridge Group**: **{group_name}** (`{grp_id}`)")

    @app_commands.command(name="bridge-add", description="Add a channel to a bridge group with routing mode.")
    @app_commands.describe(
        group_id="Group ID to add channel to",
        channel="Discord Text Channel",
        mode="Routing mode: bidirectional, send_only, or receive_only",
        bot_name="Custom bot identity name for outgoing messages (optional)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Bidirectional (Send & Receive)", value="bidirectional"),
        app_commands.Choice(name="Send Only (Broadcast to Group)", value="send_only"),
        app_commands.Choice(name="Receive Only (Listen to Group)", value="receive_only")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def bridge_add(self, interaction: discord.Interaction, group_id: str, channel: discord.TextChannel, mode: app_commands.Choice[str], bot_name: str | None = None):
        await interaction.response.defer(ephemeral=False)
        await self.bridge_service.db.add_or_update_member(
            group_id=group_id,
            channel_id=channel.id,
            mode=mode.value,
            bot_name=bot_name or "ChatBridge Bot"
        )
        await self.bridge_service.reload_cache()
        await interaction.followup.send(f"✅ Added {channel.mention} to group `{group_id}` in **{mode.name}** mode!")

    @app_commands.command(name="bridge-remove", description="Remove a channel from a bridge group or all groups.")
    @app_commands.describe(channel="Discord Text Channel to remove", group_id="Specific Group ID (optional, leave blank to remove from all)")
    @app_commands.checks.has_permissions(administrator=True)
    async def bridge_remove(self, interaction: discord.Interaction, channel: discord.TextChannel, group_id: str | None = None):
        await interaction.response.defer(ephemeral=False)
        if group_id:
            removed = await self.bridge_service.db.remove_member(group_id, channel.id)
            msg = f"✅ Removed {channel.mention} from group `{group_id}`." if removed else "❌ Channel was not in specified group."
        else:
            count = await self.bridge_service.db.remove_channel_from_all_groups(channel.id)
            msg = f"✅ Removed {channel.mention} from **{count}** bridge group(s)."

        await self.bridge_service.reload_cache()
        await interaction.followup.send(msg)

    @app_commands.command(name="set-name", description="Set custom bot display name for a channel in bridge groups.")
    @app_commands.describe(channel="Target Channel", bot_name="Bot identity display name (e.g. Message Notifier)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_name(self, interaction: discord.Interaction, channel: discord.TextChannel, bot_name: str):
        await interaction.response.defer(ephemeral=False)
        await self.bridge_service.db.update_member_config(channel_id=channel.id, bot_name=bot_name)
        await self.bridge_service.reload_cache()
        await interaction.followup.send(f"✅ Updated bot identity display name for {channel.mention} to **\"{bot_name}\"**!")

    @app_commands.command(name="set-role", description="Set role ping ID triggered when messages arrive in a channel.")
    @app_commands.describe(channel="Target Channel", role="Role to ping when messages arrive (or leave blank to clear)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_role(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role | None = None):
        await interaction.response.defer(ephemeral=False)
        role_id_str = str(role.id) if role else None
        await self.bridge_service.db.update_member_config(channel_id=channel.id, role_id=role_id_str)
        await self.bridge_service.reload_cache()
        msg = f"✅ Set role ping for {channel.mention} to {role.mention}." if role else f"✅ Cleared role pings for {channel.mention}."
        await interaction.followup.send(msg)

    @app_commands.command(name="sync-status", description="Check all active channel bridge sync groups.")
    async def sync_status(self, interaction: discord.Interaction):
        groups = await self.bridge_service.db.get_all_groups()
        embed = discord.Embed(title="🌐 Active Channel Bridge Groups", color=discord.Color.blue())
        for g in groups[:10]:
            members_info = []
            for m in g.get("members", []):
                role_info = f" <@&{m['role_id']}>" if m.get("role_id") else ""
                members_info.append(f"<#{m['channel_id']}> ({m.get('mode', 'bidirectional')}) [{m.get('bot_name', 'ChatBridge')}){role_info}")
            embed.add_field(name=f"Group: {g['name']} (`{g['id']}`)", value="\n".join(members_info) or "No channels", inline=False)
        await interaction.response.send_message(embed=embed)
