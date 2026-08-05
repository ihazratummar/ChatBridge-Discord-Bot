import logging
import asyncio
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from services.f2f_client import F2FClient
from services.template_engine import personalize_message

logger = logging.getLogger("ChatBridge.CampaignService")

def parse_f2f_datetime(dt_str: str) -> datetime | None:
    """Parses F2F ISO datetime string into UTC naive datetime."""
    if not dt_str:
        return None
    try:
        s = str(dt_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception as e:
        logger.warning(f"Error parsing F2F datetime '{dt_str}': {e}")
        return None


class CampaignService:
    def __init__(self, db_manager, f2f_client: F2FClient, event_callback=None):
        self.db = db_manager
        self.f2f_client = f2f_client
        self.event_callback = event_callback
        if self.f2f_client and not self.f2f_client.event_callback:
            self.f2f_client.event_callback = event_callback
        self.default_followup_gap_minutes = 60  # 60 minutes (1 hour) default
        self.default_followup_text = "Hey (name), subtle bump! Did you see my previous message? 😊"
        self.default_test_chat_ids = ["e85d76cb-ff3b-4f3d-a6ff-cfad7b1f6b57"]
        self.min_delay_seconds = 12.0  # Human pacing (12-20 sec delay between sends to prevent account flagging)
        self.max_delay_seconds = 20.0
        self._worker_task: asyncio.Task | None = None
        self._auto_rescan_task: asyncio.Task | None = None

    async def _notify_event(self, title: str, description: str, level: str = "info"):
        if self.event_callback:
            try:
                res = self.event_callback(title, description, level)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.warning(f"Error executing event_callback in CampaignService: {e}")

    async def get_test_chat_ids(self) -> list[str]:
        """Retrieves configured list of test target chat IDs from MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            doc = await self.db.db.settings.find_one({"_id": "test_chat_ids"})
            if doc and doc.get("chat_ids"):
                return doc.get("chat_ids")
        return self.default_test_chat_ids

    async def set_test_chat_ids(self, raw_input: str) -> list[str]:
        """Owner-only: Updates configured list of test target chat IDs in MongoDB."""
        items = [x.strip() for x in re.split(r'[\n,]+', raw_input) if x.strip()]
        valid_ids = list(dict.fromkeys(items))
        if not valid_ids:
            valid_ids = self.default_test_chat_ids

        if hasattr(self.db, "db") and self.db.db is not None:
            await self.db.db.settings.update_one(
                {"_id": "test_chat_ids"},
                {"$set": {"_id": "test_chat_ids", "chat_ids": valid_ids}},
                upsert=True
            )
            logger.info(f"Updated test chat IDs in MongoDB: {valid_ids}")
        return valid_ids

    def start_worker(self):
        """Starts background worker loops for periodic follow-up checking and auto-rescanning."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._followup_worker_loop())
            logger.info("Started Campaign Follow-up Background Worker Loop.")

        if self._auto_rescan_task is None or self._auto_rescan_task.done():
            self._auto_rescan_task = asyncio.create_task(self._auto_rescan_worker_loop())
            logger.info("Started Campaign Auto-Rescanning Background Worker Loop.")

    async def get_followup_gap(self) -> int:
        """Retrieves configured follow-up gap interval in minutes from MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            doc = await self.db.db.settings.find_one({"_id": "followup_gap"})
            if doc:
                return doc.get("minutes", self.default_followup_gap_minutes)
        return self.default_followup_gap_minutes

    async def set_followup_gap(self, minutes: int) -> bool:
        """Owner-only: Updates configured follow-up gap interval in minutes and recalculates all pending fan follow-up timers mid-campaign!"""
        new_gap = max(1, minutes)
        self.default_followup_gap_minutes = new_gap
        if hasattr(self.db, "db") and self.db.db is not None:
            # 1. Update global settings collection
            await self.db.db.settings.update_one(
                {"_id": "followup_gap"},
                {"$set": {"_id": "followup_gap", "minutes": new_gap}},
                upsert=True
            )

            # 2. Update active campaign_runs documents
            await self.db.db.campaign_runs.update_many(
                {"status": "active"},
                {"$set": {"followup_gap_minutes": new_gap}}
            )

            # Recalculate followup_due_at for all active pending fan states mid-campaign!
            cursor = self.db.db.campaign_user_states.find({"status": "initial_sent"})
            pending_states = await cursor.to_list(length=None)
            recalculated_count = 0
            for doc in pending_states:
                init_at = doc.get("initial_sent_at")
                if init_at and isinstance(init_at, datetime):
                    new_due_at = init_at + timedelta(minutes=new_gap)
                    await self.db.db.campaign_user_states.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"followup_due_at": new_due_at}}
                    )
                    recalculated_count += 1

            logger.info(f"Updated follow-up gap interval to {new_gap} minutes in MongoDB (Recalculated {recalculated_count} pending fan timers).")
            return True
        return True

    async def get_followup_text(self) -> str:
        """Retrieves configured follow-up message template from MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            doc = await self.db.db.settings.find_one({"_id": "followup_text"})
            if doc and doc.get("text"):
                return doc.get("text")
        return self.default_followup_text

    async def set_followup_text(self, text: str) -> bool:
        """Owner-only: Updates configured follow-up message template in MongoDB."""
        clean_text = text.strip()
        if hasattr(self.db, "db") and self.db.db is not None:
            await self.db.db.settings.update_one(
                {"_id": "followup_text"},
                {"$set": {"_id": "followup_text", "text": clean_text}},
                upsert=True
            )
            logger.info(f"Updated follow-up message template in MongoDB: '{clean_text}'")
            return True
        return True

    async def get_active_campaigns(self) -> list[dict]:
        """Retrieves active creator outreach campaigns from MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            cursor = self.db.db.campaign_runs.find({"status": "active"}).sort("created_at", -1)
            raw_campaigns = await cursor.to_list(length=50)

            active_campaigns = []
            for cmp in raw_campaigns:
                cmp_id = cmp["_id"]
                pending_count = await self.db.db.campaign_user_states.count_documents({
                    "campaign_id": cmp_id,
                    "status": "initial_sent"
                })
                cmp["pending_users_count"] = pending_count
                active_campaigns.append(cmp)

            return active_campaigns
        return []

    async def cancel_campaign(self, cmp_id: str) -> bool:
        """Cancels a specific active campaign in MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            res = await self.db.db.campaign_runs.update_one(
                {"_id": cmp_id, "status": "active"},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
            )
            await self.db.db.campaign_user_states.update_many(
                {"campaign_id": cmp_id, "status": "initial_sent"},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
            )
            return res.modified_count > 0
        return False

    async def cancel_all_campaigns(self) -> int:
        """Cancels all active campaigns in MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            res = await self.db.db.campaign_runs.update_many(
                {"status": "active"},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
            )
            await self.db.db.campaign_user_states.update_many(
                {"status": "initial_sent"},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
            )
            await self._notify_event(
                "All Outreach Campaigns Cancelled",
                f"• Action: Cancelled **{res.modified_count}** active campaign loop(s) across all creator models.",
                level="warning"
            )
            return res.modified_count
        return 0

    async def cancel_creator_campaigns(self, creator: str) -> int:
        """Cancels all active campaigns in MongoDB specifically for a creator model."""
        target_creator = re.sub(r'[^\x00-\x7F]+', '', creator).lower().replace("#", "").strip()
        if hasattr(self.db, "db") and self.db.db is not None:
            res = await self.db.db.campaign_runs.update_many(
                {"creator": target_creator, "status": "active"},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
            )
            await self.db.db.campaign_user_states.update_many(
                {"creator": target_creator, "status": "initial_sent"},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
            )
            logger.info(f"🛑 Cancelled all active campaigns in MongoDB Atlas for creator @{target_creator}.")
            await self._notify_event(
                "Creator Outreach Stopped",
                f"• Creator: **@{target_creator}**\n• Status: All active campaign loops stopped in Cloud MongoDB Atlas.",
                level="warning"
            )
            return res.modified_count
        return 0

    async def start_auto_rescan(self, creator: str, raw_message: str) -> str:
        """
        Starts or updates a continuous auto-rescanning campaign for a creator model.
        If an active campaign already exists for creator, updates its prompt raw_message.
        """
        self.start_worker()
        target_creator = re.sub(r'[^\x00-\x7F]+', '', creator).lower().replace("#", "").strip()
        gap_min = await self.get_followup_gap()
        configured_followup = await self.get_followup_text()

        if hasattr(self.db, "db") and self.db.db is not None:
            existing = await self.db.db.campaign_runs.find_one({"creator": target_creator, "status": "active"})
            if existing:
                cmp_id = existing["_id"]
                await self.db.db.campaign_runs.update_one(
                    {"_id": cmp_id},
                    {"$set": {
                        "raw_message": raw_message,
                        "updated_at": datetime.utcnow()
                    }}
                )
                logger.info(f"🔄 Updated active campaign prompt template for creator @{target_creator} (ID: {cmp_id}).")
                await self._notify_event(
                    "Campaign Prompt Template Updated",
                    f"• Creator: **@{target_creator}**\n• Campaign ID: `{cmp_id}`\n• New Template Message:\n> *\"{raw_message[:150]}\"*",
                    level="info"
                )
                return cmp_id
            else:
                cmp_id = f"cmp_{int(datetime.utcnow().timestamp())}_{target_creator}"
                doc = {
                    "_id": cmp_id,
                    "creator": target_creator,
                    "raw_message": raw_message,
                    "followup_text": configured_followup,
                    "status": "active",
                    "followup_gap_minutes": gap_min,
                    "created_at": datetime.utcnow()
                }
                await self.db.db.campaign_runs.insert_one(doc)
                logger.info(f"🚀 Started continuous auto-rescanning campaign {cmp_id} for creator @{target_creator}.")
                await self._notify_event(
                    "Continuous Outreach Loop Started",
                    f"• Creator: **@{target_creator}**\n• Campaign ID: `{cmp_id}`\n• Initial Template:\n> *\"{raw_message[:150]}\"*\n• Polling: **Every 15s** with 4h cooldown.",
                    level="success"
                )
                return cmp_id
        return ""

    async def has_user_replied(self, chat_id: str, creator: str, initial_sent_at: datetime | None = None) -> bool:
        """
        Checks message history to see if target fan has replied.
        Uses F2F 'received' boolean field (received=True means sent by fan).
        Converts all timestamps to UTC to accurately compare against initial_sent_at!
        """
        messages = await self.f2f_client.get_chat_messages(chat_id, creator)
        if not messages or not isinstance(messages, list):
            return False

        for m in messages:
            if not isinstance(m, dict):
                continue

            # F2F API: 'received': True indicates an incoming message from the fan
            is_fan_msg = (
                m.get("received") is True or
                m.get("is_from_user") is True or
                m.get("sender_type") == "user"
            )

            if is_fan_msg:
                msg_date_str = m.get("datetime") or m.get("created_at") or m.get("created")
                if initial_sent_at and msg_date_str:
                    msg_dt = parse_f2f_datetime(msg_date_str)
                    if msg_dt and msg_dt >= initial_sent_at:
                        logger.info(f"🛑 Fan replied at {msg_dt} UTC (after initial sent at {initial_sent_at} UTC)!")
                        return True
                elif not initial_sent_at:
                    logger.info(f"🛑 Detected fan reply message in chat {chat_id} (content: '{m.get('content')}')!")
                    return True

        return False

    async def has_user_seen_message(self, chat_id: str, creator: str, initial_sent_at: datetime | None = None) -> bool:
        """
        Checks F2F message history to see if the target fan has SEEN/READ the initial message.
        Returns True if ANY outgoing initial message sent at/after initial_sent_at has read: true on F2F.
        Includes a 5-second clock skew leeway for server clock differences.
        """
        messages = await self.f2f_client.get_chat_messages(chat_id, creator)
        if not messages or not isinstance(messages, list):
            return False

        # Allow 5 second clock skew leeway between F2F API server and local/VPS clock
        leeway_sent_at = (initial_sent_at - timedelta(seconds=5)) if initial_sent_at else None

        for m in messages:
            if not isinstance(m, dict):
                continue

            is_outgoing = (
                m.get("received") is False or
                m.get("is_from_user") is False or
                bool(m.get("sent_by_agent")) or
                m.get("sender_type") in ("agent", "creator", "system")
            )
            if is_outgoing:
                msg_date_str = m.get("datetime") or m.get("created_at") or m.get("created")
                msg_dt = parse_f2f_datetime(msg_date_str) if msg_date_str else None

                if leeway_sent_at and msg_dt and msg_dt >= leeway_sent_at:
                    is_read = m.get("read") is True or m.get("is_read") is True or m.get("seen") is True
                    if is_read:
                        logger.info(f"👁️ Fan '{chat_id}' has SEEN initial message (sent at {msg_dt} UTC).")
                        return True
                elif not leeway_sent_at and (m.get("read") is True or m.get("is_read") is True or m.get("seen") is True):
                    return True

        return False

    async def is_fan_in_cooldown(self, chat_id: str, creator: str, cooldown_hours: int = 4, chat_obj: dict | None = None) -> bool:
        """
        Checks if fan has received any outgoing message (from bot or human chatter) within cooldown_hours (default 4h).
        Checks both MongoDB campaign records and live F2F chat's recent outgoing message timestamp!
        """
        cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)

        # 1. Check MongoDB Atlas Campaign States
        if hasattr(self.db, "db") and self.db.db is not None:
            doc = await self.db.db.campaign_user_states.find_one({
                "chat_id": chat_id,
                "creator": creator,
                "initial_sent_at": {"$gte": cutoff}
            })
            if doc:
                logger.info(f"🛡️ Fan '{chat_id}' is in {cooldown_hours}h cooldown based on MongoDB record (sent at {doc.get('initial_sent_at')}).")
                return True

        # 2. Check Live F2F Chat's Last Outgoing Message Timestamp (Supports human chatter sends)
        target_chat = chat_obj
        if not target_chat:
            target_chat = await self.f2f_client.get_chat_details(chat_id, creator)

        if target_chat and isinstance(target_chat, dict):
            last_msg = target_chat.get("message")
            if last_msg and isinstance(last_msg, dict):
                is_outgoing = (
                    last_msg.get("received") is False or
                    last_msg.get("is_from_user") is False or
                    last_msg.get("sender_type") in ("agent", "creator", "system")
                )
                if is_outgoing:
                    dt_str = last_msg.get("datetime") or last_msg.get("created_at") or last_msg.get("created")
                    msg_dt = parse_f2f_datetime(dt_str)
                    if msg_dt and msg_dt >= cutoff:
                        logger.info(f"🛡️ Fan '{chat_id}' is in {cooldown_hours}h cooldown based on live F2F message sent at {msg_dt} UTC.")
                        return True

        return False

    async def create_campaign_record(self, creator: str, raw_message: str, followup_text: str | None = None) -> str:
        """Creates a new campaign record in MongoDB."""
        gap_min = await self.get_followup_gap()
        configured_followup = followup_text or await self.get_followup_text()
        cmp_id = f"cmp_{int(datetime.utcnow().timestamp())}_{creator}"
        followup_scheduled_at = datetime.utcnow() + timedelta(minutes=gap_min)

        doc = {
            "_id": cmp_id,
            "creator": creator,
            "raw_message": raw_message,
            "followup_text": configured_followup,
            "status": "active",
            "followup_gap_minutes": gap_min,
            "created_at": datetime.utcnow(),
            "followup_scheduled_at": followup_scheduled_at
        }

        if hasattr(self.db, "db") and self.db.db is not None:
            await self.db.db.campaign_runs.insert_one(doc)

        logger.info(f"Created Campaign {cmp_id}: Follow-up scheduled in {gap_min} minute(s) at {followup_scheduled_at.strftime('%H:%M:%S')} UTC.")
        return cmp_id

    async def execute_outreach_campaign(self, creator: str, raw_message: str,
                                         test_chat_id: str | None = None,
                                         enforce_cooldown: bool = False) -> dict:
        """
        Executes campaign outreach strictly on behalf of the creator corresponding to the active Discord channel.
        """
        target_creator = re.sub(r'[^\x00-\x7F]+', '', creator).lower().replace("#", "").strip()
        logger.info(f"Starting outreach campaign strictly for creator @{target_creator} (Test Chat ID: {test_chat_id or 'NONE'})")

        if test_chat_id:
            # Strictly use target_creator for the active Discord channel
            details = await self.f2f_client.get_chat_details(test_chat_id, target_creator)
            fan_name = "Fan"
            if details and isinstance(details, dict):
                fan_name = details.get("title") or details.get("other_user", {}).get("username") or "Fan"

            if enforce_cooldown and await self.is_fan_in_cooldown(test_chat_id, target_creator):
                logger.info(f"Test Cooldown Blocked: Fan '{fan_name}' ({test_chat_id}) is in 24h cooldown!")
                return {
                    "status": "cooldown_blocked",
                    "reason": f"Fan '{fan_name}' is currently in 24-hour cooldown! Initial message skipped.",
                    "target_fan_name": fan_name
                }

            personalized_text = personalize_message(raw_message, user_name=fan_name)
            logger.info(f"Personalized Test Message for creator @{target_creator} to fan '{fan_name}': '{personalized_text}'")

            res = await self.f2f_client.send_message(test_chat_id, target_creator, personalized_text)
            if res and isinstance(res, dict) and not res.get("error"):
                test_cmp_id = f"test_{int(datetime.utcnow().timestamp())}_{target_creator}"
                gap_min = await self.get_followup_gap()
                now_sent = datetime.utcnow()
                followup_due_at = now_sent + timedelta(minutes=gap_min)

                if hasattr(self.db, "db") and self.db.db is not None:
                    await self.db.db.campaign_user_states.update_one(
                        {"_id": f"{test_cmp_id}_{test_chat_id}"},
                        {"$set": {
                            "campaign_id": test_cmp_id,
                            "creator": target_creator,
                            "chat_id": test_chat_id,
                            "fan_name": fan_name,
                            "status": "initial_sent",
                            "initial_sent_at": now_sent,
                            "followup_due_at": followup_due_at
                        }},
                        upsert=True
                    )
                return {
                    "status": "success",
                    "mode": "test",
                    "sent_count": 1,
                    "target_chat_id": test_chat_id,
                    "target_fan_name": fan_name,
                    "personalized_text": personalized_text,
                    "target_creator": target_creator,
                    "campaign_id": test_cmp_id
                }
            else:
                err_msg = res.get("reason") if isinstance(res, dict) else f"Failed to send message to chat {test_chat_id} via F2F API."
                return {
                    "status": "error",
                    "mode": "test",
                    "sent_count": 0,
                    "target_chat_id": test_chat_id,
                    "target_fan_name": fan_name,
                    "target_creator": target_creator,
                    "reason": err_msg
                }

        # Full Production Online Fan Outreach Mode (Specific to creator channel)
        cmp_id = await self.create_campaign_record(target_creator, raw_message)
        online_chats = await self.f2f_client.get_online_chats(target_creator)
        if not online_chats:
            logger.info(f"No online chats found for creator @{target_creator}.")
            if hasattr(self.db, "db") and self.db.db is not None:
                await self.db.db.campaign_runs.update_one(
                    {"_id": cmp_id},
                    {"$set": {"status": "completed", "completed_at": datetime.utcnow()}}
                )
            return {"status": "success", "mode": "production", "sent_count": 0, "skipped_replied": 0, "campaign_id": cmp_id}

        sent_count = 0
        skipped_replied = 0
        gap_min = await self.get_followup_gap()

        for chat in online_chats:
            if not isinstance(chat, dict):
                continue

            chat_id = chat.get("uuid") or chat.get("id")
            if not chat_id:
                continue

            user_obj = chat.get("user") if isinstance(chat.get("user"), dict) else {}
            other_obj = chat.get("other_user") if isinstance(chat.get("other_user"), dict) else {}

            fan_name = (
                chat.get("title") or
                user_obj.get("name") or
                user_obj.get("username") or
                other_obj.get("username") or
                other_obj.get("name") or
                chat.get("username") or
                "Fan"
            )

            try:
                # 4-Hour Active Cooldown Check (Prevents sending duplicate initial messages when new campaign is triggered)
                if await self.is_fan_in_cooldown(chat_id, target_creator, chat_obj=chat):
                    logger.info(f"Skipping fan '{fan_name}' ({chat_id}): Fan already messaged within 4h cooldown!")
                    skipped_replied += 1
                    continue

                if await self.has_user_replied(chat_id, target_creator):
                    logger.info(f"Skipping fan '{fan_name}' ({chat_id}): Fan has already replied!")
                    skipped_replied += 1
                    continue

                personalized_text = personalize_message(raw_message, user_name=fan_name)
                send_res = await self.f2f_client.send_message(chat_id, target_creator, personalized_text)

                if send_res and isinstance(send_res, dict) and not send_res.get("error"):
                    sent_count += 1
                    now_sent = datetime.utcnow()
                    followup_due_at = now_sent + timedelta(minutes=gap_min)
                    if hasattr(self.db, "db") and self.db.db is not None:
                        doc_id = f"{cmp_id}_{chat_id}"
                        await self.db.db.campaign_user_states.update_one(
                            {"_id": doc_id},
                            {"$set": {
                                "campaign_id": cmp_id,
                                "creator": target_creator,
                                "chat_id": chat_id,
                                "fan_name": fan_name,
                                "status": "initial_sent",
                                "initial_sent_at": now_sent,
                                "followup_due_at": followup_due_at
                            }},
                            upsert=True
                        )
                        logger.info(f"💾 Saved fan campaign state to MongoDB Atlas ({doc_id}) for fan '{fan_name}'.")

            except Exception as e:
                logger.error(f"Error dispatching outreach to fan '{fan_name}' ({chat_id}): {e}", exc_info=True)

            delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
            logger.info(f"Waiting {delay:.1f}s before next dispatch...")
            await asyncio.sleep(delay)

        if sent_count == 0 and hasattr(self.db, "db") and self.db.db is not None:
            await self.db.db.campaign_runs.update_one(
                {"_id": cmp_id},
                {"$set": {"status": "completed", "completed_at": datetime.utcnow()}}
            )

        return {
            "status": "success",
            "mode": "production",
            "sent_count": sent_count,
            "skipped_replied": skipped_replied,
            "campaign_id": cmp_id
        }

    async def execute_test_followup(self, creator: str, test_chat_id: str, followup_text: str | None = None) -> dict:
        """Instantly tests sending a follow-up message strictly on behalf of the active channel creator."""
        target_creator = re.sub(r'[^\x00-\x7F]+', '', creator).lower().replace("#", "").strip()

        details = await self.f2f_client.get_chat_details(test_chat_id, target_creator)
        fan_name = "Fan"
        if details and isinstance(details, dict):
            fan_name = details.get("title") or details.get("other_user", {}).get("username") or "Fan"

        if await self.has_user_replied(test_chat_id, target_creator):
            logger.info(f"Test Follow-up Skipped for {fan_name}: Fan has replied!")
            if hasattr(self.db, "db") and self.db.db is not None:
                await self.db.db.campaign_user_states.update_one(
                    {"_id": f"test_{target_creator}_{test_chat_id}"},
                    {"$set": {"status": "replied_stop", "completed_at": datetime.utcnow()}}
                )
            return {"status": "stopped", "reason": f"Fan '{fan_name}' has replied! Follow-up stopped."}

        configured_template = followup_text or await self.get_followup_text()
        personalized_text = personalize_message(configured_template, user_name=fan_name)

        send_res = await self.f2f_client.send_message(test_chat_id, target_creator, personalized_text)
        if send_res and isinstance(send_res, dict) and not send_res.get("error"):
            if hasattr(self.db, "db") and self.db.db is not None:
                await self.db.db.campaign_user_states.update_one(
                    {"_id": f"test_{target_creator}_{test_chat_id}"},
                    {"$set": {"status": "completed", "followup_sent_at": datetime.utcnow()}}
                )
            return {
                "status": "success",
                "sent_text": personalized_text,
                "fan_name": fan_name,
                "target_creator": target_creator
            }
        else:
            err_msg = send_res.get("reason") if isinstance(send_res, dict) else f"Failed to send follow-up message to chat {test_chat_id} via F2F API."
            return {"status": "error", "reason": err_msg}

    async def _process_single_creator_campaign(self, cmp: dict):
        """Processes an active outreach campaign for a single creator model concurrently in parallel."""
        cmp_id = cmp["_id"]
        creator = cmp["creator"]
        raw_message = cmp.get("raw_message", "")
        if not raw_message:
            return

        online_chats = await self.f2f_client.get_online_chats(creator)
        if not online_chats:
            return

        gap_min = await self.get_followup_gap()

        for chat in online_chats:
            if not isinstance(chat, dict):
                continue
            chat_id = chat.get("uuid") or chat.get("id")
            if not chat_id:
                continue

            user_obj = chat.get("user") if isinstance(chat.get("user"), dict) else {}
            other_obj = chat.get("other_user") if isinstance(chat.get("other_user"), dict) else {}
            fan_name = (
                chat.get("title") or
                user_obj.get("name") or
                user_obj.get("username") or
                other_obj.get("username") or
                other_obj.get("name") or
                chat.get("username") or
                "Fan"
            )

            try:
                # 1. 4-Hour Cooldown Check (Checks DB and live F2F message timestamp)
                if await self.is_fan_in_cooldown(chat_id, creator, chat_obj=chat):
                    continue

                # 2. Live Reply Safety Check
                if await self.has_user_replied(chat_id, creator):
                    continue

                # 3. Personalize and Send Initial Message
                personalized_text = personalize_message(raw_message, user_name=fan_name)
                send_res = await self.f2f_client.send_message(chat_id, creator, personalized_text)

                if send_res and isinstance(send_res, dict) and not send_res.get("error"):
                    now_sent = datetime.utcnow()
                    followup_due_at = now_sent + timedelta(minutes=gap_min)
                    doc_id = f"{cmp_id}_{chat_id}"
                    await self.db.db.campaign_user_states.update_one(
                        {"_id": doc_id},
                        {"$set": {
                            "campaign_id": cmp_id,
                            "creator": creator,
                            "chat_id": chat_id,
                            "fan_name": fan_name,
                            "status": "initial_sent",
                            "initial_sent_at": now_sent,
                            "followup_due_at": followup_due_at
                        }},
                        upsert=True
                    )
                    logger.info(f"✨ Auto-Rescan: Sent & Saved initial message state to MongoDB Atlas ({doc_id}) for fan '{fan_name}' (@{creator}).")

                    delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Error in auto-rescan dispatch for fan '{fan_name}' ({chat_id}): {e}")

    async def _auto_rescan_worker_loop(self):
        """Background worker loop polling active creator campaigns every 15 seconds to dispatch to newly online fans in parallel."""
        while True:
            try:
                await asyncio.sleep(15)
                if not hasattr(self.db, "db") or self.db.db is None:
                    continue

                cursor = self.db.db.campaign_runs.find({"status": "active"})
                active_campaigns = await cursor.to_list(length=None)
                if active_campaigns:
                    tasks = [self._process_single_creator_campaign(cmp) for cmp in active_campaigns]
                    await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto rescan worker loop: {e}", exc_info=True)

    async def _followup_worker_loop(self):
        """Background worker loop checking every 15 seconds for individual fan follow-up timers due."""
        while True:
            try:
                await asyncio.sleep(15)
                if not hasattr(self.db, "db") or self.db.db is None:
                    continue

                now = datetime.utcnow()
                # Query per-fan user states directly where their unique followup_due_at timer has arrived
                cursor = self.db.db.campaign_user_states.find({
                    "status": "initial_sent",
                    "followup_due_at": {"$lte": now}
                })
                due_user_states = await cursor.to_list(length=None)

                for user_state in due_user_states:
                    chat_id = user_state["chat_id"]
                    creator = user_state["creator"]
                    fan_name = user_state.get("fan_name", "Fan")
                    initial_sent = user_state.get("initial_sent_at")
                    campaign_id = user_state.get("campaign_id", "")

                    # 1. Parent Campaign Active Status Check (Skip if campaign was cancelled or completed)
                    cmp_doc = await self.db.db.campaign_runs.find_one({"_id": campaign_id})
                    if campaign_id.startswith("test_") or not cmp_doc or cmp_doc.get("status") in ("cancelled", "completed"):
                        logger.info(f"🛑 Skipping follow-up check for fan '{fan_name}' ({chat_id}): Campaign '{campaign_id}' is no longer active.")
                        await self.db.db.campaign_user_states.update_one(
                            {"_id": user_state["_id"]},
                            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
                        )
                        continue

                    # 2. Live Reply Safety Check (Stop User)
                    if await self.has_user_replied(chat_id, creator, initial_sent_at=initial_sent):
                        logger.info(f"🛑 Follow-up SKIPPED for fan '{fan_name}' ({chat_id}): Fan has replied!")
                        await self.db.db.campaign_user_states.update_one(
                            {"_id": user_state["_id"]},
                            {"$set": {"status": "replied_stop", "completed_at": datetime.utcnow()}}
                        )
                        continue

                    # 3. Live Seen/Read Safety Check (Only send follow-up if fan HAS SEEN the initial message!)
                    if not await self.has_user_seen_message(chat_id, creator, initial_sent_at=initial_sent):
                        logger.info(f"⏳ Follow-up SKIPPED for fan '{fan_name}' ({chat_id}): Fan has NOT seen/read the message yet.")
                        continue

                    configured_template = (cmp_doc.get("followup_text") if cmp_doc else None) or await self.get_followup_text()

                    # Send Follow-up Message with Name Personalization
                    personalized_followup = personalize_message(configured_template, user_name=fan_name)
                    logger.info(f"📨 Sending Follow-up on behalf of @{creator} to '{fan_name}' ({chat_id}): '{personalized_followup}'")
                    res = await self.f2f_client.send_message(chat_id, creator, personalized_followup)

                    if res:
                        await self.db.db.campaign_user_states.update_one(
                            {"_id": user_state["_id"]},
                            {"$set": {"status": "followup_sent", "followup_sent_at": datetime.utcnow()}}
                        )

                    # Check if all user follow-ups for this campaign have finished (0 pending remaining)
                    cmp_id = user_state.get("campaign_id")
                    if cmp_id:
                        rem_pending = await self.db.db.campaign_user_states.count_documents({
                            "campaign_id": cmp_id,
                            "status": "initial_sent"
                        })
                        if rem_pending == 0:
                            await self.db.db.campaign_runs.update_one(
                                {"_id": cmp_id},
                                {"$set": {"status": "completed", "completed_at": datetime.utcnow()}}
                            )
                            logger.info(f"🎉 All user follow-ups finished! Auto-closed campaign {cmp_id}.")

                    delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
                    await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in followup worker loop: {e}", exc_info=True)
