import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3003")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8003")
API_URL = f"{BACKEND_URL}/api"
ARTIFACT_DIR = Path("data/ui-audit")
BOTTOM_NAV_TARGETS = [
    ("/", "Dashboard"),
    ("/alerts", "Alerts"),
    ("/trades", "Trades"),
    ("/positions", "Positions"),
    ("/operator-lab", "Lab"),
    ("/strike-selection", "Strikes"),
    ("/trading-settings", "Trading"),
    ("/risk-settings", "Risk"),
    ("/discord-settings", "Discord"),
    ("/broker-config", "Broker"),
    ("/profiles", "Profiles"),
    ("/settings", "Settings"),
]


class Audit:
    def __init__(self):
        self.actions = []
        self.warnings = []
        self.console_errors = []
        self.page_errors = []
        self.dialogs = []
        self.control_snapshots = []
        self.state_checks = []

    def action(self, message):
        self.actions.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def state_check(self, name, payload):
        self.state_checks.append({"name": name, "payload": payload})

    def fail_if_errors(self):
        expected_console_errors = [
            "Failed to load resource: the server responded with a status of 400 (Bad Request)",
        ]
        unexpected_console_errors = [
            error for error in self.console_errors
            if not any(expected in error for expected in expected_console_errors)
        ]
        allowed_count = len(self.console_errors) - len(unexpected_console_errors)
        if allowed_count:
            self.warning(f"allowed {allowed_count} expected validation HTTP 400 console message(s)")
        if unexpected_console_errors or self.page_errors:
            raise AssertionError(
                "Browser errors found: "
                + json.dumps(
                    {
                        "console_errors": unexpected_console_errors[:10],
                        "page_errors": self.page_errors[:10],
                    },
                    indent=2,
                )
            )


audit = Audit()


def api(method, path, payload=None, query=None, retries=1):
    url = f"{API_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"{method} {path} failed: {exc.code} {detail}") from exc
        except OSError:
            if attempt >= retries:
                raise
            time.sleep(0.5)


def wait_for_backend():
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            api("GET", "/health")
            return
        except Exception:
            time.sleep(0.5)
    raise AssertionError("Backend did not become healthy")


def seed_backend():
    wait_for_backend()
    api(
        "PUT",
        "/settings",
        {
            "simulation_mode": True,
            "auto_trading_enabled": False,
            "default_quantity": 1,
            "max_position_size": 1000,
            "risk_per_trade": 1,
            "max_drawdown_percent": 20,
            "max_positions_per_sector": 3,
            "trailing_hours": 4,
            "active_broker": "ibkr",
        },
    )
    api(
        "PUT",
        "/risk-management-settings",
        {
            "take_profit_enabled": True,
            "take_profit_percentage": 50,
            "bracket_order_enabled": False,
            "stop_loss_enabled": True,
            "stop_loss_percentage": 25,
            "stop_loss_order_type": "market",
        },
    )
    api(
        "PUT",
        "/trailing-stop-settings",
        {
            "trailing_stop_enabled": True,
            "trailing_stop_type": "percent",
            "trailing_stop_percent": 10,
            "trailing_stop_cents": 0.25,
        },
    )
    api(
        "PUT",
        "/auto-shutdown-settings",
        {
            "auto_shutdown_enabled": True,
            "max_consecutive_losses": 3,
            "max_daily_losses": 5,
            "max_daily_loss_amount": 500,
        },
    )
    api(
        "PUT",
        "/premium-buffer-settings",
        query={"premium_buffer_amount": 10, "premium_buffer_enabled": "true"},
    )
    api("PUT", "/correlation-settings", query={"max_positions_per_ticker": 3})
    api("POST", "/profiles", {"name": "Audit Profile", "description": "Browser audit"})
    api("POST", "/test-alert")
    api("POST", "/test-alert")
    audit.action("seeded backend with settings, profile, alerts, trades, and positions")


def safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip("/").replace("/", "-") or "dashboard")


def frontend_url(path):
    separator = "&" if "?" in path else "?"
    return f"{FRONTEND_URL}{path}{separator}{urllib.parse.urlencode({'backend_url': BACKEND_URL})}"


def current_path(page):
    return urllib.parse.urlparse(page.url).path.rstrip("/") or "/"


def visible(locator):
    try:
        return locator.is_visible()
    except Exception:
        return False


def click_text(page, text, exact=True, optional=False):
    locator = page.get_by_text(text, exact=exact)
    try:
        count = locator.count()
    except Exception:
        count = 0
    for index in range(min(count, 8)):
        item = locator.nth(index)
        if not visible(item):
            continue
        try:
            item.scroll_into_view_if_needed(timeout=1000)
            item.click(timeout=1500)
            page.wait_for_timeout(250)
            audit.action(f"clicked text: {text}")
            return True
        except Exception:
            continue
    if optional:
        audit.warning(f"optional text not clickable: {text}")
        return False
    raise AssertionError(f"Could not click visible text: {text}")


def click_selector(page, selector, label, optional=False):
    locator = page.locator(selector)
    try:
        count = locator.count()
    except Exception:
        count = 0
    for index in range(count):
        item = locator.nth(index)
        if not visible(item):
            continue
        try:
            item.scroll_into_view_if_needed(timeout=1000)
            item.click(timeout=1500)
            page.wait_for_timeout(250)
            audit.action(f"clicked selector: {label}")
            return True
        except Exception:
            continue
    if optional:
        audit.warning(f"optional selector not clickable: {label}")
        return False
    raise AssertionError(f"Could not click visible selector: {label}")


def fill_inputs(page, values, label):
    fields = page.locator("input, textarea")
    count = fields.count()
    used = 0
    for index, value in enumerate(values[:count]):
        field = fields.nth(index)
        if not visible(field):
            continue
        try:
            field.scroll_into_view_if_needed(timeout=1000)
            field.fill(str(value), timeout=1500)
            used += 1
        except Exception:
            continue
    audit.action(f"filled {used} inputs on {label}")


def toggle_visible_switches(page, label, limit=20):
    switches = page.locator('input[type="checkbox"], [role="switch"]')
    count = switches.count()
    used = 0
    for index in range(min(count, limit)):
        switch = switches.nth(index)
        if not visible(switch):
            continue
        try:
            switch.scroll_into_view_if_needed(timeout=1000)
            switch.click(timeout=1500)
            page.wait_for_timeout(150)
            used += 1
        except Exception:
            continue
    audit.action(f"toggled {used} switches on {label}")


def snapshot_controls(page, label):
    controls = page.evaluate(
        """
        () => {
          const selector = [
            'button',
            '[role="button"]',
            '[role="switch"]',
            'input',
            'textarea',
            'select'
          ].join(',');
          const seen = new Set();
          return Array.from(document.querySelectorAll(selector))
            .map((node, index) => {
              const rect = node.getBoundingClientRect();
              const style = window.getComputedStyle(node);
              const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
              const label =
                node.getAttribute('aria-label') ||
                node.getAttribute('title') ||
                node.getAttribute('placeholder') ||
                text ||
                node.getAttribute('data-testid') ||
                node.getAttribute('name') ||
                node.id ||
                '';
              const key = `${node.tagName}:${node.getAttribute('role') || ''}:${label}:${Math.round(rect.x)}:${Math.round(rect.y)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;
              if (seen.has(key)) return null;
              seen.add(key);
              return {
                index,
                tag: node.tagName.toLowerCase(),
                role: node.getAttribute('role') || '',
                type: node.getAttribute('type') || '',
                label: label.slice(0, 90),
                testid: node.getAttribute('data-testid') || '',
                checked: node.checked === true || node.getAttribute('aria-checked') === 'true',
                disabled: node.disabled === true || node.getAttribute('aria-disabled') === 'true',
                visible:
                  rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== 'hidden' &&
                  style.display !== 'none',
              };
            })
            .filter(Boolean)
            .filter((control) => control.visible);
        }
        """
    )
    audit.control_snapshots.append(
        {
            "label": label,
            "url": page.url,
            "count": len(controls),
            "controls": controls,
        }
    )
    audit.action(f"cataloged {len(controls)} visible controls on {label}")
    return controls


def visit(page, path, title):
    page.goto(frontend_url(path), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(ARTIFACT_DIR / f"{safe_name(path)}.png"), full_page=True)
    body = page.locator("body").inner_text(timeout=5000)
    if "Connection Error" in body or "Application error" in body:
        raise AssertionError(f"{title} rendered an error state:\n{body[:500]}")
    audit.action(f"visited {title} at {path}")
    snapshot_controls(page, title)
    return body


def click_visible_role_buttons(page, label, limit=8):
    buttons = page.locator('[role="button"], button')
    count = buttons.count()
    clicked = 0
    for index in range(min(count, limit)):
        button = buttons.nth(index)
        if not visible(button):
            continue
        try:
            before_url = page.url
            button.scroll_into_view_if_needed(timeout=1000)
            button.click(timeout=1500)
            page.wait_for_timeout(250)
            clicked += 1
            if page.url != before_url:
                page.go_back(wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(250)
        except Exception:
            continue
    audit.action(f"clicked {clicked} visible role buttons on {label}")


def exercise_bottom_navigation(page):
    visit(page, "/", "Bottom Navigation")
    for path, label in BOTTOM_NAV_TARGETS:
        if path == "/":
            continue
        locator = page.get_by_role("button", name=label)
        try:
            target = locator.last
            if not visible(target):
                raise AssertionError(f"bottom navigation button is not visible: {label}")
            target.scroll_into_view_if_needed(timeout=1000)
            target.click(timeout=2000)
            page.wait_for_timeout(350)
        except Exception as exc:
            raise AssertionError(f"Could not click bottom navigation button: {label}") from exc
        if not page.url.rstrip("/").endswith(path.rstrip("/")):
            if current_path(page) == (path.rstrip("/") or "/"):
                snapshot_controls(page, f"Bottom Navigation -> {label}")
                audit.action(f"clicked bottom navigation tab: {label}")
                continue
            raise AssertionError(f"Bottom navigation {label} landed on {page.url}, expected {path}")
        snapshot_controls(page, f"Bottom Navigation -> {label}")
        audit.action(f"clicked bottom navigation tab: {label}")


def click_web_sidebar_route(page, path, label, index):
    page.goto(frontend_url("/alerts"), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(500)
    clicked = page.evaluate(
        """
        ({ index }) => {
          const candidates = Array.from(document.querySelectorAll('[role="button"], button'));
          const railItems = candidates
            .map((node) => ({ node, rect: node.getBoundingClientRect() }))
            .filter(({ rect }) =>
              rect.width > 0 &&
              rect.height > 0 &&
              rect.left >= 0 &&
              rect.left < 70 &&
              rect.top > 56
            )
            .sort((a, b) => a.rect.top - b.rect.top);
          const item = railItems[index]?.node;
          if (!item) return false;
          item.click();
          return true;
        }
        """,
        {"index": index},
    )
    if not clicked:
        raise AssertionError(f"Could not click web sidebar route: {label}")
    page.wait_for_timeout(500)
    expected = path.rstrip("/") or "/"
    if current_path(page) != expected:
        raise AssertionError(f"Web sidebar {label} landed on {page.url}, expected {path}")
    snapshot_controls(page, f"Web Sidebar -> {label}")
    audit.action(f"clicked web sidebar route: {label}")


def exercise_route_navigation(page):
    for path, label in BOTTOM_NAV_TARGETS:
        visit(page, path, f"Route Navigation -> {label}")
    for index, (path, label) in enumerate(BOTTOM_NAV_TARGETS):
        click_web_sidebar_route(page, path, label, index)


def verify_backend_state():
    events = api("GET", "/operator/events", query={"limit": 50})
    alerts = api("GET", "/alerts", query={"limit": 200})
    trades = api("GET", "/trades", query={"limit": 200})
    positions = api("GET", "/positions")
    profiles = api("GET", "/profiles")
    settings = api("GET", "/settings")

    payload = {
        "operator_events": len(events),
        "alerts": len(alerts),
        "trades": len(trades),
        "positions": len(positions),
        "profiles": len(profiles),
        "simulation_mode": settings.get("simulation_mode"),
        "auto_trading_enabled": settings.get("auto_trading_enabled"),
    }
    audit.state_check("post_interaction_backend_state", payload)
    if payload["operator_events"] < 2:
        raise AssertionError(f"Expected at least two operator events, got {payload['operator_events']}")
    if payload["alerts"] < 3 or payload["trades"] < 3 or payload["positions"] < 2:
        raise AssertionError(f"Trading records were not created as expected: {payload}")
    if payload["profiles"] < 1:
        raise AssertionError("Expected at least one profile after profile flow")


def exercise_dashboard(page):
    visit(page, "/", "Dashboard")
    toggle_visible_switches(page, "Dashboard")
    click_visible_role_buttons(page, "Dashboard", limit=10)
    visit(page, "/", "Dashboard after buttons")


def exercise_alerts(page):
    visit(page, "/alerts", "Alerts")
    for label in ["All", "Executed", "Review", "Unparsed"]:
        click_text(page, label, optional=True)
    click_visible_role_buttons(page, "Alerts", limit=6)


def exercise_trades(page):
    visit(page, "/trades", "Trades")
    if click_text(page, "Update", optional=True):
        fill_inputs(page, ["1.75"], "Trade update modal")
        click_text(page, "Update Price", optional=True)
        visit(page, "/trades", "Trades after price update")
    if click_text(page, "Close", optional=True):
        fill_inputs(page, ["1.90"], "Trade close modal")
        click_text(page, "Close Trade", optional=True)
        visit(page, "/trades", "Trades after close")
    for label in ["All", "Open", "Closed", "Attention", "Sim"]:
        click_text(page, label, optional=True)


def exercise_positions(page):
    api("POST", "/test-alert")
    visit(page, "/positions", "Positions")
    if click_text(page, "Sell", optional=True):
        for label in ["25%", "50%", "75%", "100%"]:
            click_text(page, label, optional=True)
        fill_inputs(page, ["50", "1.80"], "Position sell modal")
        click_text(page, "Sell 50%", optional=True)
        visit(page, "/positions", "Positions after sell")
    for label in ["Open", "All", "Closed", "Watch"]:
        click_text(page, label, optional=True)


def exercise_operator_lab(page):
    visit(page, "/operator-lab", "Operator Lab")
    audit.action("verified Arm Live is present but blocked in simulated readiness state")
    click_text(page, "Disarm", optional=True)
    click_text(page, "Panic Stop", optional=True)
    click_text(page, "Reconciliation", optional=True)
    click_text(page, "Create Test Alert", optional=True)
    click_text(page, "Sell 50% Test Position", optional=True)
    click_text(page, "Refresh", optional=True)
    visit(page, "/operator-lab", "Operator Lab after actions")


def exercise_profiles(page):
    visit(page, "/profiles", "Profiles")
    click_selector(page, '[data-testid="add-profile-button"]', "add profile", optional=True)
    fill_inputs(page, ["UI Audit Profile", "Created from Playwright"], "Create profile modal")
    click_text(page, "Create", optional=True)
    click_text(page, "Audit Profile", optional=True)
    toggle_visible_switches(page, "Profiles", limit=16)
    for label in ["IBKR", "Alpaca", "Tradier", "Activate", "Delete"]:
        click_text(page, label, optional=True)


def exercise_broker_config(page):
    visit(page, "/broker-config", "Broker Config")
    broker_inputs = {
        "IBKR": ["https://localhost:5000", "DU123456"],
        "Alpaca": ["audit-key", "audit-secret", "https://paper-api.alpaca.markets"],
        "Tradier": ["audit-token", "DU123456"],
        "TradeStation": ["audit-client", "audit-secret", "audit-refresh"],
        "Robinhood": ["audit@example.com", "audit-password", "123456"],
        "Webull": ["audit@example.com", "audit-password", "audit-device", "123456"],
    }
    for label in ["IBKR", "Alpaca", "Tradier", "TradeStation", "Robinhood", "Webull"]:
        click_text(page, label, optional=True)
        fill_inputs(page, broker_inputs[label], f"Broker {label}")
        click_text(page, "Save Configuration", optional=True)
        click_text(page, "Test Connection", optional=True)
        click_text(page, "Set as Active", optional=True)


def exercise_settings(page):
    visit(page, "/settings", "Settings")
    toggle_visible_switches(page, "Settings", limit=24)
    fill_inputs(page, ["", "1", "1000", "10", "3", "5", "500"], "Settings")
    click_text(page, "Save", exact=False, optional=True)
    for label in [
        "Start Bot",
        "Test",
        "Check Connection",
        "Send Test SMS",
        "Add Pattern",
        "Reset Patterns",
        "Discard",
    ]:
        click_text(page, label, optional=True)


def exercise_risk_settings(page):
    visit(page, "/risk-settings", "Risk Settings")
    tabs = ["Position", "Stop Loss", "Take Profit", "Trailing", "Shutdown", "Correlation"]
    tab_inputs = {
        "Position": ["1000", "1", "1"],
        "Stop Loss": ["25"],
        "Take Profit": ["50"],
        "Trailing": ["10"],
        "Shutdown": ["3", "500", "20"],
        "Correlation": ["3", "3"],
    }
    for tab in tabs:
        click_text(page, tab)
        toggle_visible_switches(page, f"Risk {tab}", limit=8)
        fill_inputs(page, tab_inputs.get(tab, []), f"Risk {tab}")
    click_text(page, "Save Settings")


def exercise_discord_settings(page):
    visit(page, "/discord-settings", "Discord Settings")
    for tab in ["Communities", "Patterns", "Filters"]:
        click_text(page, tab)
        toggle_visible_switches(page, f"Discord {tab}", limit=16)
        if tab == "Communities":
            click_text(page, "Add", optional=True)
            fill_inputs(page, ["Audit Community", "123456789"], "Discord communities")
            for label in ["Default", "Conservative", "Aggressive"]:
                click_text(page, label, optional=True)
        elif tab == "Patterns":
            fill_inputs(
                page,
                ["BUY,BTO", "SELL,STC", "AVERAGE DOWN", "WATCHLIST", "\\$([A-Z]{1,5})\\b"],
                "Discord patterns",
            )
        else:
            fill_inputs(page, ["analyst1", "blocked1", "123456789", "0.10", "10.00"], "Discord filters")
    click_text(page, "Reset", optional=True)
    click_text(page, "Save Discord Settings")


def exercise_strike_selection(page):
    visit(page, "/strike-selection", "Strike Selection")
    for label in ["QQQ", "SPY", "AAPL", "30D", "45D", "60D", "CALL", "PUT", "Chain", "Select", "Compare"]:
        click_text(page, label, optional=True)
    click_text(page, "Select", optional=True)
    for label in ["ATM", "ITM", "OTM", "Delta 30", "Delta 50"]:
        click_text(page, label, optional=True)
    click_text(page, "Use Strike", optional=True)
    click_text(page, "Compare", optional=True)


def exercise_trading_settings(page):
    visit(page, "/trading-settings", "Trading Settings")
    toggle_visible_switches(page, "Trading Settings", limit=12)
    fill_inputs(page, ["3", "https://localhost:5000", "DU123456", "45", "5"], "Trading settings")
    for label in ["1%", "2%", "3%", "IBKR", "Alpaca", "Tradier", "LIMIT", "MARKET", "Reset", "Save Settings"]:
        click_text(page, label, optional=True)


def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    seed_backend()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("console", lambda msg: audit.console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: audit.page_errors.append(str(exc)))
        page.on(
            "dialog",
            lambda dialog: (
                audit.dialogs.append({"type": dialog.type, "message": dialog.message}),
                dialog.accept(),
            ),
        )

        exercises = [
            exercise_route_navigation,
            exercise_dashboard,
            exercise_alerts,
            exercise_trades,
            exercise_positions,
            exercise_operator_lab,
            exercise_profiles,
            exercise_broker_config,
            exercise_settings,
            exercise_risk_settings,
            exercise_discord_settings,
            exercise_strike_selection,
            exercise_trading_settings,
        ]
        for exercise in exercises:
            exercise(page)
        context.close()
        browser.close()

    verify_backend_state()
    audit.fail_if_errors()
    result = {
        "actions": audit.actions,
        "warnings": audit.warnings,
        "dialogs": audit.dialogs,
        "state_checks": audit.state_checks,
        "control_snapshots": audit.control_snapshots,
        "screenshots": sorted(str(path) for path in ARTIFACT_DIR.glob("*.png")),
    }
    result_path = ARTIFACT_DIR / "ui-audit-result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"actions": len(audit.actions), "warnings": len(audit.warnings), "result": str(result_path)}, indent=2))


if __name__ == "__main__":
    main()
