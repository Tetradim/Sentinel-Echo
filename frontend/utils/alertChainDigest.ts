export interface AlertChainReportRow {
  chain_key?: string;
  source?: string;
  event_id?: string;
  observed_at?: string;
  alert_id?: string;
  ticker?: string;
  status?: string;
  attention_reason?: string;
  decision_reason?: string;
  trade_id?: string;
  order_id?: string;
  position_id?: string;
  deterministic?: unknown;
}

export interface AlertChainReport {
  summary?: Record<string, unknown>;
  rows?: AlertChainReportRow[];
}

export interface AlertChainRowDigest {
  key: string;
  tickerLabel: string;
  status: string;
  sourceLabel: string;
  attentionReason: string;
  decisionReason: string;
  linkageLabel: string;
  deterministic: boolean;
}

export interface AlertChainDigest {
  total: number;
  attentionCount: number;
  deterministic: boolean;
  title: string;
  stateLabel: 'Idle' | 'Clear' | 'Review';
  detail: string;
  stageCounts: {
    seen: number;
    parsed: number;
    decided: number;
    placed: number;
    reconciled: number;
  };
  rows: AlertChainRowDigest[];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asRows(value: unknown): AlertChainReportRow[] {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === 'object') as AlertChainReportRow[] : [];
}

function cleanString(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function asCount(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.floor(numeric) : 0;
}

function asBool(value: unknown, defaultValue = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false;
  }
  if (typeof value === 'number') return value !== 0;
  return defaultValue;
}

function formatSource(value: unknown): string {
  const source = cleanString(value).replace(/_/g, ' ');
  return source || 'unknown source';
}

function buildRow(row: AlertChainReportRow): AlertChainRowDigest {
  const tradeId = cleanString(row.trade_id);
  const positionId = cleanString(row.position_id);
  const orderId = cleanString(row.order_id);
  const linkage = [
    tradeId ? `trade ${tradeId}` : '',
    orderId ? `order ${orderId}` : '',
    positionId ? `position ${positionId}` : '',
  ].filter(Boolean).join(' / ');

  return {
    key: cleanString(row.chain_key) || cleanString(row.alert_id) || cleanString(row.event_id) || 'alert-chain',
    tickerLabel: cleanString(row.ticker).toUpperCase() || 'Unknown',
    status: cleanString(row.status) || 'unknown',
    sourceLabel: formatSource(row.source),
    attentionReason: cleanString(row.attention_reason),
    decisionReason: cleanString(row.decision_reason),
    linkageLabel: linkage || 'no linked trade or position',
    deterministic: asBool(row.deterministic),
  };
}

export function summarizeAlertChains(report: unknown): AlertChainDigest {
  const payload = asRecord(report);
  const summary = asRecord(payload.summary);
  const rows = asRows(payload.rows).map(buildRow);
  const total = asCount(summary.total) || rows.length;
  const attentionCount = asCount(summary.attention_count) || rows.filter((row) => row.status === 'attention').length;
  const deterministic = asBool(summary.deterministic, total > 0 && rows.every((row) => row.deterministic));

  if (total === 0) {
    return {
      total: 0,
      attentionCount: 0,
      deterministic: false,
      title: 'No Alert Chains',
      stateLabel: 'Idle',
      detail: 'No alert chain proof rows are in the current report window.',
      stageCounts: { seen: 0, parsed: 0, decided: 0, placed: 0, reconciled: 0 },
      rows,
    };
  }

  return {
    total,
    attentionCount,
    deterministic,
    title: attentionCount > 0 ? 'Alert Chain Review' : 'Alert Chains Deterministic',
    stateLabel: attentionCount > 0 ? 'Review' : 'Clear',
    detail: attentionCount > 0
      ? `${attentionCount} alert chain${attentionCount === 1 ? '' : 's'} need operator review.`
      : `${total} alert chain${total === 1 ? '' : 's'} fully explained in this window.`,
    stageCounts: {
      seen: asCount(summary.seen_count),
      parsed: asCount(summary.parsed_count),
      decided: asCount(summary.accepted_count),
      placed: asCount(summary.trade_requested_count),
      reconciled: asCount(summary.position_linked_count),
    },
    rows,
  };
}
