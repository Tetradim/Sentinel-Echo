import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakePositionDb:
    def __init__(self):
        self.positions = {}

    async def insert_position(self, position):
        self.positions[position["id"]] = dict(position)
        return position["id"]

    async def update_position(self, position_id, updates):
        position = dict(self.positions[position_id])
        if "$set" in updates:
            position.update(updates["$set"])
        else:
            position.update(updates)
        self.positions[position_id] = position

    async def get_position_by_id(self, position_id):
        position = self.positions.get(position_id)
        return dict(position) if position else None

    async def get_positions(self, status=None):
        rows = [dict(position) for position in self.positions.values()]
        if status:
            rows = [position for position in rows if position.get("status") == status]
        return rows


class TradingPositionManagerTests(unittest.TestCase):
    def test_position_pnl_uses_configured_contract_multiplier(self):
        from trading import Position

        position = Position(
            id="pos-1",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="2026-06-30",
            quantity=2,
            entry_price=1.00,
            contract_multiplier=50,
        )
        position.current_price = 1.50

        self.assertEqual(position.calculate_pnl(), 50.0)

    def test_default_position_manager_can_persist_positions_in_database(self):
        from trading import DefaultPositionManager

        db = FakePositionDb()
        manager = DefaultPositionManager(db=db)

        opened = asyncio.run(
            manager.open_position(
                position_id="pos-1",
                ticker="SPY",
                strike=500.0,
                option_type="CALL",
                expiration="2026-06-30",
                quantity=2,
                entry_price=1.00,
            )
        )
        restarted_manager = DefaultPositionManager(db=db)
        open_positions = asyncio.run(restarted_manager.get_positions("open"))
        closed = asyncio.run(restarted_manager.close_position("pos-1", "closed"))

        self.assertEqual(opened["id"], "pos-1")
        self.assertEqual([position["id"] for position in open_positions], ["pos-1"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(db.positions["pos-1"]["status"], "closed")


if __name__ == "__main__":
    unittest.main()
