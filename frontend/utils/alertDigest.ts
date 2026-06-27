import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export type AlertFilter = 'all' | 'executed' | 'review' | 'skipped' | 'unparsed' | 'exits';

export type AlertDigestTone = 'live' | 'attention' | 'empty';

export interface DigestAlert {
  id: string;
  ticker?: string | null;
  processed?: BooleanLike;
  trade_executed?: BooleanLike;
  alert_type?: string | null;
  sell_percentage?: number | string | null;
  trade_result?: string | null;
  skip_reason?: string | null;
  trade_request_reason?: string | null;
  exit_trigger?: string | null;
  source_name?: string | null;
  source_label?: string | null;
  author_name?: string | null;
  channel_name?: string | null;
  received_at?: string | null;
}

export interface AlertDigestStatus {
  title: string;
  detail: string;
  tone: AlertDigestTone;
}

export interface AlertDigest {
  total: number;
  executed: number;
  needsReview: number;
  skipped: number;
  unparsed: number;
  exits: number;
  executionRate: number;
  topTicker: string | null;
  primaryStatus: AlertDigestStatus;
}

export type AlertExecutionStatusKey = 'executed' | 'review' | 'skipped' | 'unparsed';

export interface AlertExecutionStatus {
  key: AlertExecutionStatusKey;
  label: string;
  color: string;
  backgroundColor: string;
}

function normalizeTicker(ticker?: string | null): string | null {
  const value = String(ticker || '').trim().toUpperCase().replace(/^\$/, '');
  return value || null;
}

function cleanText(value?: string | number | null): string {
  return String(value ?? '').trim();
}

function hasSkipReason(alert: DigestAlert): boolean {
  return cleanText(alert.skip_reason).length > 0;
}

function alertType(alert: DigestAlert): string {
  return cleanText(alert.alert_type).toLowerCase();
}

function isExitAlert(alert: DigestAlert): boolean {
  return ['sell', 'trim', 'close'].includes(alertType(alert)) || cleanText(alert.exit_trigger).length > 0;
}

function formatPercent(value?: string | number | null): string | null {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  return `${Number.isInteger(numeric) ? numeric : numeric.toFixed(1)}%`;
}

function titleize(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getTopTicker(alerts: DigestAlert[]): string | null {
  const counts = new Map<string, number>();

  alerts.forEach((alert) => {
    const ticker = normalizeTicker(alert.ticker);
    if (!ticker) return;
    counts.set(ticker, (counts.get(ticker) || 0) + 1);
  });

  const [top] = [...counts.entries()].sort((left, right) => {
    const countDelta = right[1] - left[1];
    return countDelta || left[0].localeCompare(right[0]);
  });

  return top?.[0] || null;
}

function getPrimaryStatus(total: number, needsReview: number, unparsed: number): AlertDigestStatus {
  if (total === 0) {
    return {
      title: 'Listening',
      detail: 'No Discord alerts have arrived in this view.',
      tone: 'empty',
    };
  }

  if (unparsed > 0) {
    return {
      title: 'Parser Review',
      detail: `${unparsed} alert${unparsed === 1 ? '' : 's'} need parser attention.`,
      tone: 'attention',
    };
  }

  if (needsReview > 0) {
    return {
      title: 'Execution Review',
      detail: `${needsReview} alert${needsReview === 1 ? '' : 's'} did not execute.`,
      tone: 'attention',
    };
  }

  return {
    title: 'Flow Clean',
    detail: 'Every alert in this view executed successfully.',
    tone: 'live',
  };
}

export function summarizeAlerts(alerts: DigestAlert[]): AlertDigest {
  const total = alerts.length;
  const executed = alerts.filter((alert) => parseBooleanFlag(alert.trade_executed)).length;
  const unparsed = alerts.filter((alert) => !parseBooleanFlag(alert.processed)).length;
  const skipped = alerts.filter((alert) => parseBooleanFlag(alert.processed) && hasSkipReason(alert)).length;
  const exits = alerts.filter(isExitAlert).length;
  const needsReview = alerts.filter((alert) => !parseBooleanFlag(alert.trade_executed)).length;
  const executionRate = total === 0 ? 0 : Math.round((executed / total) * 100);

  return {
    total,
    executed,
    needsReview,
    skipped,
    unparsed,
    exits,
    executionRate,
    topTicker: getTopTicker(alerts),
    primaryStatus: getPrimaryStatus(total, needsReview, unparsed),
  };
}

export function filterAlerts<TAlert extends DigestAlert>(
  alerts: TAlert[],
  filter: AlertFilter
): TAlert[] {
  if (filter === 'executed') return alerts.filter((alert) => parseBooleanFlag(alert.trade_executed));
  if (filter === 'review') return alerts.filter((alert) => !parseBooleanFlag(alert.trade_executed));
  if (filter === 'skipped') return alerts.filter((alert) => parseBooleanFlag(alert.processed) && hasSkipReason(alert));
  if (filter === 'unparsed') return alerts.filter((alert) => !parseBooleanFlag(alert.processed));
  if (filter === 'exits') return alerts.filter(isExitAlert);
  return alerts;
}

export function getAlertExecutionStatus(alert: DigestAlert): AlertExecutionStatus {
  if (parseBooleanFlag(alert.trade_executed)) {
    return {
      key: 'executed',
      label: 'Executed',
      color: '#22c55e',
      backgroundColor: '#14532d',
    };
  }

  if (!parseBooleanFlag(alert.processed)) {
    return {
      key: 'unparsed',
      label: 'Unparsed',
      color: '#ef4444',
      backgroundColor: '#2d1515',
    };
  }

  if (hasSkipReason(alert)) {
    return {
      key: 'skipped',
      label: 'Skipped',
      color: '#f59e0b',
      backgroundColor: '#422006',
    };
  }

  if (parseBooleanFlag(alert.processed)) {
    return {
      key: 'review',
      label: 'Review',
      color: '#f59e0b',
      backgroundColor: '#422006',
    };
  }

  return {
    key: 'unparsed',
    label: 'Unparsed',
    color: '#ef4444',
    backgroundColor: '#2d1515',
  };
}

export function getAlertSourceSummary(alert: DigestAlert): string {
  const source = cleanText(alert.source_label) || cleanText(alert.source_name) || (
    cleanText(alert.channel_name) ? `#${cleanText(alert.channel_name)}` : ''
  );
  const author = cleanText(alert.author_name);
  if (source && author) return `${source} / ${author}`;
  return source || author || 'Unknown source';
}

export function getAlertReasonLabel(alert: DigestAlert): string {
  return cleanText(alert.skip_reason) || cleanText(alert.trade_result) || cleanText(alert.trade_request_reason);
}

export function getAlertActionSummary(alert: DigestAlert): string {
  const type = alertType(alert);
  const pct = formatPercent(alert.sell_percentage);
  if (type === 'buy') return 'Entry';
  if (type === 'average_down') return 'Avg Down';
  if (type === 'sell') return pct ? `Exit ${pct}` : 'Exit';
  if (type === 'trim') return pct ? `Trim ${pct}` : 'Trim';
  if (type === 'close') return pct ? `Close ${pct}` : 'Close';
  if (type === 'unparsed') return 'Unparsed';
  return titleize(type || 'Alert');
}

export function getExitTriggerLabel(alert: DigestAlert): string {
  const trigger = cleanText(alert.exit_trigger).toLowerCase();
  const labels: Record<string, string> = {
    sell_alert: 'Sell alert',
    trailing_stop: 'Trailing stop',
    support_resistance: 'S/R',
    sr: 'S/R',
    operator_sell: 'Operator sell',
    operator_exit: 'Operator sell',
    stop_loss: 'Stop loss',
    take_profit: 'Take profit',
    bracket_order: 'Bracket order',
  };
  return labels[trigger] || (trigger ? titleize(trigger) : '');
}
