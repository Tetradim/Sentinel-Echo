import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export interface RiskSettingsState {
  maxPositionSize: number;
  defaultQuantity: number;
  riskPerTrade: number;
  smartSizingEnabled: boolean;
  smartSizingAgreementPercent: number;
  smartSizingMixedPercent: number;
  smartSizingConflictPercent: number;
  entrySlippageSizingEnabled: boolean;
  entrySlippageMode: string;
  entrySlippageWarningPercent: number;
  entrySlippageSeverePercent: number;
  entrySlippageWarningSizePercent: number;
  entrySlippageSevereSizePercent: number;
  marketableEntryEnabled: boolean;
  riskBudgetSizingEnabled: boolean;
  maxLossPerTrade: number;
  coordinatedExitEnabled: boolean;
  coordinatedExitQuoteMaxAgeSeconds: number;
  coordinatedNormalStopLossPercent: number;
  coordinatedHighRiskStopLossPercent: number;
  coordinatedHighRiskSizePercent: number;
  coordinatedEmergencyStopLossPercent: number;
  coordinatedStopRequiredConfirmations: number;
  coordinatedStopConfirmationIntervalSeconds: number;
  coordinatedRunnerReserveQuantity: number;
  coordinatedProfitStage1Percent: number;
  coordinatedProfitStage1SellPercent: number;
  coordinatedProfitStage2Percent: number;
  coordinatedProfitStage2SellPercent: number;
  coordinatedFastScalpProfitStage1Percent: number;
  coordinatedFastScalpProfitStage2Percent: number;
  coordinatedLowActivationPercent: number;
  coordinatedLowTrailingPercent: number;
  coordinatedMediumActivationPercent: number;
  coordinatedMediumTrailingPercent: number;
  coordinatedHighActivationPercent: number;
  coordinatedHighTrailingPercent: number;
  coordinatedProgressiveTrailingEnabled: boolean;
  coordinatedTrailingMode: string;
  coordinatedTrailingStepGainPercent: number;
  coordinatedTrailingStepTightenPercent: number;
  coordinatedTrailingMinPercent: number;
  coordinatedTrailingVolatilityGatePercent: number;
  coordinatedElasticActivationPercent: number;
  coordinatedElasticMinActivationCents: number;
  coordinatedElasticTrailingStartPercent: number;
  coordinatedElasticTrailingStepGainPercent: number;
  coordinatedElasticTrailingStepWidenPercent: number;
  coordinatedElasticTrailingMaxPercent: number;
  coordinatedTrailingSpreadMultiplier: number;
  coordinatedLossLadderEnabled: boolean;
  coordinatedLossLadder: LossLadderStep[];
  fillConfirmationTimeoutSeconds: number;
  exitRepriceIntervalSeconds: number;
  profitExitRepriceIntervalSeconds: number;
  reversalExitEnabled: boolean;
  reversalWarningConfirmations: number;
  reversalConfirmedConfirmations: number;
  reversalWarningSellPercent: number;
  reversalPremiumDrawdownPercent: number;
  reversalReduceMinReturnPercent: number;
  reversalReduceMinMfePercent: number;
  adaptiveTrailingEnabled: boolean;
  adaptiveTrailingMinPercent: number;
  adaptiveTrailingMaxPercent: number;
  zeroDteLiquidationEnabled: boolean;
  zeroDteLiquidationTime: string;
  stopLossEnabled: boolean;
  stopLossPercentage: number;
  stopLossOrderType: string;
  takeProfitEnabled: boolean;
  takeProfitPercentage: number;
  takeProfitSellPercentage: number;
  multiLevelTakeProfit: boolean;
  breakEvenEnabled: boolean;
  breakEvenActivationType: string;
  breakEvenActivationPercentage: number;
  breakEvenActivationCents: number;
  trailingStopEnabled: boolean;
  trailingStopType: string;
  trailingStopPercent: number;
  trailingStopActivationPercent: number;
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

export interface LossLadderStep {
  loss_percent: number;
  quantity_mode: 'fixed' | 'percent_original' | 'percent_remaining';
  quantity: number;
  confirmations: number;
}

export interface RiskSettingsBaseInput {
  max_position_size?: number | string | null;
  default_quantity?: number | string | null;
  risk_per_trade?: number | string | null;
  smart_sizing_enabled?: BooleanLike;
  smart_sizing_agreement_percent?: number | string | null;
  smart_sizing_mixed_percent?: number | string | null;
  smart_sizing_conflict_percent?: number | string | null;
  entry_slippage_sizing_enabled?: BooleanLike;
  entry_slippage_mode?: string | null;
  entry_slippage_warning_percent?: number | string | null;
  entry_slippage_severe_percent?: number | string | null;
  entry_slippage_warning_size_percent?: number | string | null;
  entry_slippage_severe_size_percent?: number | string | null;
  marketable_entry_enabled?: BooleanLike;
  risk_budget_sizing_enabled?: BooleanLike;
  max_loss_per_trade?: number | string | null;
  coordinated_exit_enabled?: BooleanLike;
  coordinated_exit_quote_max_age_seconds?: number | string | null;
  coordinated_normal_stop_loss_percent?: number | string | null;
  coordinated_high_risk_stop_loss_percent?: number | string | null;
  coordinated_high_risk_size_percent?: number | string | null;
  coordinated_emergency_stop_loss_percent?: number | string | null;
  coordinated_stop_required_confirmations?: number | string | null;
  coordinated_stop_confirmation_interval_seconds?: number | string | null;
  coordinated_runner_reserve_quantity?: number | string | null;
  coordinated_profit_stage_1_percent?: number | string | null;
  coordinated_profit_stage_1_sell_percent?: number | string | null;
  coordinated_profit_stage_2_percent?: number | string | null;
  coordinated_profit_stage_2_sell_percent?: number | string | null;
  coordinated_fast_scalp_profit_stage_1_percent?: number | string | null;
  coordinated_fast_scalp_profit_stage_2_percent?: number | string | null;
  coordinated_low_activation_percent?: number | string | null;
  coordinated_low_trailing_percent?: number | string | null;
  coordinated_medium_activation_percent?: number | string | null;
  coordinated_medium_trailing_percent?: number | string | null;
  coordinated_high_activation_percent?: number | string | null;
  coordinated_high_trailing_percent?: number | string | null;
  coordinated_progressive_trailing_enabled?: BooleanLike;
  coordinated_trailing_mode?: string | null;
  coordinated_trailing_step_gain_percent?: number | string | null;
  coordinated_trailing_step_tighten_percent?: number | string | null;
  coordinated_trailing_min_percent?: number | string | null;
  coordinated_trailing_volatility_gate_percent?: number | string | null;
  coordinated_elastic_activation_percent?: number | string | null;
  coordinated_elastic_min_activation_cents?: number | string | null;
  coordinated_elastic_trailing_start_percent?: number | string | null;
  coordinated_elastic_trailing_step_gain_percent?: number | string | null;
  coordinated_elastic_trailing_step_widen_percent?: number | string | null;
  coordinated_elastic_trailing_max_percent?: number | string | null;
  coordinated_trailing_spread_multiplier?: number | string | null;
  coordinated_loss_ladder_enabled?: BooleanLike;
  coordinated_loss_ladder?: LossLadderStep[] | null;
  fill_confirmation_timeout_seconds?: number | string | null;
  exit_reprice_interval_seconds?: number | string | null;
  profit_exit_reprice_interval_seconds?: number | string | null;
  reversal_exit_enabled?: BooleanLike;
  reversal_warning_confirmations?: number | string | null;
  reversal_confirmed_confirmations?: number | string | null;
  reversal_warning_sell_percent?: number | string | null;
  reversal_premium_drawdown_percent?: number | string | null;
  reversal_reduce_min_return_percent?: number | string | null;
  reversal_reduce_min_mfe_percent?: number | string | null;
  adaptive_trailing_enabled?: BooleanLike;
  adaptive_trailing_min_percent?: number | string | null;
  adaptive_trailing_max_percent?: number | string | null;
  zero_dte_liquidation_enabled?: BooleanLike;
  zero_dte_liquidation_time?: string | null;
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
  take_profit_sell_percentage?: number | string | null;
  bracket_order_enabled?: BooleanLike;
  break_even_enabled?: BooleanLike;
  break_even_activation_type?: string | null;
  break_even_activation_percentage?: number | string | null;
  break_even_activation_cents?: number | string | null;
}

export interface TrailingStopInput {
  trailing_stop_enabled?: BooleanLike;
  trailing_stop_type?: string | null;
  trailing_stop_percent?: number | string | null;
  trailing_stop_activation_percent?: number | string | null;
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
    smartSizingEnabled: parseBooleanFlag(base.smart_sizing_enabled, defaults.smartSizingEnabled),
    smartSizingAgreementPercent: toNumber(
      base.smart_sizing_agreement_percent,
      defaults.smartSizingAgreementPercent,
    ),
    smartSizingMixedPercent: toNumber(base.smart_sizing_mixed_percent, defaults.smartSizingMixedPercent),
    smartSizingConflictPercent: toNumber(
      base.smart_sizing_conflict_percent,
      defaults.smartSizingConflictPercent,
    ),
    entrySlippageSizingEnabled: parseBooleanFlag(
      base.entry_slippage_sizing_enabled,
      defaults.entrySlippageSizingEnabled,
    ),
    entrySlippageMode: toText(base.entry_slippage_mode, defaults.entrySlippageMode),
    entrySlippageWarningPercent: toNumber(
      base.entry_slippage_warning_percent,
      defaults.entrySlippageWarningPercent,
    ),
    entrySlippageSeverePercent: toNumber(
      base.entry_slippage_severe_percent,
      defaults.entrySlippageSeverePercent,
    ),
    entrySlippageWarningSizePercent: toNumber(
      base.entry_slippage_warning_size_percent,
      defaults.entrySlippageWarningSizePercent,
    ),
    entrySlippageSevereSizePercent: toNumber(
      base.entry_slippage_severe_size_percent,
      defaults.entrySlippageSevereSizePercent,
    ),
    marketableEntryEnabled: parseBooleanFlag(
      base.marketable_entry_enabled,
      defaults.marketableEntryEnabled,
    ),
    riskBudgetSizingEnabled: parseBooleanFlag(
      base.risk_budget_sizing_enabled,
      defaults.riskBudgetSizingEnabled,
    ),
    maxLossPerTrade: toNumber(base.max_loss_per_trade, defaults.maxLossPerTrade),
    coordinatedExitEnabled: parseBooleanFlag(
      base.coordinated_exit_enabled,
      defaults.coordinatedExitEnabled,
    ),
    coordinatedExitQuoteMaxAgeSeconds: toNumber(
      base.coordinated_exit_quote_max_age_seconds,
      defaults.coordinatedExitQuoteMaxAgeSeconds,
    ),
    coordinatedNormalStopLossPercent: toNumber(
      base.coordinated_normal_stop_loss_percent,
      defaults.coordinatedNormalStopLossPercent,
    ),
    coordinatedHighRiskStopLossPercent: toNumber(
      base.coordinated_high_risk_stop_loss_percent,
      defaults.coordinatedHighRiskStopLossPercent,
    ),
    coordinatedHighRiskSizePercent: toNumber(
      base.coordinated_high_risk_size_percent,
      defaults.coordinatedHighRiskSizePercent,
    ),
    coordinatedEmergencyStopLossPercent: toNumber(
      base.coordinated_emergency_stop_loss_percent,
      defaults.coordinatedEmergencyStopLossPercent,
    ),
    coordinatedStopRequiredConfirmations: toNumber(
      base.coordinated_stop_required_confirmations,
      defaults.coordinatedStopRequiredConfirmations,
    ),
    coordinatedStopConfirmationIntervalSeconds: toNumber(
      base.coordinated_stop_confirmation_interval_seconds,
      defaults.coordinatedStopConfirmationIntervalSeconds,
    ),
    coordinatedRunnerReserveQuantity: toNumber(
      base.coordinated_runner_reserve_quantity,
      defaults.coordinatedRunnerReserveQuantity,
    ),
    coordinatedProfitStage1Percent: toNumber(
      base.coordinated_profit_stage_1_percent,
      defaults.coordinatedProfitStage1Percent,
    ),
    coordinatedProfitStage1SellPercent: toNumber(
      base.coordinated_profit_stage_1_sell_percent,
      defaults.coordinatedProfitStage1SellPercent,
    ),
    coordinatedProfitStage2Percent: toNumber(
      base.coordinated_profit_stage_2_percent,
      defaults.coordinatedProfitStage2Percent,
    ),
    coordinatedProfitStage2SellPercent: toNumber(
      base.coordinated_profit_stage_2_sell_percent,
      defaults.coordinatedProfitStage2SellPercent,
    ),
    coordinatedFastScalpProfitStage1Percent: toNumber(
      base.coordinated_fast_scalp_profit_stage_1_percent,
      defaults.coordinatedFastScalpProfitStage1Percent,
    ),
    coordinatedFastScalpProfitStage2Percent: toNumber(
      base.coordinated_fast_scalp_profit_stage_2_percent,
      defaults.coordinatedFastScalpProfitStage2Percent,
    ),
    coordinatedLowActivationPercent: toNumber(
      base.coordinated_low_activation_percent,
      defaults.coordinatedLowActivationPercent,
    ),
    coordinatedLowTrailingPercent: toNumber(
      base.coordinated_low_trailing_percent,
      defaults.coordinatedLowTrailingPercent,
    ),
    coordinatedMediumActivationPercent: toNumber(
      base.coordinated_medium_activation_percent,
      defaults.coordinatedMediumActivationPercent,
    ),
    coordinatedMediumTrailingPercent: toNumber(
      base.coordinated_medium_trailing_percent,
      defaults.coordinatedMediumTrailingPercent,
    ),
    coordinatedHighActivationPercent: toNumber(
      base.coordinated_high_activation_percent,
      defaults.coordinatedHighActivationPercent,
    ),
    coordinatedHighTrailingPercent: toNumber(
      base.coordinated_high_trailing_percent,
      defaults.coordinatedHighTrailingPercent,
    ),
    coordinatedProgressiveTrailingEnabled: parseBooleanFlag(
      base.coordinated_progressive_trailing_enabled,
      defaults.coordinatedProgressiveTrailingEnabled,
    ),
    coordinatedTrailingMode: toText(base.coordinated_trailing_mode, defaults.coordinatedTrailingMode),
    coordinatedTrailingStepGainPercent: toNumber(
      base.coordinated_trailing_step_gain_percent,
      defaults.coordinatedTrailingStepGainPercent,
    ),
    coordinatedTrailingStepTightenPercent: toNumber(
      base.coordinated_trailing_step_tighten_percent,
      defaults.coordinatedTrailingStepTightenPercent,
    ),
    coordinatedTrailingMinPercent: toNumber(
      base.coordinated_trailing_min_percent,
      defaults.coordinatedTrailingMinPercent,
    ),
    coordinatedTrailingVolatilityGatePercent: toNumber(
      base.coordinated_trailing_volatility_gate_percent,
      defaults.coordinatedTrailingVolatilityGatePercent,
    ),
    coordinatedElasticActivationPercent: toNumber(base.coordinated_elastic_activation_percent, defaults.coordinatedElasticActivationPercent),
    coordinatedElasticMinActivationCents: toNumber(base.coordinated_elastic_min_activation_cents, defaults.coordinatedElasticMinActivationCents),
    coordinatedElasticTrailingStartPercent: toNumber(base.coordinated_elastic_trailing_start_percent, defaults.coordinatedElasticTrailingStartPercent),
    coordinatedElasticTrailingStepGainPercent: toNumber(base.coordinated_elastic_trailing_step_gain_percent, defaults.coordinatedElasticTrailingStepGainPercent),
    coordinatedElasticTrailingStepWidenPercent: toNumber(base.coordinated_elastic_trailing_step_widen_percent, defaults.coordinatedElasticTrailingStepWidenPercent),
    coordinatedElasticTrailingMaxPercent: toNumber(base.coordinated_elastic_trailing_max_percent, defaults.coordinatedElasticTrailingMaxPercent),
    coordinatedTrailingSpreadMultiplier: toNumber(base.coordinated_trailing_spread_multiplier, defaults.coordinatedTrailingSpreadMultiplier),
    coordinatedLossLadderEnabled: parseBooleanFlag(base.coordinated_loss_ladder_enabled, defaults.coordinatedLossLadderEnabled),
    coordinatedLossLadder: normalizeLossLadder(base.coordinated_loss_ladder, defaults.coordinatedLossLadder),
    fillConfirmationTimeoutSeconds: toNumber(
      base.fill_confirmation_timeout_seconds,
      defaults.fillConfirmationTimeoutSeconds,
    ),
    exitRepriceIntervalSeconds: toNumber(base.exit_reprice_interval_seconds, defaults.exitRepriceIntervalSeconds),
    profitExitRepriceIntervalSeconds: toNumber(base.profit_exit_reprice_interval_seconds, defaults.profitExitRepriceIntervalSeconds),
    reversalExitEnabled: parseBooleanFlag(base.reversal_exit_enabled, defaults.reversalExitEnabled),
    reversalWarningConfirmations: toNumber(
      base.reversal_warning_confirmations,
      defaults.reversalWarningConfirmations,
    ),
    reversalConfirmedConfirmations: toNumber(
      base.reversal_confirmed_confirmations,
      defaults.reversalConfirmedConfirmations,
    ),
    reversalWarningSellPercent: toNumber(
      base.reversal_warning_sell_percent,
      defaults.reversalWarningSellPercent,
    ),
    reversalPremiumDrawdownPercent: toNumber(
      base.reversal_premium_drawdown_percent,
      defaults.reversalPremiumDrawdownPercent,
    ),
    reversalReduceMinReturnPercent: toNumber(base.reversal_reduce_min_return_percent, defaults.reversalReduceMinReturnPercent),
    reversalReduceMinMfePercent: toNumber(base.reversal_reduce_min_mfe_percent, defaults.reversalReduceMinMfePercent),
    adaptiveTrailingEnabled: parseBooleanFlag(
      base.adaptive_trailing_enabled,
      defaults.adaptiveTrailingEnabled,
    ),
    adaptiveTrailingMinPercent: toNumber(
      base.adaptive_trailing_min_percent,
      defaults.adaptiveTrailingMinPercent,
    ),
    adaptiveTrailingMaxPercent: toNumber(
      base.adaptive_trailing_max_percent,
      defaults.adaptiveTrailingMaxPercent,
    ),
    zeroDteLiquidationEnabled: parseBooleanFlag(
      base.zero_dte_liquidation_enabled,
      defaults.zeroDteLiquidationEnabled,
    ),
    zeroDteLiquidationTime: toText(
      base.zero_dte_liquidation_time,
      defaults.zeroDteLiquidationTime,
    ),
    stopLossEnabled: parseBooleanFlag(risk.stop_loss_enabled),
    stopLossPercentage: toNumber(risk.stop_loss_percentage, defaults.stopLossPercentage),
    stopLossOrderType: toText(risk.stop_loss_order_type, defaults.stopLossOrderType),
    takeProfitEnabled: parseBooleanFlag(risk.take_profit_enabled),
    takeProfitPercentage: toNumber(risk.take_profit_percentage, defaults.takeProfitPercentage),
    takeProfitSellPercentage: toNumber(risk.take_profit_sell_percentage, defaults.takeProfitSellPercentage),
    multiLevelTakeProfit: parseBooleanFlag(risk.bracket_order_enabled),
    breakEvenEnabled: parseBooleanFlag(risk.break_even_enabled),
    breakEvenActivationType: toText(risk.break_even_activation_type, defaults.breakEvenActivationType),
    breakEvenActivationPercentage: toNumber(
      risk.break_even_activation_percentage,
      defaults.breakEvenActivationPercentage,
    ),
    breakEvenActivationCents: toNumber(risk.break_even_activation_cents, defaults.breakEvenActivationCents),
    trailingStopEnabled: parseBooleanFlag(trailing.trailing_stop_enabled),
    trailingStopType: toText(trailing.trailing_stop_type, defaults.trailingStopType),
    trailingStopPercent: toNumber(trailing.trailing_stop_percent, defaults.trailingStopPercent),
    trailingStopActivationPercent: toNumber(
      trailing.trailing_stop_activation_percent,
      defaults.trailingStopActivationPercent,
    ),
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

function normalizeLossLadder(value: LossLadderStep[] | null | undefined, fallback: LossLadderStep[]): LossLadderStep[] {
  if (!Array.isArray(value) || value.length === 0) return fallback.map(step => ({ ...step }));
  const modes = new Set(['fixed', 'percent_original', 'percent_remaining']);
  const normalized = value.map((step) => ({
    loss_percent: toNumber(step?.loss_percent, 0),
    quantity_mode: (modes.has(step?.quantity_mode) ? step.quantity_mode : 'percent_original') as LossLadderStep['quantity_mode'],
    quantity: toNumber(step?.quantity, 0),
    confirmations: Math.max(1, Math.round(toNumber(step?.confirmations, 1))),
  })).filter(step => step.loss_percent > 0 && step.quantity > 0);
  return normalized.length ? normalized : fallback.map(step => ({ ...step }));
}
