import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export interface ProfileBrokerFlagsInput {
  enabled?: BooleanLike;
  auto_trading_enabled?: BooleanLike;
  alerts_only?: BooleanLike;
  premium_buffer_enabled?: BooleanLike;
  take_profit_enabled?: BooleanLike;
  bracket_order_enabled?: BooleanLike;
  stop_loss_enabled?: BooleanLike;
  trailing_stop_enabled?: BooleanLike;
  averaging_down_enabled?: BooleanLike;
  auto_shutdown_enabled?: BooleanLike;
}

export interface ProfileBrokerFlags {
  enabled: boolean;
  autoTradingEnabled: boolean;
  alertsOnly: boolean;
  premiumBufferEnabled: boolean;
  takeProfitEnabled: boolean;
  bracketOrderEnabled: boolean;
  stopLossEnabled: boolean;
  trailingStopEnabled: boolean;
  averagingDownEnabled: boolean;
  autoShutdownEnabled: boolean;
}

export function parseProfileBrokerFlags(settings?: ProfileBrokerFlagsInput | null): ProfileBrokerFlags {
  const source = settings || {};
  return {
    enabled: parseBooleanFlag(source.enabled),
    autoTradingEnabled: parseBooleanFlag(source.auto_trading_enabled),
    alertsOnly: parseBooleanFlag(source.alerts_only),
    premiumBufferEnabled: parseBooleanFlag(source.premium_buffer_enabled),
    takeProfitEnabled: parseBooleanFlag(source.take_profit_enabled),
    bracketOrderEnabled: parseBooleanFlag(source.bracket_order_enabled),
    stopLossEnabled: parseBooleanFlag(source.stop_loss_enabled),
    trailingStopEnabled: parseBooleanFlag(source.trailing_stop_enabled),
    averagingDownEnabled: parseBooleanFlag(source.averaging_down_enabled),
    autoShutdownEnabled: parseBooleanFlag(source.auto_shutdown_enabled),
  };
}

export function getProfileBrokerSummary(settings?: ProfileBrokerFlagsInput | null): string | null {
  const flags = parseProfileBrokerFlags(settings);
  if (!flags.enabled) return null;

  const features: string[] = [];
  if (flags.alertsOnly) features.push('Alerts Only');
  else if (flags.autoTradingEnabled) features.push('Auto');
  if (flags.bracketOrderEnabled) features.push('Bracket');
  if (flags.trailingStopEnabled) features.push('Trail');
  if (flags.takeProfitEnabled) features.push('TP');
  if (flags.stopLossEnabled) features.push('SL');
  return features.length > 0 ? features.join(' • ') : 'Enabled';
}
