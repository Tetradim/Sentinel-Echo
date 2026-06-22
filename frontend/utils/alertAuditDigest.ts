export interface OperatorEventLike {
  id?: string;
  timestamp?: string;
  action?: string;
  summary?: string;
  severity?: string;
  details?: unknown;
}

export interface BridgeAlertDecisionRow {
  id: string;
  timestamp: string;
  status: 'accepted' | 'skipped';
  summary: string;
  skipReason: string;
  channelLabel: string;
  authorLabel: string;
  tickerLabel: string;
  parserConfidence: string;
  sourceLabel: string;
  rawTextPreview: string;
}

export interface BridgeAlertDecisionDigest {
  total: number;
  acceptedCount: number;
  skippedCount: number;
  title: string;
  stateLabel: 'Idle' | 'Clear' | 'Review';
  detail: string;
  rows: BridgeAlertDecisionRow[];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function cleanString(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = cleanString(value);
    if (text) return text;
  }
  return '';
}

function summarizeRawText(value: unknown): string {
  const text = cleanString(value).replace(/\s+/g, ' ');
  if (!text) return '';
  return text.length > 90 ? `${text.slice(0, 87)}...` : text;
}

function buildTickerLabel(parsed: Record<string, unknown>): string {
  const ticker = firstString(parsed.ticker, parsed.symbol).toUpperCase();
  const strike = firstString(parsed.strike);
  const optionType = firstString(parsed.option_type, parsed.optionType, parsed.type).toUpperCase();
  const expiration = firstString(parsed.expiration, parsed.expiry);
  const label = [ticker, strike, optionType, expiration].filter(Boolean).join(' ');
  return label || 'Unparsed';
}

function buildRow(event: OperatorEventLike): BridgeAlertDecisionRow {
  const details = asRecord(event.details);
  const channel = asRecord(details.channel);
  const author = asRecord(details.author);
  const parsed = asRecord(details.parsed);
  const parser = asRecord(details.parser);
  const source = asRecord(details.source);
  const decision = asRecord(details.decision);
  const skipReason = firstString(decision.skip_reason, decision.reason);
  const decisionStatus = firstString(decision.status).toLowerCase();
  const status = decisionStatus === 'skipped' || cleanString(event.severity).toLowerCase() === 'warning'
    ? 'skipped'
    : 'accepted';

  return {
    id: firstString(event.id, details.event_id, channel.message_url, event.timestamp) || 'bridge-alert-decision',
    timestamp: firstString(event.timestamp),
    status,
    summary: firstString(event.summary) || (status === 'skipped' ? `Skipped: ${skipReason || 'policy blocked'}` : 'Chrome bridge alert accepted.'),
    skipReason,
    channelLabel: firstString(channel.name, channel.id, channel.url, 'Unknown channel'),
    authorLabel: firstString(author.name, author.id, 'Unknown author'),
    tickerLabel: buildTickerLabel(parsed),
    parserConfidence: firstString(parser.confidence, source.min_parser_confidence, 'unknown'),
    sourceLabel: firstString(source.name, source.key, 'No source override'),
    rawTextPreview: summarizeRawText(details.raw_text),
  };
}

export function summarizeBridgeAlertDecisions(
  events: OperatorEventLike[] | null | undefined
): BridgeAlertDecisionDigest {
  const rows = (Array.isArray(events) ? events : [])
    .filter((event) => event?.action === 'bridge_alert_decision')
    .map(buildRow);
  const skippedCount = rows.filter((row) => row.status === 'skipped').length;
  const acceptedCount = rows.length - skippedCount;

  if (rows.length === 0) {
    return {
      total: 0,
      acceptedCount: 0,
      skippedCount: 0,
      title: 'No Bridge Alerts',
      stateLabel: 'Idle',
      detail: 'No Chrome bridge alert decisions are in the current event window.',
      rows,
    };
  }

  return {
    total: rows.length,
    acceptedCount,
    skippedCount,
    title: skippedCount > 0 ? 'Bridge Alerts Need Review' : 'Bridge Alerts Accepted',
    stateLabel: skippedCount > 0 ? 'Review' : 'Clear',
    detail: `${skippedCount} skipped, ${acceptedCount} accepted in current event window.`,
    rows,
  };
}
