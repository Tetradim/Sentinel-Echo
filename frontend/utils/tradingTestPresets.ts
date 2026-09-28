export type TradingTestPresetId =
  | 'runner_capture'
  | 'take_profit_50'
  | 'no_downside_stop'
  | 'mike_directed'
  | 'wide_risk_control';

export type TradingTestPresetRisk = 'measured' | 'high' | 'full-premium';

export interface TradingTestPreset {
  id: TradingTestPresetId;
  name: string;
  shortName: string;
  summary: string;
  automaticExits: string;
  risk: TradingTestPresetRisk;
  payload: Readonly<Record<string, unknown>>;
}

export interface TradingTestPresetChange {
  key: string;
  label: string;
  before: unknown;
  after: unknown;
}

const OPERATIONAL_INVARIANTS = {
  sell_alert_listening_enabled: true,
  bracket_order_enabled: false,
  zero_dte_liquidation_enabled: true,
  zero_dte_liquidation_time: '15:40',
  core_runner_zero_dte_liquidation_enabled: true,
  core_runner_zero_dte_liquidation_time: '15:40',
};

const LEGACY_EXITS_OFF = {
  take_profit_enabled: false,
  take_profit_percentage: 50,
  take_profit_sell_percentage: 100,
  break_even_enabled: false,
  stop_loss_enabled: false,
  stop_loss_percentage: 25,
  stop_loss_order_type: 'market',
  trailing_stop_enabled: false,
  trailing_stop_type: 'percent',
  trailing_stop_percent: 10,
  trailing_stop_activation_percent: 10,
};

const COORDINATED_PROFIT_POLICY = {
  coordinated_exit_enabled: true,
  coordinated_normal_stop_loss_percent: 35,
  coordinated_high_risk_stop_loss_percent: 50,
  coordinated_emergency_stop_loss_percent: 65,
  coordinated_stop_required_confirmations: 2,
  coordinated_stop_confirmation_interval_seconds: 1,
  coordinated_profit_stage_1_percent: 25,
  coordinated_profit_stage_1_sell_percent: 50,
  coordinated_profit_stage_2_percent: 50,
  coordinated_profit_stage_2_sell_percent: 25,
  coordinated_progressive_trailing_enabled: true,
  coordinated_trailing_mode: 'tightening',
  coordinated_trailing_step_gain_percent: 10,
  coordinated_trailing_step_tighten_percent: 1,
  coordinated_trailing_min_percent: 8,
  coordinated_trailing_volatility_gate_percent: 8,
  reversal_exit_enabled: true,
  adaptive_trailing_enabled: true,
};

const RUNNER_POLICY = {
  core_runner_enabled: true,
  core_runner_allocation_mode: 'greater_of',
  core_runner_allocation_percent: 20,
  core_runner_fixed_contracts: 1,
  core_runner_min_contracts: 1,
  core_runner_max_contracts: 2,
  core_runner_allow_single_contract: false,
  core_runner_activation_mfe_percent: 100,
  core_runner_reserve_candidates_from_profit: true,
  core_runner_loss_ladder_consumes_candidates: true,
  core_runner_protect_loss_ladder: true,
  core_runner_protect_hard_stop: true,
  core_runner_protect_break_even: true,
  core_runner_protect_profit_stages: true,
  core_runner_protect_ordinary_trailing: true,
  core_runner_protect_reversal_warning: true,
  core_runner_protect_contextual_trims: true,
  core_runner_confirmed_reversal_exits: true,
  core_runner_catastrophic_stop_percent: 65,
  core_runner_catastrophic_confirmations: 2,
  core_runner_catastrophic_confirmation_interval_seconds: 3,
  core_runner_trailing_enabled: true,
  core_runner_trailing_mode: 'tiered',
  core_runner_fixed_trailing_percent: 35,
  core_runner_trailing_tiers: [
    { mfe_percent: 100, trail_percent: 35 },
    { mfe_percent: 300, trail_percent: 30 },
    { mfe_percent: 500, trail_percent: 25 },
    { mfe_percent: 1000, trail_percent: 20 },
  ],
  core_runner_min_trailing_cents: 0,
  core_runner_spread_multiplier: 2,
  core_runner_trailing_confirmations: 2,
  core_runner_trailing_confirmation_interval_seconds: 3,
  core_runner_minimum_activation_seconds: 0,
  core_runner_require_fresh_high: false,
  core_runner_allow_floor_to_move_down: false,
  core_runner_analyst_override_percent: 80,
  core_runner_explicit_full_exit_overrides: true,
  core_runner_contextual_full_exit_overrides: false,
};

const RUNNER_OFF = {
  ...RUNNER_POLICY,
  core_runner_enabled: false,
};

const CORE_LOSS_LADDER = [
  { loss_percent: 15, quantity_mode: 'percent_original', quantity: 10, confirmations: 2, allocation_target: 'core_only' },
  { loss_percent: 25, quantity_mode: 'percent_original', quantity: 20, confirmations: 2, allocation_target: 'core_only' },
  { loss_percent: 35, quantity_mode: 'percent_original', quantity: 30, confirmations: 2, allocation_target: 'core_only' },
  { loss_percent: 50, quantity_mode: 'percent_remaining', quantity: 100, confirmations: 1, allocation_target: 'core_only' },
];

const LABELS: Record<string, string> = {
  take_profit_enabled: 'Take profit',
  take_profit_percentage: 'Take-profit target',
  take_profit_sell_percentage: 'Take-profit quantity',
  stop_loss_enabled: 'Legacy stop loss',
  break_even_enabled: 'Break-even exit',
  trailing_stop_enabled: 'Legacy trailing stop',
  coordinated_exit_enabled: 'Coordinated exits',
  coordinated_normal_stop_loss_percent: 'Normal hard stop',
  coordinated_high_risk_stop_loss_percent: 'High-risk hard stop',
  coordinated_emergency_stop_loss_percent: 'Emergency hard stop',
  coordinated_loss_ladder_enabled: 'Loss ladder',
  coordinated_profit_stage_1_percent: 'First profit target',
  coordinated_profit_stage_2_percent: 'Second profit target',
  reversal_exit_enabled: 'Reversal exits',
  adaptive_trailing_enabled: 'Adaptive trailing',
  core_runner_enabled: 'Core / Runners',
  core_runner_activation_mfe_percent: 'Runner activation',
  core_runner_catastrophic_stop_percent: 'Runner catastrophic stop',
  core_runner_trailing_enabled: 'Runner trailing',
  core_runner_trailing_tiers: 'Runner trail tiers',
  sell_alert_listening_enabled: 'Discord sell alerts',
  zero_dte_liquidation_enabled: '0DTE liquidation',
};

function cloneValue<T>(value: T): T {
  if (value === undefined) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function preset(
  id: TradingTestPresetId,
  name: string,
  shortName: string,
  summary: string,
  automaticExits: string,
  risk: TradingTestPresetRisk,
  payload: Record<string, unknown>,
): TradingTestPreset {
  return { id, name, shortName, summary, automaticExits, risk, payload };
}

export const TRADING_TEST_PRESETS: readonly TradingTestPreset[] = [
  preset(
    'runner_capture',
    'Runner Capture',
    'Runners',
    'Stage core profits and reserve contracts for exceptional moves.',
    '+25% and +50% core stages, defensive loss ladder, then a tiered runner trail.',
    'measured',
    {
      ...OPERATIONAL_INVARIANTS,
      ...LEGACY_EXITS_OFF,
      ...COORDINATED_PROFIT_POLICY,
      coordinated_loss_ladder_enabled: true,
      coordinated_loss_ladder: CORE_LOSS_LADDER,
      ...RUNNER_POLICY,
    },
  ),
  preset(
    'take_profit_50',
    'Full Take Profit +50',
    '+50% TP',
    'Use one automatic target as a simple comparison policy.',
    'Sell 100% at +50%; no autonomous downside, trailing, break-even, or reversal exit.',
    'high',
    {
      ...OPERATIONAL_INVARIANTS,
      ...LEGACY_EXITS_OFF,
      take_profit_enabled: true,
      take_profit_percentage: 50,
      take_profit_sell_percentage: 100,
      coordinated_exit_enabled: false,
      coordinated_loss_ladder_enabled: false,
      reversal_exit_enabled: false,
      adaptive_trailing_enabled: false,
      ...RUNNER_OFF,
    },
  ),
  preset(
    'no_downside_stop',
    'No Downside Stop',
    'No stop',
    'Test the full move without an automatic price-based loss exit.',
    'Keep staged profits and runner trailing; risk the full premium until an analyst, reversal, profit, or time exit.',
    'full-premium',
    {
      ...OPERATIONAL_INVARIANTS,
      ...LEGACY_EXITS_OFF,
      ...COORDINATED_PROFIT_POLICY,
      coordinated_normal_stop_loss_percent: 100,
      coordinated_high_risk_stop_loss_percent: 100,
      coordinated_emergency_stop_loss_percent: 100,
      coordinated_loss_ladder_enabled: false,
      coordinated_loss_ladder: CORE_LOSS_LADDER,
      ...RUNNER_POLICY,
      core_runner_catastrophic_stop_percent: 0,
    },
  ),
  preset(
    'mike_directed',
    'Mike Directed',
    'Mike only',
    'Measure Mike\'s exit conversation without Echo price exits.',
    'Only explicit Discord exits and mandatory 0DTE liquidation close positions.',
    'full-premium',
    {
      ...OPERATIONAL_INVARIANTS,
      ...LEGACY_EXITS_OFF,
      coordinated_exit_enabled: false,
      coordinated_loss_ladder_enabled: false,
      reversal_exit_enabled: false,
      adaptive_trailing_enabled: false,
      ...RUNNER_OFF,
    },
  ),
  preset(
    'wide_risk_control',
    'Wide-Risk Control',
    'Wide stop',
    'Use one wider hard stop with staged profits and no protected runners.',
    'Take core profits at +25% and +50%; use -50% normal and -75% emergency protection.',
    'high',
    {
      ...OPERATIONAL_INVARIANTS,
      ...LEGACY_EXITS_OFF,
      ...COORDINATED_PROFIT_POLICY,
      coordinated_normal_stop_loss_percent: 50,
      coordinated_high_risk_stop_loss_percent: 65,
      coordinated_emergency_stop_loss_percent: 75,
      coordinated_loss_ladder_enabled: false,
      coordinated_loss_ladder: CORE_LOSS_LADDER,
      ...RUNNER_OFF,
    },
  ),
];

export function getTradingTestPreset(id: TradingTestPresetId): TradingTestPreset {
  const found = TRADING_TEST_PRESETS.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`Unknown trading test preset: ${id}`);
  return found;
}

export function applyTradingTestPreset(
  current: Record<string, unknown>,
  id: TradingTestPresetId,
): Record<string, any> {
  const selected = getTradingTestPreset(id);
  return { ...cloneValue(current), ...cloneValue(selected.payload) };
}

export function diffTradingTestPreset(
  current: Record<string, unknown>,
  id: TradingTestPresetId,
): TradingTestPresetChange[] {
  const selected = getTradingTestPreset(id);
  return Object.entries(selected.payload)
    .filter(([key, value]) => !sameValue(current[key], value))
    .map(([key, value]) => ({
      key,
      label: LABELS[key] || key.replaceAll('_', ' '),
      before: cloneValue(current[key]),
      after: cloneValue(value),
    }));
}

export function matchesTradingTestPreset(
  current: Record<string, unknown>,
  id: TradingTestPresetId,
): boolean {
  return diffTradingTestPreset(current, id).length === 0;
}

