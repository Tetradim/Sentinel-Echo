export type TradeFilter = 'all' | 'open' | 'closed' | 'attention' | 'simulated';

export type TradeDigestTone = 'live' | 'attention' | 'empty';

export interface DigestTrade {
  id: string;
  ticker?: string | null;
  quantity?: number | null;
  status?: string | null;
  simulated?: boolean | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
}

export interface TradeDigestStatus {
  title: string;
  detail: string;
  tone: TradeDigestTone;
}

export interface TradeDigest {
  total: number;
  open: number;
  closed: number;
  failed: number;
  simulated: number;
  attention: number;
  netPnl: number;
  openQuantity: number;
  bestTicker: string | null;
  worstTicker: string | null;
  primaryStatus: TradeDigestStatus;
}

function isOpenTrade(trade: DigestTrade): boolean {
  return trade.status !== 'closed' && trade.status !== 'failed';
}

function isClosedTrade(trade: DigestTrade): boolean {
  return trade.status === 'closed' || trade.status === 'failed';
}

function tradePnl(trade: DigestTrade): number {
  return Number(trade.realized_pnl ?? trade.unrealized_pnl ?? 0);
}

function normalizeTicker(ticker?: string | null): string | null {
  const value = String(ticker || '').trim().toUpperCase().replace(/^\$/, '');
  return value || null;
}

function needsAttention(trade: DigestTrade): boolean {
  return trade.status === 'failed' || (isOpenTrade(trade) && tradePnl(trade) < 0);
}

function getExtremeTicker(
  trades: DigestTrade[],
  compare: (candidate: number, current: number) => boolean
): string | null {
  let chosen: DigestTrade | null = null;

  for (const trade of trades) {
    if (!normalizeTicker(trade.ticker)) continue;
    if (!chosen || compare(tradePnl(trade), tradePnl(chosen))) {
      chosen = trade;
    }
  }

  return chosen ? normalizeTicker(chosen.ticker) : null;
}

function primaryStatus(total: number, attention: number, open: number): TradeDigestStatus {
  if (total === 0) {
    return {
      title: 'No Trades',
      detail: 'No trade history is available in this view.',
      tone: 'empty',
    };
  }

  if (attention > 0) {
    return {
      title: 'Needs Review',
      detail: `${attention} trade${attention === 1 ? '' : 's'} need operator attention.`,
      tone: 'attention',
    };
  }

  return {
    title: open > 0 ? 'Open Flow' : 'Settled',
    detail: open > 0 ? `${open} open trade${open === 1 ? '' : 's'} are being tracked.` : 'All trades are closed or settled.',
    tone: 'live',
  };
}

export function summarizeTrades(trades: DigestTrade[]): TradeDigest {
  const openTrades = trades.filter(isOpenTrade);
  const failedTrades = trades.filter((trade) => trade.status === 'failed');
  const attentionTrades = trades.filter(needsAttention);
  const netPnl = trades.reduce((total, trade) => total + tradePnl(trade), 0);

  return {
    total: trades.length,
    open: openTrades.length,
    closed: trades.filter((trade) => trade.status === 'closed').length,
    failed: failedTrades.length,
    simulated: trades.filter((trade) => Boolean(trade.simulated)).length,
    attention: attentionTrades.length,
    netPnl,
    openQuantity: openTrades.reduce((total, trade) => total + Number(trade.quantity ?? 0), 0),
    bestTicker: getExtremeTicker(trades, (candidate, current) => candidate > current),
    worstTicker: getExtremeTicker(trades, (candidate, current) => candidate < current),
    primaryStatus: primaryStatus(trades.length, attentionTrades.length, openTrades.length),
  };
}

export function filterTrades<TTrade extends DigestTrade>(
  trades: TTrade[],
  filter: TradeFilter
): TTrade[] {
  if (filter === 'open') return trades.filter(isOpenTrade);
  if (filter === 'closed') return trades.filter(isClosedTrade);
  if (filter === 'attention') return trades.filter(needsAttention);
  if (filter === 'simulated') return trades.filter((trade) => Boolean(trade.simulated));
  return trades;
}
