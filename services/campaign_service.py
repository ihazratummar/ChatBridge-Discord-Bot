import logging
import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Dict, Any

from services.f2f_client import F2FClient
from services.template_engine import personalize_message

logger = logging.getLogger("ChatBridge.CampaignService")

class CampaignService:
    def __init__(self, db_manager, f2f_client: F2FClient):
        self.db = db_manager
        self.f2f_client = f2f_client
        self.default_followup_gap_minutes = 60  # 60 minutes (1 hour) default
        self.default_followup_text = "Hey (name), subtle bump! Did you see my previous message? 😊"
        self.min_delay_seconds = 2
        self.max_delay_seconds = 5
        self._worker_task: asyncio.Task | None = None

    def start_worker(self):
        """Starts background worker loop for periodic follow-up checking."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._followup_worker_loop())
            logger.info("Started Campaign Follow-up Background Worker Loop.")

    async def get_followup_gap(self) -> int:
        """Retrieves configured follow-up gap interval in minutes from MongoDB."""
        if hasattr(self.db, "db") and self.db.db is not None:
            doc = await self.db.db.settings.find_one({"_id": "followup_gap"})
            if doc:
                return doc.get("minutes", self.default_followup_gap_minutes)
        return self.default_followup_gap_minutes

    async def set_followup_gap(self, minutes: int) -> bool:
        """Owner-only: Updates configured follow-up gap interval in minutes."""
        self.default_followup_gap_minutes = max(1, minutes)
        if hasattr(self.db, "db") and self.db.db is not None:
            await self.db.db.settings.update_one(
                {"_id": "followup_gap"},
                {"$set": {"_id": "followup_gap", "minutes": self.default_followup_gap_minutes}},
                upsert=True
            )
            logger.info(f"Updated follow-up gap interval to {self.default_followup_gap_minutes} minutes in MongoDB.")
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

    async def has_user_replied(self, chat_id: str, creator: str) -> bool:
        """Checks message history to see if target fan has replied."""
        messages = await self.f2f_client.get_chat_messages(chat_id, creator)
        if not messages:
            return False

        last_msg = messages[-1] if isinstance(messages, list) else None
        if not last_msg:
            return False

        is_user = last_msg.get("is_from_user", False) or last_msg.get("sender_type") == "user"
        return bool(is_user)

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
                                         test_chat_id: str | None = None) -> dict:
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

            personalized_text = personalize_message(raw_message, user_name=fan_name)
            logger.info(f"Personalized Test Message for creator @{target_creator} to fan '{fan_name}': '{personalized_text}'")

            res = await self.f2f_client.send_message(test_chat_id, target_creator, personalized_text)
            if res:
                cmp_id = await self.create_campaign_record(target_creator, raw_message)
                if hasattr(self.db, "db") and self.db.db is not None:
                    await self.db.db.campaign_user_states.update_one(
                        {"_id": f"{cmp_id}_{test_chat_id}"},
                        {"$set": {
                            "campaign_id": cmp_id,
                            "creator": target_creator,
                            "chat_id": test_chat_id,
                            "fan_name": fan_name,
                            "status": "initial_sent",
                            "initial_sent_at": datetime.utcnow()
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
                    "campaign_id": cmp_id
                }
            else:
                return {
                    "status": "error",
                    "mode": "test",
                    "sent_count": 0,
                    "target_chat_id": test_chat_id,
                    "target_creator": target_creator,
                    "error": f"Failed to send message on behalf of creator @{target_creator} via F2F API"
                }

        # Full Production Online Fan Outreach Mode (Specific to creator channel)
        cmp_id = await self.create_campaign_record(target_creator, raw_message)
        online_chats = await self.f2f_client.get_online_chats(target_creator)
        if not online_chats:
            logger.info(f"No online chats found for creator @{target_creator}.")
            return {"status": "success", "mode": "production", "sent_count": 0, "skipped_replied": 0, "campaign_id": cmp_id}

        sent_count = 0
        skipped_replied = 0

        for chat in online_chats:
            chat_id = chat.get("uuid", chat.get("id"))
            fan_name = chat.get("title") or chat.get("user", {}).get("name") or chat.get("username")

            if not chat_id:
                continue

            if await self.has_user_replied(chat_id, target_creator):
                logger.info(f"Skipping fan {fan_name} ({chat_id}): Fan has already replied!")
                skipped_replied += 1
                continue

            personalized_text = personalize_message(raw_message, user_name=fan_name)
            send_res = await self.f2f_client.send_message(chat_id, target_creator, personalized_text)

            if send_res:
                sent_count += 1
                if hasattr(self.db, "db") and self.db.db is not None:
                    await self.db.db.campaign_user_states.update_one(
                        {"_id": f"{cmp_id}_{chat_id}"},
                        {"$set": {
                            "campaign_id": cmp_id,
                            "creator": target_creator,
                            "chat_id": chat_id,
                            "fan_name": fan_name,
                            "status": "initial_sent",
                            "initial_sent_at": datetime.utcnow()
                        }},
                        upsert=True
                    )

            delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
            logger.info(f"Waiting {delay:.1f}s before next dispatch...")
            await asyncio.sleep(delay)

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
            return {"status": "stopped", "reason": "Fan has replied! Follow-up stopped."}

        configured_template = followup_text or await self.get_followup_text()
        personalized_text = personalize_message(configured_template, user_name=fan_name)

        send_res = await self.f2f_client.send_message(test_chat_id, target_creator, personalized_text)
        if send_res:
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
            return {"status": "error", "reason": f"Failed to send follow-up message on behalf of creator @{target_creator} via API"}

    async def _followup_worker_loop(self):
        """Background worker loop checking every 15 seconds for campaigns due for follow-up."""
        while True:
            try:
                await asyncio.sleep(15)
                if not hasattr(self.db, "db") or self.db.db is None:
                    continue

                now = datetime.utcnow()
                cursor = self.db.db.campaign_runs.find({
                    "status": "active",
                    "followup_scheduled_at": {"$lte": now}
                })
                due_campaigns = await cursor.to_list(length=None)

                for cmp in due_campaigns:
                    cmp_id = cmp["_id"]
                    creator = cmp["creator"]
                    configured_template = cmp.get("followup_text") or await self.get_followup_text()

                    logger.info(f"⏱️ Follow-up Timer Reached! Executing follow-up phase for campaign {cmp_id} (@{creator})...")

                    u_cursor = self.db.db.campaign_user_states.find({
                        "campaign_id": cmp_id,
                        "status": "initial_sent"
                    })
                    pending_users = await u_cursor.to_list(length=None)

                    for user_state in pending_users:
                        chat_id = user_state["chat_id"]
                        fan_name = user_state.get("fan_name", "Fan")

                        # Reply Check Safety (Stop User)
                        if await self.has_user_replied(chat_id, creator):
                            logger.info(f"🛑 Follow-up SKIPPED for fan {fan_name} ({chat_id}): Fan has replied!")
                            await self.db.db.campaign_user_states.update_one(
                                {"_id": user_state["_id"]},
                                {"$set": {"status": "replied_stop", "completed_at": datetime.utcnow()}}
                            )
                            continue

                        # Send Follow-up Message with Name Personalization
                        personalized_followup = personalize_message(configured_template, user_name=fan_name)
                        logger.info(f"📨 Sending Follow-up on behalf of @{creator} to '{fan_name}': '{personalized_followup}'")
                        res = await self.f2f_client.send_message(chat_id, creator, personalized_followup)

                        if res:
                            await self.db.db.campaign_user_states.update_one(
                                {"_id": user_state["_id"]},
                                {"$set": {"status": "followup_sent", "followup_sent_at": datetime.utcnow()}}
                            )

                        delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
                        await asyncio.sleep(delay)

                    # Mark Campaign as Completed and close it!
                    await self.db.db.campaign_runs.update_one(
                        {"_id": cmp_id},
                        {"$set": {"status": "completed", "completed_at": datetime.utcnow()}}
                    )
                    logger.info(f"🎉 Campaign {cmp_id} follow-up phase finished and campaign closed!")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in followup worker loop: {e}", exc_info=True)
