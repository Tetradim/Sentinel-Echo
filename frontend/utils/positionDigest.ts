export type PositionFilter = 'open' | 'all' | 'closed' | 'attention';

export type PositionDigestTone = 'live' | 'attention' | 'empty';

export interface DigestPosition {
  id: string;
  ticker?: string | null;
  status?: string | null;
  expiration?: string | null;
  entry_price?: number | null;
  remaining_quantity?: number | null;
  total_cost?: number | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
}

export interface PositionDigestStatus {
  title: string;
  detail: string;
  tone: PositionDigestTone;
}

export interface PositionDigest {
  total: number;
  open: number;
  closed: number;
  partial: number;
  losingOpen: number;
  expiringSoon: number;
  totalUnrealized: number;
  totalRealized: number;
  openExposure: number;
  topExposureTicker: string | null;
  primaryStatus: PositionDigestStatus;
}

function isOpenPosition(position: DigestPosition): boolean {
  return position.status === 'open' || position.status === 'partial';
}

function positionExposure(position: DigestPosition): number {
  if (!isOpenPosition(position)) return 0;
  const totalCost = Number(position.total_cost ?? 0);
  if (totalCost > 0) return totalCost;
  return Number(position.entry_price ?? 0) * Number(position.remaining_quantity ?? 0) * 100;
}

function normalizeTicker(ticker?: string | null): string | null {
  const value = String(ticker || '').trim().toUpperCase().replace(/^\$/, '');
  return value || null;
}

function daysUntilExpiration(position: DigestPosition, now: Date): number | null {
  if (!position.expiration) return null;
  const expiry = new Date(`${position.expiration}T21:00:00Z`);
  if (Number.isNaN(expiry.getTime())) return null;
  return Math.ceil((expiry.getTime() - now.getTime()) / 86_400_000);
}

function isExpiringSoon(position: DigestPosition, now: Date): boolean {
  const days = daysUntilExpiration(position, now);
  return isOpenPosition(position) && days !== null && days <= 7;
}

function isLosingOpen(position: DigestPosition): boolean {
  return isOpenPosition(position) && Number(position.unrealized_pnl ?? 0) < 0;
}

function needsAttention(position: DigestPosition, now: Date): boolean {
  return isLosingOpen(position) || isExpiringSoon(position, now);
}

function topExposureTicker(openPositions: DigestPosition[]): string | null {
  let chosen: DigestPosition | null = null;

  for (const position of openPositions) {
    if (!normalizeTicker(position.ticker)) continue;
    if (!chosen || positionExposure(position) > positionExposure(chosen)) {
      chosen = position;
    }
  }

  return chosen ? normalizeTicker(chosen.ticker) : null;
}

function primaryStatus(
  total: number,
  expiringSoon: number,
  losingOpen: number,
  open: number
): PositionDigestStatus {
  if (total === 0) {
    return {
      title: 'Flat',
      detail: 'No positions are currently loaded.',
      tone: 'empty',
    };
  }

  if (expiringSoon > 0) {
    return {
      title: 'Expiry Watch',
      detail: `${expiringSoon} open position${expiringSoon === 1 ? '' : 's'} are expired or within 7 days.`,
      tone: 'attention',
    };
  }

  if (losingOpen > 0) {
    return {
      title: 'Loss Watch',
      detail: `${losingOpen} open position${losingOpen === 1 ? '' : 's'} are below entry.`,
      tone: 'attention',
    };
  }

  return {
    title: open > 0 ? 'Open Exposure' : 'Settled',
    detail: open > 0 ? `${open} open position${open === 1 ? '' : 's'} are being tracked.` : 'All loaded positions are closed.',
    tone: 'live',
  };
}

export function summarizePositions(
  positions: DigestPosition[],
  nowInput: string | Date = new Date()
): PositionDigest {
  const now = nowInput instanceof Date ? nowInput : new Date(nowInput);
  const openPositions = positions.filter(isOpenPosition);
  const expiringSoon = positions.filter((position) => isExpiringSoon(position, now)).length;
  const losingOpen = positions.filter(isLosingOpen).length;

  return {
    total: positions.length,
    open: openPositions.length,
    closed: positions.filter((position) => position.status === 'closed').length,
    partial: positions.filter((position) => position.status === 'partial').length,
    losingOpen,
    expiringSoon,
    totalUnrealized: openPositions.reduce((total, position) => total + Number(position.unrealized_pnl ?? 0), 0),
    totalRealized: positions.reduce((total, position) => total + Number(position.realized_pnl ?? 0), 0),
    openExposure: openPositions.reduce((total, position) => total + positionExposure(position), 0),
    topExposureTicker: topExposureTicker(openPositions),
    primaryStatus: primaryStatus(positions.length, expiringSoon, losingOpen, openPositions.length),
  };
}

export function filterPositions<TPosition extends DigestPosition>(
  positions: TPosition[],
  filter: PositionFilter,
  nowInput: string | Date = new Date()
): TPosition[] {
  const now = nowInput instanceof Date ? nowInput : new Date(nowInput);
  if (filter === 'open') return positions.filter(isOpenPosition);
  if (filter === 'closed') return positions.filter((position) => position.status === 'closed');
  if (filter === 'attention') return positions.filter((position) => needsAttention(position, now));
  return positions;
}
