import os
import aiosqlite
import logging
import uuid

logger = logging.getLogger("ChatBridge.Database")
DB_PATH = os.getenv("DB_PATH", "chatbridge.db")
MONGODB_URI = os.getenv("MONGODB_URI")

UNSET = object()

def get_database_manager():
    """Factory returning MongoDatabaseManager if MONGODB_URI is set, else SQLite DatabaseManager."""
    uri = os.getenv("MONGODB_URI")
    if uri and uri.strip():
        from core.mongo_database import MongoDatabaseManager
        logger.info("Selected Database Backend: Cloud MongoDB Atlas")
        return MongoDatabaseManager(uri=uri.strip())
    else:
        logger.info(f"Selected Database Backend: Local SQLite ({DB_PATH})")
        return DatabaseManager()

class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")
        await self._create_tables()
        logger.info(f"Connected to SQLite database at '{self.db_path}' (WAL mode enabled).")

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Closed SQLite database connection.")

    async def _create_tables(self):
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS bridge_groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS bridge_members (
                group_id TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                mode TEXT DEFAULT 'bidirectional',
                bot_name TEXT DEFAULT 'ChatBridge Bot',
                avatar_url TEXT,
                role_id TEXT,
                webhook_url TEXT,
                PRIMARY KEY (group_id, channel_id),
                FOREIGN KEY (group_id) REFERENCES bridge_groups(id) ON DELETE CASCADE
            );
        """)
        await self._db.commit()

    async def create_group(self, group_id: str | None = None, name: str = "Sync Group") -> str:
        if not self._db:
            raise RuntimeError("Database not connected")

        if not group_id:
            group_id = f"grp_{uuid.uuid4().hex[:8]}"

        await self._db.execute(
            "INSERT OR IGNORE INTO bridge_groups (id, name) VALUES (?, ?)",
            (group_id, name)
        )
        await self._db.commit()
        return group_id

    async def delete_group(self, group_id: str) -> bool:
        if not self._db:
            return False
        cursor = await self._db.execute("DELETE FROM bridge_groups WHERE id = ?", (group_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def add_or_update_member(self, group_id: str, channel_id: int, mode: str = "bidirectional",
                                    bot_name: str = "ChatBridge Bot", avatar_url: str | None = None,
                                    role_id: str | None = None, webhook_url: str | None = None):
        if not self._db:
            raise RuntimeError("Database not connected")

        await self.create_group(group_id, f"Group-{group_id}")

        await self._db.execute("""
            INSERT INTO bridge_members (group_id, channel_id, mode, bot_name, avatar_url, role_id, webhook_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id, channel_id) DO UPDATE SET
                mode = excluded.mode,
                bot_name = COALESCE(excluded.bot_name, bridge_members.bot_name),
                avatar_url = COALESCE(excluded.avatar_url, bridge_members.avatar_url),
                role_id = COALESCE(excluded.role_id, bridge_members.role_id),
                webhook_url = COALESCE(excluded.webhook_url, bridge_members.webhook_url)
        """, (group_id, channel_id, mode, bot_name, avatar_url, role_id, webhook_url))
        await self._db.commit()

    async def remove_member(self, group_id: str, channel_id: int) -> bool:
        if not self._db:
            return False
        cursor = await self._db.execute(
            "DELETE FROM bridge_members WHERE group_id = ? AND channel_id = ?",
            (group_id, channel_id)
        )
        await self._db.commit()

        async with self._db.execute("SELECT COUNT(*) as count FROM bridge_members WHERE group_id = ?", (group_id,)) as c_cur:
            row = await c_cur.fetchone()
            if row and row["count"] == 0:
                await self.delete_group(group_id)

        return cursor.rowcount > 0

    async def remove_channel_from_all_groups(self, channel_id: int) -> int:
        if not self._db:
            return 0
        cursor = await self._db.execute("DELETE FROM bridge_members WHERE channel_id = ?", (channel_id,))
        count = cursor.rowcount
        await self._db.commit()

        await self._db.execute("""
            DELETE FROM bridge_groups WHERE id NOT IN (SELECT DISTINCT group_id FROM bridge_members)
        """)
        await self._db.commit()
        return count

    async def update_member_config(self, channel_id: int, group_id: str | None = None,
                                     bot_name: str | object = UNSET,
                                     role_id: str | None | object = UNSET,
                                     webhook_url: str | None | object = UNSET):
        if not self._db:
            return

        updates = []
        params = []

        if bot_name is not UNSET:
            updates.append("bot_name = ?")
            params.append(bot_name)
        if role_id is not UNSET:
            updates.append("role_id = ?")
            params.append(role_id)
        if webhook_url is not UNSET:
            updates.append("webhook_url = ?")
            params.append(webhook_url)

        if not updates:
            return

        query = f"UPDATE bridge_members SET {', '.join(updates)} WHERE channel_id = ?"
        params.append(channel_id)

        if group_id:
            query += " AND group_id = ?"
            params.append(group_id)

        await self._db.execute(query, tuple(params))
        await self._db.commit()

    async def get_all_groups(self) -> list[dict]:
        if not self._db:
            return []

        async with self._db.execute("SELECT * FROM bridge_groups") as cursor:
            groups = await cursor.fetchall()

        result = []
        for g in groups:
            g_dict = dict(g)
            async with self._db.execute("SELECT * FROM bridge_members WHERE group_id = ?", (g_dict["id"],)) as m_cur:
                members = await m_cur.fetchall()
                g_dict["members"] = [dict(m) for m in members]
            result.append(g_dict)
        return result

    async def get_channel_memberships(self, channel_id: int) -> list[dict]:
        if not self._db:
            return []
        async with self._db.execute("""
            SELECT m.*, g.name as group_name
            FROM bridge_members m
            JOIN bridge_groups g ON m.group_id = g.id
            WHERE m.channel_id = ?
        """, (channel_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
