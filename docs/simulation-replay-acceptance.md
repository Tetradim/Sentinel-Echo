# Simulation Replay Acceptance

`POST /api/simulation-engine/replay-preview` returns a preview-only replay report. No orders are placed.

Replay fixtures can include expected outcomes either on each event payload:

```json
{
  "event_id": "discord_alert:m1",
  "payload": {
    "message": {"channel_id": "alerts", "content": "BTO SPY 500C 6/21 @ 1.25"},
    "expected": {
      "parsed": {"ticker": "SPY", "alert_type": "buy"},
      "would_insert_alert": true,
      "would_request_trade": true,
      "skip_reason": null,
      "execution_reason": null
    }
  }
}
```

Or in a top-level `expected_results` object keyed by `event_id`.

Only supplied fields are checked. The preview response includes a top-level `acceptance` summary and per-result `acceptance.mismatches` entries for deterministic pass/fail review.
