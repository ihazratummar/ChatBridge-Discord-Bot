import logging
import uuid
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("ChatBridge.MongoDatabase")
UNSET = object()

class MongoDatabaseManager:
    def __init__(self, uri: str, db_name: str = "chatbridge"):
        self.uri = uri
        self.db_name = db_name
        self.client: AsyncIOMotorClient | None = None
        self.db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(self.uri)
        self.db = self.client[self.db_name]
        await self.db.bridge_members.create_index([("group_id", 1)])
        await self.db.bridge_members.create_index([("channel_id", 1)])
        logger.info(f"Connected to Cloud MongoDB database '{self.db_name}'.")

    async def close(self):
        if self.client:
            self.client.close()
            self.client = None
            logger.info("Closed Cloud MongoDB connection.")

    async def create_group(self, group_id: str | None = None, name: str = "Sync Group") -> str:
        if self.db is None:
            raise RuntimeError("Database not connected")

        if not group_id:
            group_id = f"grp_{uuid.uuid4().hex[:8]}"

        await self.db.bridge_groups.update_one(
            {"_id": group_id},
            {"$setOnInsert": {"_id": group_id, "id": group_id, "name": name}},
            upsert=True
        )
        return group_id

    async def delete_group(self, group_id: str) -> bool:
        if self.db is None:
            return False
        res = await self.db.bridge_groups.delete_one({"_id": group_id})
        await self.db.bridge_members.delete_many({"group_id": group_id})
        return res.deleted_count > 0

    async def add_or_update_member(self, group_id: str, channel_id: int, mode: str = "bidirectional",
                                    bot_name: str = "ChatBridge Bot", avatar_url: str | None = None,
                                    role_id: str | None = None, webhook_url: str | None = None):
        if self.db is None:
            raise RuntimeError("Database not connected")

        await self.create_group(group_id, f"Group-{group_id}")
        doc_id = f"{group_id}_{channel_id}"

        update_fields = {
            "group_id": group_id,
            "channel_id": channel_id,
            "mode": mode,
            "bot_name": bot_name,
        }
        if avatar_url is not None:
            update_fields["avatar_url"] = avatar_url
        if role_id is not None:
            update_fields["role_id"] = role_id
        if webhook_url is not None:
            update_fields["webhook_url"] = webhook_url

        await self.db.bridge_members.update_one(
            {"_id": doc_id},
            {"$set": update_fields},
            upsert=True
        )

    async def remove_member(self, group_id: str, channel_id: int) -> bool:
        if self.db is None:
            return False
        doc_id = f"{group_id}_{channel_id}"
        res = await self.db.bridge_members.delete_one({"_id": doc_id})

        count = await self.db.bridge_members.count_documents({"group_id": group_id})
        if count == 0:
            await self.delete_group(group_id)

        return res.deleted_count > 0

    async def remove_channel_from_all_groups(self, channel_id: int) -> int:
        if self.db is None:
            return 0
        res = await self.db.bridge_members.delete_many({"channel_id": channel_id})
        count = res.deleted_count

        active_group_ids = await self.db.bridge_members.distinct("group_id")
        await self.db.bridge_groups.delete_many({"_id": {"$nin": active_group_ids}})
        return count

    async def update_member_config(self, channel_id: int, group_id: str | None = None,
                                     bot_name: str | object = UNSET,
                                     role_id: str | None | object = UNSET,
                                     webhook_url: str | None | object = UNSET):
        if self.db is None:
            return

        updates = {}
        if bot_name is not UNSET:
            updates["bot_name"] = bot_name
        if role_id is not UNSET:
            updates["role_id"] = role_id
        if webhook_url is not UNSET:
            updates["webhook_url"] = webhook_url

        if not updates:
            return

        query = {"channel_id": channel_id}
        if group_id:
            query["group_id"] = group_id

        await self.db.bridge_members.update_many(query, {"$set": updates})

    async def get_all_groups(self) -> list[dict]:
        if self.db is None:
            return []

        groups_cursor = self.db.bridge_groups.find({})
        groups = await groups_cursor.to_list(length=None)

        result = []
        for g in groups:
            g_dict = {
                "id": g.get("id", g["_id"]),
                "name": g.get("name", "Sync Group"),
                "created_at": g.get("created_at")
            }
            members_cursor = self.db.bridge_members.find({"group_id": g_dict["id"]})
            members = await members_cursor.to_list(length=None)
            g_dict["members"] = [
                {
                    "group_id": m["group_id"],
                    "channel_id": int(m["channel_id"]),
                    "mode": m.get("mode", "bidirectional"),
                    "bot_name": m.get("bot_name", "ChatBridge Bot"),
                    "avatar_url": m.get("avatar_url"),
                    "role_id": m.get("role_id"),
                    "webhook_url": m.get("webhook_url")
                }
                for m in members
            ]
            result.append(g_dict)
        return result

    async def get_channel_memberships(self, channel_id: int) -> list[dict]:
        if self.db is None:
            return []

        members_cursor = self.db.bridge_members.find({"channel_id": channel_id})
        members = await members_cursor.to_list(length=None)

        result = []
        for m in members:
            grp_id = m["group_id"]
            grp_doc = await self.db.bridge_groups.find_one({"_id": grp_id})
            grp_name = grp_doc.get("name", grp_id) if grp_doc else grp_id

            result.append({
                "group_id": grp_id,
                "group_name": grp_name,
                "channel_id": int(m["channel_id"]),
                "mode": m.get("mode", "bidirectional"),
                "bot_name": m.get("bot_name", "ChatBridge Bot"),
                "avatar_url": m.get("avatar_url"),
                "role_id": m.get("role_id"),
                "webhook_url": m.get("webhook_url")
            })
        return result
