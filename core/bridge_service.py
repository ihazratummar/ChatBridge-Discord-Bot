import io
import logging
import asyncio
import discord
from typing import Dict, List, Any

logger = logging.getLogger("ChatBridge.BridgeService")

DISCORD_MAX_TEXT_LEN = 1950

class BridgeService:
    def __init__(self, bot, db_manager):
        self.bot = bot
        self.db = db_manager
        self.channel_to_groups: Dict[int, List[dict]] = {}

    async def reload_cache(self):
        """Reloads active bridge groups and member routing mappings from Database."""
        groups = await self.db.get_all_groups()
        new_mapping: Dict[int, List[dict]] = {}

        for group in groups:
            grp_id = group["id"]
            members = group.get("members", [])
            for member in members:
                ch_id = int(member["channel_id"])
                if ch_id not in new_mapping:
                    new_mapping[ch_id] = []
                member_entry = dict(member)
                member_entry["group_id"] = grp_id
                new_mapping[ch_id].append(member_entry)

        self.channel_to_groups = new_mapping
        logger.info(f"Bridge cache loaded: {len(groups)} groups routing {len(new_mapping)} source channels.")

    async def handle_incoming_message(self, message: discord.Message):
        """Processes incoming Discord message and relays it across active bridge channels."""
        if message.author.bot or message.webhook_id is not None:
            return

        source_channel_id = message.channel.id
        if source_channel_id not in self.channel_to_groups:
            return

        groups_for_source = self.channel_to_groups[source_channel_id]
        targets_to_dispatch = []

        for grp_config in groups_for_source:
            group_id = grp_config["group_id"]
            source_mode = grp_config.get("mode", "bidirectional")

            if source_mode == "receive_only":
                continue

            all_groups = await self.db.get_all_groups()
            target_group = next((g for g in all_groups if g["id"] == group_id), None)
            if not target_group:
                continue

            for target_member in target_group.get("members", []):
                target_channel_id = int(target_member["channel_id"])
                if target_channel_id == source_channel_id:
                    continue

                target_mode = target_member.get("mode", "bidirectional")
                if target_mode == "send_only":
                    continue

                targets_to_dispatch.append({
                    "group_id": group_id,
                    "target_member": target_member
                })

        if not targets_to_dispatch:
            return

        # Prepare attachments
        cached_attachments = []
        for att in message.attachments:
            try:
                raw_bytes = await att.read()
                cached_attachments.append((att.filename, raw_bytes, att.content_type, att.description))
            except Exception as e:
                logger.error(f"Failed to read attachment {att.filename}: {e}")

        # Sanitize mass mentions
        clean_content = message.content
        allowed_mentions = discord.AllowedMentions(roles=False, everyone=False, users=False)

        # Process reply headers
        reply_quote = ""
        if message.reference and message.reference.resolved:
            resolved_msg = message.reference.resolved
            if isinstance(resolved_msg, discord.Message):
                ref_author = resolved_msg.author.display_name
                ref_text = resolved_msg.content[:100].replace("\n", " ")
                reply_quote = f"> ↩️ Replying to **{ref_author}**: {ref_text}\n"

        full_message_text = f"{reply_quote}{clean_content}".strip()
        text_chunks = self._chunk_text(full_message_text) if full_message_text else [""]

        # Dispatch relay tasks
        tasks = []
        for item in targets_to_dispatch:
            tasks.append(self._dispatch_to_target(
                item["target_member"],
                text_chunks,
                cached_attachments,
                allowed_mentions
            ))

        await asyncio.gather(*tasks, return_exceptions=True)

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= DISCORD_MAX_TEXT_LEN:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 > DISCORD_MAX_TEXT_LEN:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                if len(line) > DISCORD_MAX_TEXT_LEN:
                    for i in range(0, len(line), DISCORD_MAX_TEXT_LEN):
                        chunks.append(line[i:i + DISCORD_MAX_TEXT_LEN])
                else:
                    current_chunk = line
            else:
                if current_chunk:
                    current_chunk += "\n" + line
                else:
                    current_chunk = line

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    async def _dispatch_to_target(self, target_member: dict,
                                  text_chunks: list[str], cached_attachments: list[tuple],
                                  allowed_mentions: discord.AllowedMentions):
        target_channel_id = int(target_member["channel_id"])
        group_id = target_member["group_id"]
        webhook_url = target_member.get("webhook_url")
        bot_identity_name = target_member.get("bot_name") or "Message Notifier"
        role_id = target_member.get("role_id")

        display_username = bot_identity_name
        # Only use custom avatar_url if explicitly set in config; otherwise omit avatar_url so Discord uses webhook's defined logo!
        custom_avatar_url = target_member.get("avatar_url")

        role_ping = f"<@&{role_id}> " if role_id else ""

        webhook = None
        if webhook_url:
            try:
                webhook = discord.Webhook.from_url(webhook_url, client=self.bot)
            except Exception as e:
                logger.warning(f"Invalid webhook URL for channel {target_channel_id}: {e}")

        # Re-create webhook if missing
        if not webhook:
            channel = self.bot.get_channel(target_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    webhook = await channel.create_webhook(name=bot_identity_name)
                    await self.db.update_member_config(
                        channel_id=target_channel_id,
                        group_id=group_id,
                        webhook_url=webhook.url
                    )
                    await self.reload_cache()
                except Exception as e:
                    logger.error(f"Failed to auto-create webhook for channel {target_channel_id}: {e}")

        # Send via webhook
        if webhook:
            for idx, chunk in enumerate(text_chunks):
                is_first = (idx == 0)
                chunk_text = f"{role_ping}{chunk}" if (is_first and role_ping) else chunk

                files_to_send = []
                if is_first:
                    for fname, raw_bytes, content_type, desc in cached_attachments:
                        files_to_send.append(discord.File(fp=io.BytesIO(raw_bytes), filename=fname, description=desc))

                send_kwargs = {
                    "content": chunk_text,
                    "username": display_username,
                    "files": files_to_send,
                    "allowed_mentions": allowed_mentions
                }
                if custom_avatar_url:
                    send_kwargs["avatar_url"] = custom_avatar_url

                try:
                    await webhook.send(**send_kwargs)
                except Exception as e:
                    logger.error(f"Error executing webhook for channel {target_channel_id}: {e}")
        else:
            # Fallback to direct channel send if webhooks unavailable
            channel = self.bot.get_channel(target_channel_id)
            if isinstance(channel, discord.TextChannel):
                for idx, chunk in enumerate(text_chunks):
                    is_first = (idx == 0)
                    chunk_text = f"**[{display_username}]** {role_ping}{chunk}" if (is_first and role_ping) else chunk
                    files_to_send = []
                    if is_first:
                        for fname, raw_bytes, content_type, desc in cached_attachments:
                            files_to_send.append(discord.File(fp=io.BytesIO(raw_bytes), filename=fname, description=desc))
                    try:
                        await channel.send(content=chunk_text, files=files_to_send, allowed_mentions=allowed_mentions)
                    except Exception as e:
                        logger.error(f"Fallback channel send error for {target_channel_id}: {e}")
