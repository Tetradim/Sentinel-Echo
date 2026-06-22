import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export interface DashboardRuntimeStatusInput {
  auto_trading_enabled?: BooleanLike;
  simulation_mode?: BooleanLike;
}

export interface DashboardRuntimeSettingsInput {
  simulation_mode?: BooleanLike;
}

export interface DashboardAveragingDownInput {
  averaging_down_enabled?: BooleanLike;
}

export interface DashboardRiskInput {
  take_profit_enabled?: BooleanLike;
  stop_loss_enabled?: BooleanLike;
  take_profit_percentage?: number | string | null;
  stop_loss_percentage?: number | string | null;
}

export interface DashboardTrailingInput {
  trailing_stop_enabled?: BooleanLike;
  trailing_stop_percent?: number | string | null;
}

export interface DashboardShutdownInput {
  auto_shutdown_enabled?: BooleanLike;
  max_consecutive_losses?: number | string | null;
  max_daily_losses?: number | string | null;
  max_daily_loss_amount?: number | string | null;
  consecutive_losses?: number | string | null;
  daily_losses?: number | string | null;
  shutdown_triggered?: BooleanLike;
  shutdown_reason?: string | null;
}

export interface DashboardPremiumBufferInput {
  premium_buffer_enabled?: BooleanLike;
  premium_buffer_amount?: number | string | null;
}

export interface DashboardRuntimeStateInput {
  status?: DashboardRuntimeStatusInput | null;
  settings?: DashboardRuntimeSettingsInput | null;
  averagingDown?: DashboardAveragingDownInput | null;
  risk?: DashboardRiskInput | null;
  trailing?: DashboardTrailingInput | null;
  shutdown?: DashboardShutdownInput | null;
  premium?: DashboardPremiumBufferInput | null;
}

export interface DashboardRuntimeShutdownSettings {
  max_consecutive_losses: number;
  max_daily_losses: number;
  max_daily_loss_amount: number;
  consecutive_losses: number;
  daily_losses: number;
  shutdown_triggered: boolean;
  shutdown_reason: string;
}

export interface DashboardRuntimeState {
  autoTrading: boolean;
  simMode: boolean;
  avgDown: boolean;
  takeProfit: boolean;
  stopLoss: boolean;
  riskSettings: {
    take_profit_percentage: number;
    stop_loss_percentage: number;
  };
  trailingStop: boolean;
  trailingSettings: {
    trailing_stop_percent: number;
  };
  autoShutdown: boolean;
  shutdownSettings: DashboardRuntimeShutdownSettings;
  premiumBuffer: boolean;
  premiumBufferAmt: number;
}

function toNumber(value: number | string | null | undefined, fallback: number): number {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function normalizeDashboardRuntimeState(input: DashboardRuntimeStateInput): DashboardRuntimeState {
  const status = input.status || {};
  const settings = input.settings || {};
  const averagingDown = input.averagingDown || {};
  const risk = input.risk || {};
  const trailing = input.trailing || {};
  const shutdown = input.shutdown || {};
  const premium = input.premium || {};

  return {
    autoTrading: parseBooleanFlag(status.auto_trading_enabled),
    simMode: parseBooleanFlag(status.simulation_mode ?? settings.simulation_mode),
    avgDown: parseBooleanFlag(averagingDown.averaging_down_enabled),
    takeProfit: parseBooleanFlag(risk.take_profit_enabled),
    stopLoss: parseBooleanFlag(risk.stop_loss_enabled),
    riskSettings: {
      take_profit_percentage: toNumber(risk.take_profit_percentage, 50),
      stop_loss_percentage: toNumber(risk.stop_loss_percentage, 25),
    },
    trailingStop: parseBooleanFlag(trailing.trailing_stop_enabled),
    trailingSettings: {
      trailing_stop_percent: toNumber(trailing.trailing_stop_percent, 10),
    },
    autoShutdown: parseBooleanFlag(shutdown.auto_shutdown_enabled),
    shutdownSettings: {
      max_consecutive_losses: toNumber(shutdown.max_consecutive_losses, 3),
      max_daily_losses: toNumber(shutdown.max_daily_losses, 5),
      max_daily_loss_amount: toNumber(shutdown.max_daily_loss_amount, 500),
      consecutive_losses: toNumber(shutdown.consecutive_losses, 0),
      daily_losses: toNumber(shutdown.daily_losses, 0),
      shutdown_triggered: parseBooleanFlag(shutdown.shutdown_triggered),
      shutdown_reason: String(shutdown.shutdown_reason || ''),
    },
    premiumBuffer: parseBooleanFlag(premium.premium_buffer_enabled),
    premiumBufferAmt: toNumber(premium.premium_buffer_amount, 10),
  };
}
