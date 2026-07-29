import aiosqlite
import logging

logger = logging.getLogger("ChatBridge.Database")
DB_PATH = "chatbridge.db"

class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        # Enable WAL mode for high concurrency and foreign keys for data integrity
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
            CREATE TABLE IF NOT EXISTS bridges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_a_id INTEGER UNIQUE NOT NULL,
                channel_b_id INTEGER UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS direction_configs (
                bridge_id INTEGER NOT NULL,
                direction TEXT NOT NULL, -- 'a_to_b' or 'b_to_a'
                webhook_url TEXT,
                bot_name TEXT DEFAULT 'ChatBridge Bot',
                avatar_url TEXT,
                role_id TEXT,
                PRIMARY KEY (bridge_id, direction),
                FOREIGN KEY (bridge_id) REFERENCES bridges(id) ON DELETE CASCADE
            );
        """)
        await self._db.commit()

    async def get_all_bridges(self) -> list[dict]:
        if not self._db:
            return []
        async with self._db.execute("SELECT * FROM bridges") as cursor:
            bridges = await cursor.fetchall()

        result = []
        for b in bridges:
            b_dict = dict(b)
            async with self._db.execute("SELECT * FROM direction_configs WHERE bridge_id = ?", (b_dict["id"],)) as dir_cursor:
                dirs = await dir_cursor.fetchall()
                dir_dict = {d["direction"]: dict(d) for d in dirs}
                b_dict["direction_a_to_b"] = dir_dict.get("a_to_b", {
                    "bot_name": "Forgotten Names", "avatar_url": None, "role_id": None, "webhook_url": None
                })
                b_dict["direction_b_to_a"] = dir_dict.get("b_to_a", {
                    "bot_name": "Message Notifier", "avatar_url": None, "role_id": None, "webhook_url": None
                })
            result.append(b_dict)
        return result

    async def add_or_update_bridge(self, channel_a_id: int, channel_b_id: int,
                                    name_a_to_b: str = "Forgotten Names",
                                    name_b_to_a: str = "Message Notifier") -> dict:
        if not self._db:
            raise RuntimeError("Database not connected")

        # Check if bridge exists with either channel
        async with self._db.execute(
            "SELECT id FROM bridges WHERE channel_a_id IN (?, ?) OR channel_b_id IN (?, ?)",
            (channel_a_id, channel_b_id, channel_a_id, channel_b_id)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            bridge_id = row["id"]
            await self._db.execute(
                "UPDATE bridges SET channel_a_id = ?, channel_b_id = ? WHERE id = ?",
                (channel_a_id, channel_b_id, bridge_id)
            )
        else:
            async with self._db.execute(
                "INSERT INTO bridges (channel_a_id, channel_b_id) VALUES (?, ?)",
                (channel_a_id, channel_b_id)
            ) as cursor:
                bridge_id = cursor.lastrowid

            # Initialize direction configs if not present
            await self._db.execute(
                "INSERT OR IGNORE INTO direction_configs (bridge_id, direction, bot_name) VALUES (?, 'a_to_b', ?)",
                (bridge_id, name_a_to_b)
            )
            await self._db.execute(
                "INSERT OR IGNORE INTO direction_configs (bridge_id, direction, bot_name) VALUES (?, 'b_to_a', ?)",
                (bridge_id, name_b_to_a)
            )

        await self._db.commit()
        all_bridges = await self.get_all_bridges()
        return next(b for b in all_bridges if b["id"] == bridge_id)

    async def update_webhook(self, bridge_id: int, direction: str, webhook_url: str | None):
        if not self._db:
            return
        await self._db.execute("""
            INSERT INTO direction_configs (bridge_id, direction, webhook_url)
            VALUES (?, ?, ?)
            ON CONFLICT(bridge_id, direction) DO UPDATE SET webhook_url = excluded.webhook_url
        """, (bridge_id, direction, webhook_url))
        await self._db.commit()

    async def update_bot_name(self, bridge_id: int, direction: str, name: str):
        if not self._db:
            return
        await self._db.execute("""
            UPDATE direction_configs SET bot_name = ? WHERE bridge_id = ? AND direction = ?
        """, (name, bridge_id, direction))
        await self._db.commit()

    async def update_role_ping(self, bridge_id: int, direction: str, role_id: str | None):
        if not self._db:
            return
        await self._db.execute("""
            UPDATE direction_configs SET role_id = ? WHERE bridge_id = ? AND direction = ?
        """, (role_id, bridge_id, direction))
        await self._db.commit()

    async def remove_bridge_by_channel(self, channel_id: int) -> bool:
        if not self._db:
            return False
        async with self._db.execute(
            "SELECT id FROM bridges WHERE channel_a_id = ? OR channel_b_id = ?",
            (channel_id, channel_id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False

        bridge_id = row["id"]
        await self._db.execute("DELETE FROM direction_configs WHERE bridge_id = ?", (bridge_id,))
        await self._db.execute("DELETE FROM bridges WHERE id = ?", (bridge_id,))
        await self._db.commit()
        return True
