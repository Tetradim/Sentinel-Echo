import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export interface RiskSettingsState {
  maxPositionSize: number;
  defaultQuantity: number;
  riskPerTrade: number;
  stopLossEnabled: boolean;
  stopLossPercentage: number;
  stopLossOrderType: string;
  takeProfitEnabled: boolean;
  takeProfitPercentage: number;
  multiLevelTakeProfit: boolean;
  trailingStopEnabled: boolean;
  trailingStopType: string;
  trailingStopPercent: number;
  trailingStopCents: number;
  trailingHours: number;
  autoShutdownEnabled: boolean;
  maxConsecutiveLosses: number;
  maxDailyLosses: number;
  maxDailyLossAmount: number;
  maxDrawdownPercent: number;
  maxPositionsPerTicker: number;
  maxPositionsPerSector: number;
}

export interface RiskSettingsBaseInput {
  max_position_size?: number | string | null;
  default_quantity?: number | string | null;
  risk_per_trade?: number | string | null;
  trailing_hours?: number | string | null;
  max_drawdown_percent?: number | string | null;
  max_positions_per_sector?: number | string | null;
}

export interface RiskManagementInput {
  stop_loss_enabled?: BooleanLike;
  stop_loss_percentage?: number | string | null;
  stop_loss_order_type?: string | null;
  take_profit_enabled?: BooleanLike;
  take_profit_percentage?: number | string | null;
  bracket_order_enabled?: BooleanLike;
}

export interface TrailingStopInput {
  trailing_stop_enabled?: BooleanLike;
  trailing_stop_type?: string | null;
  trailing_stop_percent?: number | string | null;
  trailing_stop_cents?: number | string | null;
}

export interface AutoShutdownInput {
  auto_shutdown_enabled?: BooleanLike;
  max_consecutive_losses?: number | string | null;
  max_daily_losses?: number | string | null;
  max_daily_loss_amount?: number | string | null;
}

export interface CorrelationInput {
  max_positions_per_ticker?: number | string | null;
}

export interface NormalizeRiskSettingsStateInput {
  defaults: RiskSettingsState;
  base?: RiskSettingsBaseInput | null;
  risk?: RiskManagementInput | null;
  trailing?: TrailingStopInput | null;
  shutdown?: AutoShutdownInput | null;
  correlation?: CorrelationInput | null;
}

function toNumber(value: number | string | null | undefined, fallback: number): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function toText(value: string | null | undefined, fallback: string): string {
  const text = String(value || '').trim();
  return text || fallback;
}

export function normalizeRiskSettingsState(input: NormalizeRiskSettingsStateInput): RiskSettingsState {
  const defaults = input.defaults;
  const base = input.base || {};
  const risk = input.risk || {};
  const trailing = input.trailing || {};
  const shutdown = input.shutdown || {};
  const correlation = input.correlation || {};

  return {
    maxPositionSize: toNumber(base.max_position_size, defaults.maxPositionSize),
    defaultQuantity: toNumber(base.default_quantity, defaults.defaultQuantity),
    riskPerTrade: toNumber(base.risk_per_trade, defaults.riskPerTrade),
    stopLossEnabled: parseBooleanFlag(risk.stop_loss_enabled),
    stopLossPercentage: toNumber(risk.stop_loss_percentage, defaults.stopLossPercentage),
    stopLossOrderType: toText(risk.stop_loss_order_type, defaults.stopLossOrderType),
    takeProfitEnabled: parseBooleanFlag(risk.take_profit_enabled),
    takeProfitPercentage: toNumber(risk.take_profit_percentage, defaults.takeProfitPercentage),
    multiLevelTakeProfit: parseBooleanFlag(risk.bracket_order_enabled),
    trailingStopEnabled: parseBooleanFlag(trailing.trailing_stop_enabled),
    trailingStopType: toText(trailing.trailing_stop_type, defaults.trailingStopType),
    trailingStopPercent: toNumber(trailing.trailing_stop_percent, defaults.trailingStopPercent),
    trailingStopCents: toNumber(trailing.trailing_stop_cents, defaults.trailingStopCents),
    trailingHours: toNumber(base.trailing_hours, defaults.trailingHours),
    autoShutdownEnabled: parseBooleanFlag(shutdown.auto_shutdown_enabled),
    maxConsecutiveLosses: toNumber(shutdown.max_consecutive_losses, defaults.maxConsecutiveLosses),
    maxDailyLosses: toNumber(shutdown.max_daily_losses, defaults.maxDailyLosses),
    maxDailyLossAmount: toNumber(shutdown.max_daily_loss_amount, defaults.maxDailyLossAmount),
    maxDrawdownPercent: toNumber(base.max_drawdown_percent, defaults.maxDrawdownPercent),
    maxPositionsPerTicker: toNumber(correlation.max_positions_per_ticker, defaults.maxPositionsPerTicker),
    maxPositionsPerSector: toNumber(base.max_positions_per_sector, defaults.maxPositionsPerSector),
  };
}
