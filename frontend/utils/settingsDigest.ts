export type SettingsDigestTone = 'live' | 'attention' | 'idle';

export interface DigestSettings {
  discord_token?: string | null;
  discord_channel_ids?: string[] | null;
  active_broker?: string | null;
  auto_trading_enabled?: boolean | null;
  simulation_mode?: boolean | null;
  take_profit_enabled?: boolean | null;
  stop_loss_enabled?: boolean | null;
  trailing_stop_enabled?: boolean | null;
  auto_shutdown_enabled?: boolean | null;
  premium_buffer_enabled?: boolean | null;
  sms_enabled?: boolean | null;
  sms_phone_number?: string | null;
}

export interface DigestAlertPatterns {
  buy_patterns?: string[] | null;
  sell_patterns?: string[] | null;
  partial_sell_patterns?: string[] | null;
  average_down_patterns?: string[] | null;
  stop_loss_patterns?: string[] | null;
  take_profit_patterns?: string[] | null;
  ignore_patterns?: string[] | null;
}

export interface SettingsDigestStatus {
  title: string;
  detail: string;
  tone: SettingsDigestTone;
}

export interface SettingsDigestWarning {
  title: string;
  detail: string;
}

export interface SettingsDigest {
  primaryStatus: SettingsDigestStatus;
  warningItems: SettingsDigestWarning[];
  guardrailCount: number;
  guardrailCoveragePercent: number;
  channelLabel: string;
  parserLabel: string;
  modeLabel: string;
  brokerLabel: string;
  notificationLabel: string;
}

const TOTAL_GUARDRAILS = 6;

function hasText(value: string | null | undefined): boolean {
  return String(value || '').trim().length > 0;
}

function patternCount(patterns: DigestAlertPatterns | null | undefined): number {
  if (!patterns) return 0;
  return [
    patterns.buy_patterns,
    patterns.sell_patterns,
    patterns.partial_sell_patterns,
    patterns.average_down_patterns,
    patterns.stop_loss_patterns,
    patterns.take_profit_patterns,
    patterns.ignore_patterns,
  ].reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0);
}

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function normalizeBroker(value: string | null | undefined): string {
  const broker = String(value || '').trim();
  return broker ? broker.toUpperCase() : 'None';
}

export function summarizeSettings(
  settings: DigestSettings,
  patterns: DigestAlertPatterns | null | undefined
): SettingsDigest {
  const channelCount = Array.isArray(settings.discord_channel_ids)
    ? settings.discord_channel_ids.filter((channel) => hasText(channel)).length
    : 0;
  const parserPatterns = patternCount(patterns);
  const hasIgnorePatterns = Boolean(patterns?.ignore_patterns?.length);

  const discordWarnings: SettingsDigestWarning[] = [];
  if (!hasText(settings.discord_token)) {
    discordWarnings.push({
      title: 'Discord token missing',
      detail: 'Add a bot token before the listener can connect.',
    });
  }
  if (channelCount === 0) {
    discordWarnings.push({
      title: 'Discord channels empty',
      detail: 'Add at least one channel ID for alert ingestion.',
    });
  }

  const patternWarnings: SettingsDigestWarning[] = [];
  if (!patterns?.buy_patterns?.length) {
    patternWarnings.push({ title: 'Buy patterns empty', detail: 'Entry alerts need buy-side keywords.' });
  }
  if (!patterns?.sell_patterns?.length) {
    patternWarnings.push({ title: 'Sell patterns empty', detail: 'Exit alerts need sell-side keywords.' });
  }
  if (!hasIgnorePatterns) {
    patternWarnings.push({ title: 'Ignore patterns empty', detail: 'Watchlist and paper-only alerts will not be filtered.' });
  }

  const guardrailWarnings: SettingsDigestWarning[] = [];
  if (!settings.stop_loss_enabled) {
    guardrailWarnings.push({ title: 'Stop loss disabled', detail: 'Positions do not have a fixed downside exit.' });
  }
  if (!settings.take_profit_enabled) {
    guardrailWarnings.push({ title: 'Take profit disabled', detail: 'Winning positions do not have a default profit target.' });
  }
  if (!settings.auto_shutdown_enabled) {
    guardrailWarnings.push({ title: 'Auto shutdown disabled', detail: 'Daily loss guardrails will not stop new entries.' });
  }
  if (!settings.premium_buffer_enabled) {
    guardrailWarnings.push({ title: 'Premium buffer disabled', detail: 'Alert prices can be submitted without a limit margin.' });
  }

  const liveWarnings: SettingsDigestWarning[] = [];
  if (settings.auto_trading_enabled && !settings.simulation_mode) {
    liveWarnings.push({ title: 'Live auto trading', detail: 'Real broker orders can be placed automatically.' });
  }

  const guardrailChecks = [
    Boolean(settings.simulation_mode),
    Boolean(settings.stop_loss_enabled),
    Boolean(settings.take_profit_enabled),
    Boolean(settings.auto_shutdown_enabled),
    Boolean(settings.premium_buffer_enabled),
    hasIgnorePatterns,
  ];
  const guardrailCount = guardrailChecks.filter(Boolean).length;
  const guardrailCoveragePercent = Math.round((guardrailCount / TOTAL_GUARDRAILS) * 100);

  let primaryStatus: SettingsDigestStatus;
  if (discordWarnings.length > 0) {
    primaryStatus = {
      title: 'Discord Setup',
      detail: `${discordWarnings.length} Discord field${discordWarnings.length === 1 ? '' : 's'} need attention.`,
      tone: 'attention',
    };
  } else if (liveWarnings.length > 0) {
    primaryStatus = {
      title: 'Live Auto Review',
      detail: 'Automation can reach the broker without simulation.',
      tone: 'attention',
    };
  } else if (patternWarnings.length > 0) {
    primaryStatus = {
      title: 'Pattern Review',
      detail: `${patternWarnings.length} parser safeguard${patternWarnings.length === 1 ? '' : 's'} need coverage.`,
      tone: 'attention',
    };
  } else if (guardrailWarnings.length > 0) {
    primaryStatus = {
      title: 'Guardrail Review',
      detail: `${guardrailWarnings.length} risk guardrail${guardrailWarnings.length === 1 ? '' : 's'} are relaxed.`,
      tone: 'attention',
    };
  } else {
    primaryStatus = {
      title: settings.auto_trading_enabled ? 'Simulation Guarded' : 'Manual Guarded',
      detail: settings.auto_trading_enabled
        ? 'Discord alerts route to simulated execution with core safeguards on.'
        : 'Alerts require operator approval with core safeguards on.',
      tone: settings.auto_trading_enabled ? 'live' : 'idle',
    };
  }

  return {
    primaryStatus,
    warningItems: [...discordWarnings, ...patternWarnings, ...guardrailWarnings, ...liveWarnings],
    guardrailCount,
    guardrailCoveragePercent,
    channelLabel: countLabel(channelCount, 'channel', 'channels'),
    parserLabel: countLabel(parserPatterns, 'pattern', 'patterns'),
    modeLabel: settings.auto_trading_enabled
      ? (settings.simulation_mode ? 'Sim auto' : 'Live auto')
      : 'Manual',
    brokerLabel: normalizeBroker(settings.active_broker),
    notificationLabel: settings.sms_enabled && hasText(settings.sms_phone_number) ? 'SMS armed' : 'In-app only',
  };
}
