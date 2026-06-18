export type RiskDigestTone = 'live' | 'attention';

export interface DigestRiskSettings {
  maxPositionSize?: number | null;
  riskPerTrade?: number | null;
  stopLossEnabled?: boolean | null;
  takeProfitEnabled?: boolean | null;
  trailingStopEnabled?: boolean | null;
  autoShutdownEnabled?: boolean | null;
  maxPositionsPerTicker?: number | null;
  maxPositionsPerSector?: number | null;
}

export interface RiskDigestStatus {
  title: string;
  detail: string;
  tone: RiskDigestTone;
}

export interface RiskDigestWarning {
  title: string;
  detail: string;
}

export interface RiskDigest {
  enabledGuards: number;
  guardCoveragePercent: number;
  riskPerTradeLabel: string;
  maxPositionSizeLabel: string;
  primaryStatus: RiskDigestStatus;
  warningItems: RiskDigestWarning[];
}

const TOTAL_GUARDS = 6;

function toNumber(value: number | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `$${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
  }

  return `$${value}`;
}

function formatPercent(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

export function summarizeRiskSettings(settings: DigestRiskSettings): RiskDigest {
  const guardChecks = [
    Boolean(settings.stopLossEnabled),
    Boolean(settings.takeProfitEnabled),
    Boolean(settings.trailingStopEnabled),
    Boolean(settings.autoShutdownEnabled),
    toNumber(settings.maxPositionsPerTicker) > 0,
    toNumber(settings.maxPositionsPerSector) > 0,
  ];
  const enabledGuards = guardChecks.filter(Boolean).length;
  const guardCoveragePercent = Math.round((enabledGuards / TOTAL_GUARDS) * 100);
  const riskPerTrade = toNumber(settings.riskPerTrade);
  const maxPositionSize = toNumber(settings.maxPositionSize);

  const guardWarnings: RiskDigestWarning[] = [];
  if (!settings.stopLossEnabled) {
    guardWarnings.push({ title: 'Stop loss disabled', detail: 'Downside exits will need manual handling.' });
  }
  if (!settings.takeProfitEnabled) {
    guardWarnings.push({ title: 'Take profit disabled', detail: 'Winning exits are not currently staged.' });
  }
  if (!settings.trailingStopEnabled) {
    guardWarnings.push({ title: 'Trailing stop disabled', detail: 'Open winners will not tighten automatically.' });
  }
  if (!settings.autoShutdownEnabled) {
    guardWarnings.push({ title: 'Auto shutdown disabled', detail: 'Loss streak controls are not armed.' });
  }
  if (toNumber(settings.maxPositionsPerTicker) <= 0) {
    guardWarnings.push({ title: 'Ticker cap missing', detail: 'Single-name concentration is uncapped.' });
  }
  if (toNumber(settings.maxPositionsPerSector) <= 0) {
    guardWarnings.push({ title: 'Sector cap missing', detail: 'Sector concentration is uncapped.' });
  }

  const sizingWarnings: RiskDigestWarning[] = [];
  if (riskPerTrade > 2) {
    sizingWarnings.push({ title: 'Risk per trade high', detail: 'Keep this near 1-2% for routine automation.' });
  }
  if (maxPositionSize > 5000) {
    sizingWarnings.push({ title: 'Position size high', detail: 'Large single-ticket caps deserve a manual review.' });
  }

  let primaryStatus: RiskDigestStatus = {
    title: 'Guarded',
    detail: 'Core exits, shutdowns, and concentration limits are armed.',
    tone: 'live',
  };

  if (guardWarnings.length > 0) {
    primaryStatus = {
      title: 'Needs Guardrails',
      detail: `${guardWarnings.length} risk control${guardWarnings.length === 1 ? '' : 's'} need attention.`,
      tone: 'attention',
    };
  } else if (sizingWarnings.length > 0) {
    primaryStatus = {
      title: 'Sizing Review',
      detail: `${sizingWarnings.length} allocation setting${sizingWarnings.length === 1 ? '' : 's'} look aggressive.`,
      tone: 'attention',
    };
  }

  return {
    enabledGuards,
    guardCoveragePercent,
    riskPerTradeLabel: formatPercent(riskPerTrade),
    maxPositionSizeLabel: formatCompactCurrency(maxPositionSize),
    primaryStatus,
    warningItems: [...guardWarnings, ...sizingWarnings],
  };
}
