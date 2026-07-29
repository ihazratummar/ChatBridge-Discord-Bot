import logging
import asyncio
import discord
from database import DatabaseManager

logger = logging.getLogger("ChatBridge.BridgeService")

class BridgeService:
    def __init__(self, bot: discord.Client, db: DatabaseManager):
        self.bot = bot
        self.db = db
        # Fast in-memory cache mapping: channel_id -> route dict
        self._channel_cache: dict[int, dict] = {}
        # In-memory webhook objects cache: bridge_id_direction -> discord.Webhook
        self._webhook_cache: dict[str, discord.Webhook] = {}

    async def reload_cache(self):
        """Loads all bridges from DB into fast in-memory cache for O(1) message lookups."""
        try:
            bridges = await self.db.get_all_bridges()
            new_cache = {}

            for b in bridges:
                b_id = b["id"]
                ch_a = b["channel_a_id"]
                ch_b = b["channel_b_id"]

                # Direction A -> B (Message sent in A, posted into B)
                new_cache[ch_a] = {
                    "bridge_id": b_id,
                    "source_channel_id": ch_a,
                    "target_channel_id": ch_b,
                    "direction": "a_to_b",
                    "config": b["direction_a_to_b"]
                }

                # Direction B -> A (Message sent in B, posted into A)
                new_cache[ch_b] = {
                    "bridge_id": b_id,
                    "source_channel_id": ch_b,
                    "target_channel_id": ch_a,
                    "direction": "b_to_a",
                    "config": b["direction_b_to_a"]
                }

            self._channel_cache = new_cache
            self._webhook_cache.clear()
            logger.info(f"Bridge cache loaded: {len(bridges)} pairs ({len(self._channel_cache)} channels).")
        except Exception as e:
            logger.error(f"Failed to reload bridge cache: {e}", exc_info=True)

    def get_route(self, channel_id: int) -> dict | None:
        return self._channel_cache.get(channel_id)

    async def setup_bridge(self, channel_a_id: int, channel_b_id: int,
                           name_a_to_b: str, name_b_to_a: str) -> dict:
        bridge_data = await self.db.add_or_update_bridge(channel_a_id, channel_b_id, name_a_to_b, name_b_to_a)
        await self.reload_cache()
        return bridge_data

    async def remove_bridge(self, channel_id: int) -> bool:
        removed = await self.db.remove_bridge_by_channel(channel_id)
        if removed:
            await self.reload_cache()
        return removed

    async def update_bot_name(self, target_channel_id: int, name: str) -> bool:
        route = self.get_route(target_channel_id)
        if not route:
            return False
        b_id = route["bridge_id"]
        dir_originating = route["direction"]
        target_dir = "b_to_a" if dir_originating == "a_to_b" else "a_to_b"

        await self.db.update_bot_name(b_id, target_dir, name)
        await self.reload_cache()
        return True

    async def update_role_ping(self, target_channel_id: int, role_id: str | None) -> bool:
        route = self.get_route(target_channel_id)
        if not route:
            return False
        b_id = route["bridge_id"]
        dir_originating = route["direction"]
        target_dir = "b_to_a" if dir_originating == "a_to_b" else "a_to_b"

        await self.db.update_role_ping(b_id, target_dir, role_id)
        await self.reload_cache()
        return True

    async def handle_incoming_message(self, message: discord.Message):
        # 1. Strict Loop Prevention: ignore messages from any bot or webhook
        if message.author.bot or message.webhook_id is not None:
            return

        # 2. Fast O(1) lookup
        route = self.get_route(message.channel.id)
        if not route:
            return

        target_ch_id = route["target_channel_id"]
        cfg = route["config"]
        b_id = route["bridge_id"]
        direction = route["direction"]

        # Target direction key for webhook config
        target_dir_key = "a_to_b" if direction == "a_to_b" else "b_to_a"

        # 3. Resolve Target Channel
        target_channel = self.bot.get_channel(target_ch_id)
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(target_ch_id)
            except (discord.NotFound, discord.Forbidden) as e:
                logger.warning(f"Target channel {target_ch_id} inaccessible: {e}")
                return
            except Exception as e:
                logger.error(f"Error fetching channel {target_ch_id}: {e}")
                return

        # 4. Prepare message content & reply context
        content_parts = []

        # If message is a reply, add context header
        if message.reference and message.reference.resolved:
            ref_msg = message.reference.resolved
            if isinstance(ref_msg, discord.Message):
                author_name = ref_msg.author.display_name if not ref_msg.author.bot else "Relayed Message"
                ref_preview = ref_msg.content[:50] + "..." if len(ref_msg.content) > 50 else ref_msg.content
                content_parts.append(f"> ↩️ *Replying to {author_name}:* \"{ref_preview}\"")

        main_content = message.content or ""
        role_id = cfg.get("role_id")

        # 5. Safe Allowed Mentions (Prevent unauthorized mass pings)
        allow_roles = False
        allow_everyone = False
        role_ping_str = ""

        if role_id:
            if role_id == "everyone":
                role_ping_str = "@everyone "
                allow_everyone = True
            else:
                role_ping_str = f"<@&{role_id}> "
                allow_roles = True

        if role_ping_str:
            content_parts.append(f"{role_ping_str}{main_content}".strip())
        elif main_content:
            content_parts.append(main_content)

        final_content = "\n".join(content_parts).strip()

        # 6. Process attachments with timeout & error safety
        files = []
        attachment_warnings = []
        for att in message.attachments:
            try:
                # 10 second timeout per attachment download
                file_obj = await asyncio.wait_for(att.to_file(), timeout=10.0)
                files.append(file_obj)
            except asyncio.TimeoutError:
                attachment_warnings.append(f"⚠️ *Attachment `{att.filename}` timed out downloading.*")
                logger.warning(f"Attachment {att.filename} timed out.")
            except Exception as e:
                attachment_warnings.append(f"⚠️ *Attachment `{att.filename}` failed to transfer.*")
                logger.error(f"Error transferring attachment {att.filename}: {e}")

        if attachment_warnings:
            final_content = (final_content + "\n" + "\n".join(attachment_warnings)).strip()

        # 7. Dynamic Webhook Resolution & Error Recovery
        webhook = await self._get_or_create_webhook(target_channel, b_id, target_dir_key, cfg.get("webhook_url"))

        bot_name = cfg.get("bot_name", "ChatBridge Bot")
        avatar_url = cfg.get("avatar_url")

        # Restrict allowed mentions to prevent user text from triggering unauthorized role/everyone pings
        allowed_mentions = discord.AllowedMentions(
            roles=allow_roles,
            everyone=allow_everyone,
            users=False
        )

        content_chunks = self._chunk_text(final_content, 2000) if final_content else [""]

        # Send via Webhook with fallback to Direct Channel Send
        sent_success = False
        if webhook:
            try:
                for idx, chunk in enumerate(content_chunks):
                    chunk_files = files if idx == 0 else []
                    chunk_embeds = message.embeds if idx == 0 else []

                    if not chunk and not chunk_files and not chunk_embeds:
                        continue

                    await webhook.send(
                        content=chunk if chunk else None,
                        username=bot_name,
                        avatar_url=avatar_url,
                        embeds=chunk_embeds,
                        files=chunk_files,
                        allowed_mentions=allowed_mentions
                    )
                sent_success = True
            except discord.NotFound:
                logger.warning(f"Webhook for channel {target_ch_id} not found on Discord. Invalidating cache and retrying...")
                await self.db.update_webhook(b_id, target_dir_key, None)
                cache_key = f"{b_id}_{target_dir_key}"
                self._webhook_cache.pop(cache_key, None)
                # Re-fetch/create webhook
                webhook = await self._get_or_create_webhook(target_channel, b_id, target_dir_key, None)
            except discord.HTTPException as e:
                logger.error(f"HTTP exception sending via webhook: {e}")

        if not sent_success:
            # Fallback direct channel message
            try:
                for idx, chunk in enumerate(content_chunks):
                    chunk_files = files if idx == 0 else []
                    chunk_embeds = message.embeds if idx == 0 else []
                    header = f"**[{bot_name}]** " if idx == 0 else ""

                    await target_channel.send(
                        content=f"{header}{chunk}".strip(),
                        embeds=chunk_embeds,
                        files=chunk_files,
                        allowed_mentions=allowed_mentions
                    )
            except Exception as e:
                logger.error(f"Fallback send failed to channel {target_ch_id}: {e}")

    async def _get_or_create_webhook(self, target_channel: discord.TextChannel, bridge_id: int, direction: str, cached_url: str | None) -> discord.Webhook | None:
        cache_key = f"{bridge_id}_{direction}"

        # 1. Check in-memory webhook object cache
        if cache_key in self._webhook_cache:
            return self._webhook_cache[cache_key]

        # 2. Check cached URL from DB
        if cached_url:
            try:
                wh = discord.Webhook.from_url(cached_url, client=self.bot)
                self._webhook_cache[cache_key] = wh
                return wh
            except Exception:
                pass

        # 3. Create or find webhook in channel
        try:
            webhooks = await target_channel.webhooks()
            for wh in webhooks:
                if wh.name == "ChatBridge Webhook" or wh.user == self.bot.user:
                    await self.db.update_webhook(bridge_id, direction, wh.url)
                    self._webhook_cache[cache_key] = wh
                    return wh

            wh = await target_channel.create_webhook(name="ChatBridge Webhook")
            await self.db.update_webhook(bridge_id, direction, wh.url)
            self._webhook_cache[cache_key] = wh
            return wh
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Webhook permission missing in {target_channel.id}: {e}")
            return None

    @staticmethod
    def _chunk_text(text: str, limit: int = 2000) -> list[str]:
        """Bulletproof text chunker ensuring safe splitting under 2000 chars without infinite loops."""
        if not text:
            return []
        if len(text) <= limit:
            return [text]

        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break

            # Find optimal space split point
            split_at = text.rfind(" ", 0, limit)
            if split_at <= 0:  # No space found or at start
                split_at = limit

            chunk = text[:split_at].strip()
            if chunk:
                chunks.append(chunk)
            text = text[split_at:].lstrip()

        return chunks
