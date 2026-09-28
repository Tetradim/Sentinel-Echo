export type RunnerAllocationMode = 'percent' | 'fixed' | 'greater_of';
export type RunnerTrailingMode = 'fixed' | 'tiered' | 'underlying_confirmed';

export interface RunnerTrailingTier {
  mfe_percent: number;
  trail_percent: number;
}

export interface RunnerSettingsState {
  enabled: boolean;
  allocationMode: RunnerAllocationMode;
  allocationPercent: number;
  fixedContracts: number;
  minContracts: number;
  maxContracts: number;
  allowSingleContract: boolean;
  activationMfePercent: number;
  reserveCandidatesFromProfit: boolean;
  lossLadderConsumesCandidates: boolean;
  protectLossLadder: boolean;
  protectHardStop: boolean;
  protectBreakEven: boolean;
  protectProfitStages: boolean;
  protectOrdinaryTrailing: boolean;
  protectReversalWarning: boolean;
  protectContextualTrims: boolean;
  confirmedReversalExits: boolean;
  catastrophicStopPercent: number;
  catastrophicConfirmations: number;
  catastrophicConfirmationIntervalSeconds: number;
  trailingEnabled: boolean;
  trailingMode: RunnerTrailingMode;
  fixedTrailingPercent: number;
  trailingTiers: RunnerTrailingTier[];
  minTrailingCents: number;
  spreadMultiplier: number;
  trailingConfirmations: number;
  trailingConfirmationIntervalSeconds: number;
  minimumActivationSeconds: number;
  requireFreshHigh: boolean;
  allowFloorToMoveDown: boolean;
  analystOverridePercent: number;
  explicitFullExitOverrides: boolean;
  contextualFullExitOverrides: boolean;
  zeroDteLiquidationEnabled: boolean;
  zeroDteLiquidationTime: string;
}

export const DEFAULT_RUNNER_SETTINGS: RunnerSettingsState = {
  enabled: false,
  allocationMode: 'greater_of',
  allocationPercent: 20,
  fixedContracts: 1,
  minContracts: 1,
  maxContracts: 2,
  allowSingleContract: false,
  activationMfePercent: 100,
  reserveCandidatesFromProfit: true,
  lossLadderConsumesCandidates: true,
  protectLossLadder: true,
  protectHardStop: true,
  protectBreakEven: true,
  protectProfitStages: true,
  protectOrdinaryTrailing: true,
  protectReversalWarning: true,
  protectContextualTrims: true,
  confirmedReversalExits: true,
  catastrophicStopPercent: 65,
  catastrophicConfirmations: 2,
  catastrophicConfirmationIntervalSeconds: 3,
  trailingEnabled: true,
  trailingMode: 'tiered',
  fixedTrailingPercent: 35,
  trailingTiers: [
    { mfe_percent: 100, trail_percent: 35 },
    { mfe_percent: 300, trail_percent: 30 },
    { mfe_percent: 500, trail_percent: 25 },
    { mfe_percent: 1000, trail_percent: 20 },
  ],
  minTrailingCents: 0,
  spreadMultiplier: 2,
  trailingConfirmations: 2,
  trailingConfirmationIntervalSeconds: 3,
  minimumActivationSeconds: 0,
  requireFreshHigh: false,
  allowFloorToMoveDown: false,
  analystOverridePercent: 80,
  explicitFullExitOverrides: true,
  contextualFullExitOverrides: false,
  zeroDteLiquidationEnabled: true,
  zeroDteLiquidationTime: '15:40',
};

function bool(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = String(value ?? '').trim().toLowerCase();
  if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
  if (['false', '0', 'no', 'off'].includes(normalized)) return false;
  return fallback;
}

function number(value: unknown, fallback: number): number {
  if (value === null || value === undefined || value === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function mode<T extends string>(value: unknown, choices: readonly T[], fallback: T): T {
  const normalized = String(value ?? '').trim().toLowerCase() as T;
  return choices.includes(normalized) ? normalized : fallback;
}

export function normalizeRunnerSettings(raw: Record<string, unknown> = {}): RunnerSettingsState {
  const defaults = DEFAULT_RUNNER_SETTINGS;
  const tiers = Array.isArray(raw.core_runner_trailing_tiers)
    ? raw.core_runner_trailing_tiers
        .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
        .map((item) => ({
          mfe_percent: number(item.mfe_percent, 0),
          trail_percent: number(item.trail_percent, 0),
        }))
    : defaults.trailingTiers.map((tier) => ({ ...tier }));
  return {
    enabled: bool(raw.core_runner_enabled, defaults.enabled),
    allocationMode: mode(raw.core_runner_allocation_mode, ['percent', 'fixed', 'greater_of'] as const, defaults.allocationMode),
    allocationPercent: number(raw.core_runner_allocation_percent, defaults.allocationPercent),
    fixedContracts: number(raw.core_runner_fixed_contracts, defaults.fixedContracts),
    minContracts: number(raw.core_runner_min_contracts, defaults.minContracts),
    maxContracts: number(raw.core_runner_max_contracts, defaults.maxContracts),
    allowSingleContract: bool(raw.core_runner_allow_single_contract, defaults.allowSingleContract),
    activationMfePercent: number(raw.core_runner_activation_mfe_percent, defaults.activationMfePercent),
    reserveCandidatesFromProfit: bool(raw.core_runner_reserve_candidates_from_profit, defaults.reserveCandidatesFromProfit),
    lossLadderConsumesCandidates: bool(raw.core_runner_loss_ladder_consumes_candidates, defaults.lossLadderConsumesCandidates),
    protectLossLadder: bool(raw.core_runner_protect_loss_ladder, defaults.protectLossLadder),
    protectHardStop: bool(raw.core_runner_protect_hard_stop, defaults.protectHardStop),
    protectBreakEven: bool(raw.core_runner_protect_break_even, defaults.protectBreakEven),
    protectProfitStages: bool(raw.core_runner_protect_profit_stages, defaults.protectProfitStages),
    protectOrdinaryTrailing: bool(raw.core_runner_protect_ordinary_trailing, defaults.protectOrdinaryTrailing),
    protectReversalWarning: bool(raw.core_runner_protect_reversal_warning, defaults.protectReversalWarning),
    protectContextualTrims: bool(raw.core_runner_protect_contextual_trims, defaults.protectContextualTrims),
    confirmedReversalExits: bool(raw.core_runner_confirmed_reversal_exits, defaults.confirmedReversalExits),
    catastrophicStopPercent: number(raw.core_runner_catastrophic_stop_percent, defaults.catastrophicStopPercent),
    catastrophicConfirmations: number(raw.core_runner_catastrophic_confirmations, defaults.catastrophicConfirmations),
    catastrophicConfirmationIntervalSeconds: number(raw.core_runner_catastrophic_confirmation_interval_seconds, defaults.catastrophicConfirmationIntervalSeconds),
    trailingEnabled: bool(raw.core_runner_trailing_enabled, defaults.trailingEnabled),
    trailingMode: mode(raw.core_runner_trailing_mode, ['fixed', 'tiered', 'underlying_confirmed'] as const, defaults.trailingMode),
    fixedTrailingPercent: number(raw.core_runner_fixed_trailing_percent, defaults.fixedTrailingPercent),
    trailingTiers: tiers.length ? tiers : defaults.trailingTiers.map((tier) => ({ ...tier })),
    minTrailingCents: number(raw.core_runner_min_trailing_cents, defaults.minTrailingCents),
    spreadMultiplier: number(raw.core_runner_spread_multiplier, defaults.spreadMultiplier),
    trailingConfirmations: number(raw.core_runner_trailing_confirmations, defaults.trailingConfirmations),
    trailingConfirmationIntervalSeconds: number(raw.core_runner_trailing_confirmation_interval_seconds, defaults.trailingConfirmationIntervalSeconds),
    minimumActivationSeconds: number(raw.core_runner_minimum_activation_seconds, defaults.minimumActivationSeconds),
    requireFreshHigh: bool(raw.core_runner_require_fresh_high, defaults.requireFreshHigh),
    allowFloorToMoveDown: bool(raw.core_runner_allow_floor_to_move_down, defaults.allowFloorToMoveDown),
    analystOverridePercent: number(raw.core_runner_analyst_override_percent, defaults.analystOverridePercent),
    explicitFullExitOverrides: bool(raw.core_runner_explicit_full_exit_overrides, defaults.explicitFullExitOverrides),
    contextualFullExitOverrides: bool(raw.core_runner_contextual_full_exit_overrides, defaults.contextualFullExitOverrides),
    zeroDteLiquidationEnabled: bool(raw.core_runner_zero_dte_liquidation_enabled, defaults.zeroDteLiquidationEnabled),
    zeroDteLiquidationTime: String(raw.core_runner_zero_dte_liquidation_time ?? defaults.zeroDteLiquidationTime),
  };
}

export function validateRunnerSettings(state: RunnerSettingsState): string[] {
  const errors: string[] = [];
  if (state.allocationPercent < 0 || state.allocationPercent > 100) errors.push('Allocation percent must be between 0 and 100.');
  if (![state.fixedContracts, state.minContracts, state.maxContracts].every((value) => Number.isInteger(value) && value >= 0)) errors.push('Contract allocations must be whole numbers of 0 or more.');
  if (state.maxContracts > 0 && state.minContracts > state.maxContracts) errors.push('Minimum contracts cannot exceed maximum contracts.');
  if (state.activationMfePercent < 0) errors.push('Activation MFE must be 0 or more.');
  if (state.catastrophicStopPercent < 0 || state.catastrophicStopPercent > 100) errors.push('Catastrophic stop must be between 0 and 100.');
  if (state.trailingTiers.length < 1 || state.trailingTiers.length > 10) errors.push('Trailing tiers require 1 to 10 rows.');
  state.trailingTiers.forEach((tier, index) => {
    if (tier.mfe_percent < 0 || tier.trail_percent <= 0 || tier.trail_percent > 100) errors.push(`Trailing tier ${index + 1} has invalid percentages.`);
    if (index > 0 && tier.mfe_percent <= state.trailingTiers[index - 1].mfe_percent) errors.push('Trailing tier MFE values must be strictly increasing.');
  });
  if (![state.catastrophicConfirmations, state.trailingConfirmations].every((value) => Number.isInteger(value) && value >= 1)) errors.push('Confirmation counts must be whole numbers of at least 1.');
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(state.zeroDteLiquidationTime)) errors.push('0DTE liquidation time must use HH:MM.');
  return [...new Set(errors)];
}

export function toRunnerSettingsPayload(state: RunnerSettingsState): Record<string, unknown> {
  return {
    core_runner_enabled: state.enabled,
    core_runner_allocation_mode: state.allocationMode,
    core_runner_allocation_percent: state.allocationPercent,
    core_runner_fixed_contracts: state.fixedContracts,
    core_runner_min_contracts: state.minContracts,
    core_runner_max_contracts: state.maxContracts,
    core_runner_allow_single_contract: state.allowSingleContract,
    core_runner_activation_mfe_percent: state.activationMfePercent,
    core_runner_reserve_candidates_from_profit: state.reserveCandidatesFromProfit,
    core_runner_loss_ladder_consumes_candidates: state.lossLadderConsumesCandidates,
    core_runner_protect_loss_ladder: state.protectLossLadder,
    core_runner_protect_hard_stop: state.protectHardStop,
    core_runner_protect_break_even: state.protectBreakEven,
    core_runner_protect_profit_stages: state.protectProfitStages,
    core_runner_protect_ordinary_trailing: state.protectOrdinaryTrailing,
    core_runner_protect_reversal_warning: state.protectReversalWarning,
    core_runner_protect_contextual_trims: state.protectContextualTrims,
    core_runner_confirmed_reversal_exits: state.confirmedReversalExits,
    core_runner_catastrophic_stop_percent: state.catastrophicStopPercent,
    core_runner_catastrophic_confirmations: state.catastrophicConfirmations,
    core_runner_catastrophic_confirmation_interval_seconds: state.catastrophicConfirmationIntervalSeconds,
    core_runner_trailing_enabled: state.trailingEnabled,
    core_runner_trailing_mode: state.trailingMode,
    core_runner_fixed_trailing_percent: state.fixedTrailingPercent,
    core_runner_trailing_tiers: state.trailingTiers.map((tier) => ({ ...tier })),
    core_runner_min_trailing_cents: state.minTrailingCents,
    core_runner_spread_multiplier: state.spreadMultiplier,
    core_runner_trailing_confirmations: state.trailingConfirmations,
    core_runner_trailing_confirmation_interval_seconds: state.trailingConfirmationIntervalSeconds,
    core_runner_minimum_activation_seconds: state.minimumActivationSeconds,
    core_runner_require_fresh_high: state.requireFreshHigh,
    core_runner_allow_floor_to_move_down: state.allowFloorToMoveDown,
    core_runner_analyst_override_percent: state.analystOverridePercent,
    core_runner_explicit_full_exit_overrides: state.explicitFullExitOverrides,
    core_runner_contextual_full_exit_overrides: state.contextualFullExitOverrides,
    core_runner_zero_dte_liquidation_enabled: state.zeroDteLiquidationEnabled,
    core_runner_zero_dte_liquidation_time: state.zeroDteLiquidationTime,
  };
}
