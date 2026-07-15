from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRADING_ROUTE = ROOT / "backend" / "routes" / "trading.py"
RUNTIME_APP = ROOT / "backend" / "runtime_app.py"
POSITIONS_UI = ROOT / "frontend" / "app" / "positions.tsx"
LIVE_UI = ROOT / "frontend" / "app" / "live-operations.tsx"
LAYOUT = ROOT / "frontend" / "app" / "_layout.tsx"
BROKER_OPERATIONS = ROOT / "backend" / "routes" / "live_broker_operations.py"


def test_positions_sell_control_uses_durable_broker_lifecycle():
    route = TRADING_ROUTE.read_text(encoding="utf-8")
    ui = POSITIONS_UI.read_text(encoding="utf-8")

    assert '@router.post("/positions/{position_id}/sell")' in route
    assert "get_configured_broker_client" in route
    assert "build_client_order_id" in route
    assert "server.monitor_fill" in route
    assert '"status": "submitted"' in route
    assert "/api/positions/${selected.id}/sell" in ui
    assert "The position will change only after broker fills" in ui
    assert "Fallback to demo data on error" not in ui
    assert "setPositions(DEMO_POSITIONS)" in ui  # explicit DEMO_MODE path remains


def test_live_operations_router_is_mounted_in_production_app():
    runtime = RUNTIME_APP.read_text(encoding="utf-8")
    live_ui = LIVE_UI.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert '"/api/live-operations"' in runtime
    assert "live_operations_router" in runtime
    assert "/api/live-operations?limit=250" in live_ui
    assert "position_supervisor" in live_ui
    assert "unresolved_orders" in live_ui
    assert "live-operations" in layout


def test_broker_config_ui_paths_are_backed_by_runtime_routes():
    route = BROKER_OPERATIONS.read_text(encoding="utf-8")
    runtime = RUNTIME_APP.read_text(encoding="utf-8")

    assert '@router.post("/broker/switch/{broker_id}")' in route
    assert '@router.post("/broker/check/{broker_id}")' in route
    assert 'LIVE_EXECUTION_BROKERS = {"alpaca", "tradier"}' in route
    assert "live_broker_operations_router" in runtime
    assert '"/api/live-brokers"' in runtime
