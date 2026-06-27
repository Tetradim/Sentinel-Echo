import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export interface SettingsViewFlagsInput {
  auto_trading_enabled?: BooleanLike;
  simulation_mode?: BooleanLike;
  premium_buffer_enabled?: BooleanLike;
  averaging_down_enabled?: BooleanLike;
  take_profit_enabled?: BooleanLike;
  bracket_order_enabled?: BooleanLike;
  stop_loss_enabled?: BooleanLike;
  trailing_stop_enabled?: BooleanLike;
  sell_alert_listening_enabled?: BooleanLike;
  auto_shutdown_enabled?: BooleanLike;
  sms_enabled?: BooleanLike;
}

export interface SettingsViewFlags {
  autoTradingEnabled: boolean;
  simulationMode: boolean;
  premiumBufferEnabled: boolean;
  averagingDownEnabled: boolean;
  takeProfitEnabled: boolean;
  bracketOrderEnabled: boolean;
  stopLossEnabled: boolean;
  trailingStopEnabled: boolean;
  sellAlertListeningEnabled: boolean;
  autoShutdownEnabled: boolean;
  smsEnabled: boolean;
}

export function parseSettingsViewFlags(settings?: SettingsViewFlagsInput | null): SettingsViewFlags {
  const source = settings || {};
  return {
    autoTradingEnabled: parseBooleanFlag(source.auto_trading_enabled),
    simulationMode: parseBooleanFlag(source.simulation_mode),
    premiumBufferEnabled: parseBooleanFlag(source.premium_buffer_enabled),
    averagingDownEnabled: parseBooleanFlag(source.averaging_down_enabled),
    takeProfitEnabled: parseBooleanFlag(source.take_profit_enabled),
    bracketOrderEnabled: parseBooleanFlag(source.bracket_order_enabled),
    stopLossEnabled: parseBooleanFlag(source.stop_loss_enabled),
    trailingStopEnabled: parseBooleanFlag(source.trailing_stop_enabled),
    sellAlertListeningEnabled: parseBooleanFlag(source.sell_alert_listening_enabled),
    autoShutdownEnabled: parseBooleanFlag(source.auto_shutdown_enabled),
    smsEnabled: parseBooleanFlag(source.sms_enabled),
  };
}
