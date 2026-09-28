# Sentinel Link Source Auto-Enrollment

## Goal

Make every Discord channel explicitly saved in Sentinel Link immediately eligible for Echo alert ingestion without requiring a second manual `source_overrides` entry.

## Contract

Sentinel Link remains the authority for whether a visible Discord channel is enrolled. For every direct bridge message it sends, Link includes `source_mode` as either `listen` or `listen-only`. Link only emits this field after the current tab matches a URL saved in the corresponding Link list.

Echo trusts that enrollment only on its authenticated, localhost-only Chrome bridge endpoint and only when `source` is `sentinel-link`, the channel ID is a numeric Discord channel ID, the channel URL is canonical, and the URL contains the same channel ID.

## Echo Behavior

On the first valid Link message from a channel without a source override, Echo creates a default enabled source policy keyed by channel ID. The policy records the exact channel URL, requires medium parser confidence, permits all supported alert actions, and preserves normal follow-up and edit processing. Existing source overrides are never replaced or weakened.

The strict source-override gate remains in place for other bridge clients and for Link payloads without valid enrollment proof. Auto-enrollment authorizes the source, not the message: unparsed, incomplete, stale, duplicate, low-confidence, or otherwise blocked messages still cannot request a trade.

## Reposting

`listen-only` changes only Link's repost behavior. Both `listen` and `listen-only` modes send actionable messages to Echo and receive identical source enrollment behavior.

## Auditability

The generated source policy identifies Sentinel Link as its manager and records the enrollment mode. Echo's existing bridge audit continues to report parser output, source policy proof, acceptance, rejection, and trade-request status.

## Verification

- Link tests prove saved Listen and Listen Only channels emit the correct `source_mode`.
- Echo tests prove a valid Link payload auto-enrolls and passes normal ingestion.
- Echo tests prove ordinary unparsed conversation remains non-actionable after enrollment.
- Echo tests prove unmarked/untrusted bridge clients still require an explicit override.
- Existing Link and Echo bridge suites remain green.
