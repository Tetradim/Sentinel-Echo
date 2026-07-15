"""Direct trade lookup methods for reconciliation recovery."""
from __future__ import annotations

import json

from database.abstraction import MongoDBDatabase, SQLiteDatabase


async def _mongo_get_trade_by_id(self, trade_id: str):
    return await self.db.trades.find_one({"id": trade_id}, {"_id": 0})


async def _sqlite_get_trade_by_id(self, trade_id: str):
    await self._ensure_ready()
    import aiosqlite

    async with aiosqlite.connect(self.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT data FROM trades WHERE id = ?",
            (trade_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return json.loads(row["data"]) if row else None


MongoDBDatabase.get_trade_by_id = _mongo_get_trade_by_id
SQLiteDatabase.get_trade_by_id = _sqlite_get_trade_by_id
