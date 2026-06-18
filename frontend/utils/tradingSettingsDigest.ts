export type TradingSettingsDigestTone = 'live' | 'attention' | 'idle';

export interface DigestTradingSettings {
  simulationMode?: boolean | null;
  autoTradingEnabled?: boolean | null;
  priceBufferEnabled?: boolean | null;
  priceBufferPercentage?: number | null;
  orderTimeout?: number | null;
  retryFilledCheck?: boolean | null;
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

export function summarizeTradingSettings(settings: DigestTradingSettings): TradingSettingsDigest {
  const brokerConfigured = hasText(settings.brokerAccountId) && hasText(settings.brokerGatewayUrl);
  const safeguardChecks = [
    Boolean(settings.simulationMode),
    Boolean(settings.priceBufferEnabled),
    Boolean(settings.retryFilledCheck),
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
  if (!settings.priceBufferEnabled) {
    executionWarnings.push({ title: 'Price buffer disabled', detail: 'Alert prices will be sent without a margin.' });
  }
  if (!settings.retryFilledCheck) {
    executionWarnings.push({ title: 'Fill retry disabled', detail: 'Filled status checks will not retry after timeout.' });
  }
  if (String(settings.orderType || '').toUpperCase() === 'MARKET') {
    executionWarnings.push({ title: 'Market orders enabled', detail: 'Market execution can slip during fast moves.' });
  }

  const liveWarnings: TradingSettingsDigestWarning[] = [];
  if (!settings.simulationMode && settings.autoTradingEnabled) {
    liveWarnings.push({ title: 'Live auto trading', detail: 'Real orders can be placed automatically.' });
  }

  let primaryStatus: TradingSettingsDigestStatus;
  if (!settings.autoTradingEnabled) {
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
      title: settings.simulationMode ? 'Sim Auto-Ready' : 'Live Auto-Armed',
      detail: settings.simulationMode
        ? 'Automated alerts are routed to simulated execution.'
        : 'Automated alerts can place live broker orders.',
      tone: settings.simulationMode ? 'live' : 'attention',
    };
  }

  return {
    primaryStatus,
    warningItems: [...brokerWarnings, ...executionWarnings, ...liveWarnings],
    safeguardCount,
    safeguardCoveragePercent,
    modeLabel: settings.simulationMode ? 'Simulation' : 'Live',
    brokerLabel: normalizeBrokerLabel(settings.activeBroker),
    bufferLabel: settings.priceBufferEnabled ? formatPercent(toNumber(settings.priceBufferPercentage)) : 'Off',
    timeoutLabel: `${toNumber(settings.orderTimeout)}s`,
  };
}
