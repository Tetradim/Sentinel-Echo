import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export type AlertFilter = 'all' | 'executed' | 'review' | 'unparsed';

export type AlertDigestTone = 'live' | 'attention' | 'empty';

export interface DigestAlert {
  id: string;
  ticker?: string | null;
  processed?: BooleanLike;
  trade_executed?: BooleanLike;
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
  unparsed: number;
  executionRate: number;
  topTicker: string | null;
  primaryStatus: AlertDigestStatus;
}

function normalizeTicker(ticker?: string | null): string | null {
  const value = String(ticker || '').trim().toUpperCase().replace(/^\$/, '');
  return value || null;
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
  const needsReview = alerts.filter((alert) => !parseBooleanFlag(alert.trade_executed)).length;
  const executionRate = total === 0 ? 0 : Math.round((executed / total) * 100);

  return {
    total,
    executed,
    needsReview,
    unparsed,
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
  if (filter === 'unparsed') return alerts.filter((alert) => !parseBooleanFlag(alert.processed));
  return alerts;
}
