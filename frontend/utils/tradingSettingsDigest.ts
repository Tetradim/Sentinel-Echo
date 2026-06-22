export type TradingSettingsDigestTone = 'live' | 'attention' | 'idle';

type BooleanLike = boolean | string | number | null | undefined;

export interface DigestTradingSettings {
  simulationMode?: BooleanLike;
  autoTradingEnabled?: BooleanLike;
  priceBufferEnabled?: BooleanLike;
  priceBufferPercentage?: number | null;
  orderTimeout?: number | null;
  retryFilledCheck?: BooleanLike;
  activeBroker?: string | null;
  brokerGatewayUrl?: string | null;
  brokerAccountId?: string | null;
  orderType?: string | null;
}

export interface TradingSettingsDigestStatus {
  title: string;
  detail: string;
  tone: TradingSettingsDigestTone;
}

export interface TradingSettingsDigestWarning {
  title: string;
  detail: string;
}

export interface TradingSettingsDigest {
  primaryStatus: TradingSettingsDigestStatus;
  warningItems: TradingSettingsDigestWarning[];
  safeguardCount: number;
  safeguardCoveragePercent: number;
  modeLabel: string;
  brokerLabel: string;
  bufferLabel: string;
  timeoutLabel: string;
}

const TOTAL_SAFEGUARDS = 5;

function toNumber(value: number | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function hasText(value: string | null | undefined): boolean {
  return String(value || '').trim().length > 0;
}

function formatPercent(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

function normalizeBrokerLabel(value: string | null | undefined): string {
  const broker = String(value || '').trim();
  return broker ? broker.toUpperCase() : 'None';
}

function parseBooleanFlag(value: BooleanLike, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (value === 1) return true;
    if (value === 0) return false;
    return fallback;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false;
  }
  return fallback;
}

export function summarizeTradingSettings(settings: DigestTradingSettings): TradingSettingsDigest {
  const brokerConfigured = hasText(settings.brokerAccountId) && hasText(settings.brokerGatewayUrl);
  const simulationMode = parseBooleanFlag(settings.simulationMode);
  const autoTradingEnabled = parseBooleanFlag(settings.autoTradingEnabled);
  const priceBufferEnabled = parseBooleanFlag(settings.priceBufferEnabled);
  const retryFilledCheck = parseBooleanFlag(settings.retryFilledCheck);
  const safeguardChecks = [
    simulationMode,
    priceBufferEnabled,
    retryFilledCheck,
    String(settings.orderType || '').toUpperCase() === 'LIMIT',
    brokerConfigured,
  ];
  const safeguardCount = safeguardChecks.filter(Boolean).length;
  const safeguardCoveragePercent = Math.round((safeguardCount / TOTAL_SAFEGUARDS) * 100);

  const brokerWarnings: TradingSettingsDigestWarning[] = [];
  if (!hasText(settings.brokerAccountId)) {
    brokerWarnings.push({ title: 'Broker account missing', detail: 'Add an account ID before trusting automation.' });
  }
  if (!hasText(settings.brokerGatewayUrl)) {
    brokerWarnings.push({ title: 'Gateway URL missing', detail: 'Execution cannot confirm the broker endpoint.' });
  }

  const executionWarnings: TradingSettingsDigestWarning[] = [];
  if (!priceBufferEnabled) {
    executionWarnings.push({ title: 'Price buffer disabled', detail: 'Alert prices will be sent without a margin.' });
  }
  if (!retryFilledCheck) {
    executionWarnings.push({ title: 'Fill retry disabled', detail: 'Filled status checks will not retry after timeout.' });
  }
  if (String(settings.orderType || '').toUpperCase() === 'MARKET') {
    executionWarnings.push({ title: 'Market orders enabled', detail: 'Market execution can slip during fast moves.' });
  }

  const liveWarnings: TradingSettingsDigestWarning[] = [];
  if (!simulationMode && autoTradingEnabled) {
    liveWarnings.push({ title: 'Live auto trading', detail: 'Real orders can be placed automatically.' });
  }

  let primaryStatus: TradingSettingsDigestStatus;
  if (!autoTradingEnabled) {
    primaryStatus = {
      title: 'Manual Mode',
      detail: 'Alerts require operator approval before execution.',
      tone: 'idle',
    };
  } else if (brokerWarnings.length > 0) {
    primaryStatus = {
      title: 'Broker Setup',
      detail: `${brokerWarnings.length} broker field${brokerWarnings.length === 1 ? '' : 's'} need attention.`,
      tone: 'attention',
    };
  } else if (executionWarnings.length > 0) {
    primaryStatus = {
      title: 'Execution Review',
      detail: `${executionWarnings.length} execution safeguard${executionWarnings.length === 1 ? '' : 's'} are relaxed.`,
      tone: 'attention',
    };
  } else {
    primaryStatus = {
      title: simulationMode ? 'Sim Auto-Ready' : 'Live Auto-Armed',
      detail: simulationMode
        ? 'Automated alerts are routed to simulated execution.'
        : 'Automated alerts can place live broker orders.',
      tone: simulationMode ? 'live' : 'attention',
    };
  }

  return {
    primaryStatus,
    warningItems: [...brokerWarnings, ...executionWarnings, ...liveWarnings],
    safeguardCount,
    safeguardCoveragePercent,
    modeLabel: simulationMode ? 'Simulation' : 'Live',
    brokerLabel: normalizeBrokerLabel(settings.activeBroker),
    bufferLabel: priceBufferEnabled ? formatPercent(toNumber(settings.priceBufferPercentage)) : 'Off',
    timeoutLabel: `${toNumber(settings.orderTimeout)}s`,
  };
}
