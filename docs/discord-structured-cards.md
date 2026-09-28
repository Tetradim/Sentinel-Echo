# Discord structured option cards

## Supported input

Echo recognizes the text-based AQTrades cards observed in Discord, plus unbranded
cards with the same labelled contract, expiration, and entry layout. These are
Discord embeds, not screenshots. Sentinel Link forwards the title, description,
fields, and footer separately. It preserves field line breaks and does not duplicate
embed text into the message body.

- A new entry needs one ticker/strike/call-or-put contract, a labelled expiration
  including its year, and a positive labelled entry price.
- Expiration accepts month names, YYYY-MM-DD, and MM/DD/YY or MM/DD/YYYY. Footer
  timestamps and fractions such as 3/4 are never expiration sources.
- Position Update with Type "Trimmed 3/4" requests a 75% exit of the remaining
  position, using the existing whole-contract rounding rule. Explicit percentages
  are also accepted. The reported exit price identifies the notification; the
  execution engine obtains its own executable quote.
- Type "Full Close" requests a 100% exit. A final close on an edited entry card
  takes priority over that card's previous trim history.
- Type "Comment" is recorded as non-trading. Profit commentary does not create
  orders or overwrite broker marks.
- An entry card already containing a trim is an exit update, never a fresh buy.

Unknown card layouts, multiple contracts, contradictory values, trim histories with
multiple different actions, and missing essential fields are not guessed. They
return a reason instead of falling through to Echo's free-text buy/sell inference.
Actual image-only alerts do not have OCR support and are not trade-ready inputs.

## Position matching and duplicate actions

Exits must match exactly one open/partial option position at the active broker whose
originating alert belongs to the same source channel. Missing expiry is resolved
only from that position. The execution plan is restricted to its position ID.
Missing source provenance, no local position yet, and ambiguous expirations block
the card exit with an explicit reason; these require reconciliation, not guessing.

The edited entry card and a separate trim notification share a deterministic action
ID based on source channel, entry cycle, exact contract, action, fraction, and reported
exit price. That ID is persisted atomically as the alert's primary identity before
requesting execution. Duplicate deliveries, simultaneous requests, and restarts
cannot submit that same action twice. A later entry cycle has a new identity.

An action already handed to execution is not automatically retried from duplicate
Discord notifications, including after an uncertain failure. Inspect its persisted
alert/trade and broker outcome before retrying. Duplicate suppression does not prove
a fill. Existing fill monitors, exit reservations, and broker reconciliation still
own execution outcomes. Two genuinely separate equal-fraction/equal-price trims
within one entry cycle are conservatively treated as one action.

## Link Listen Only

Listen Only is eligible for direct Echo API forwarding and local helper capture,
but never creates a Discord repost, even when the same source also appears in
Listen or a helper mapping. Existing queued reposts from that source are suppressed.
No Post channel is required. Normal Listen/Post routing is unchanged.

The Echo Bridge target must be enabled and include the source channel in its target
channel list (or already allow all sources). Echo's source override, author/channel
policy, auto-trading, sell-listening, and actionable-edit controls remain in force.
Simply receiving a card is not a bypass of those settings.

Reload Sentinel Link and refresh its Discord tabs, restart the local helper if it
predates Listen Only capture support, and restart Echo to activate the backend code.
Do not enable historical forwarding as a deployment test. Freshness checks remain:
edits still carrying an old original message timestamp can be rejected as stale;
the corresponding fresh standalone update is independently eligible.

## Verification

Automated tests cover parser classification, expiration validation, ignored comments,
ambiguous cards/positions, source isolation, stable execution identity across SQLite
restarts and concurrent requests, both edit/update delivery orders, complete bridge
ingestion with mocked execution, and Link direct forwarding without reposts. No
broker orders or Discord posts are created by these tests. Profitability is not
established by parsing tests.
