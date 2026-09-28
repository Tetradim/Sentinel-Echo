const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ts = require('typescript');

require.extensions['.ts'] = function loadTs(module, filename) {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  module._compile(output, filename);
};

const { normalizeRiskSettingsState } = require('../utils/riskSettingsState.ts');

const defaults = {
  maxPositionSize: 1000,
  defaultQuantity: 1,
  riskPerTrade: 1,
  smartSizingEnabled: true,
  smartSizingAgreementPercent: 100,
  smartSizingMixedPercent: 50,
  smartSizingConflictPercent: 25,
  entrySlippageSizingEnabled: true,
  entrySlippageMode: 'tiered',
  entrySlippageWarningPercent: 10,
  entrySlippageSeverePercent: 20,
  entrySlippageWarningSizePercent: 50,
  entrySlippageSevereSizePercent: 25,
  marketableEntryEnabled: true,
  riskBudgetSizingEnabled: true,
  maxLossPerTrade: 500,
  coordinatedExitEnabled: true,
  coordinatedExitQuoteMaxAgeSeconds: 15,
  coordinatedNormalStopLossPercent: 35,
  coordinatedHighRiskStopLossPercent: 50,
  coordinatedHighRiskSizePercent: 25,
  coordinatedEmergencyStopLossPercent: 50,
  coordinatedStopRequiredConfirmations: 2,
  coordinatedStopConfirmationIntervalSeconds: 1,
  coordinatedRunnerReserveQuantity: 1,
  coordinatedProfitStage1Percent: 25,
  coordinatedProfitStage1SellPercent: 50,
  coordinatedProfitStage2Percent: 35,
  coordinatedProfitStage2SellPercent: 25,
  coordinatedFastScalpProfitStage1Percent: 10,
  coordinatedFastScalpProfitStage2Percent: 20,
  coordinatedLowActivationPercent: 25,
  coordinatedLowTrailingPercent: 18,
  coordinatedMediumActivationPercent: 20,
  coordinatedMediumTrailingPercent: 15,
  coordinatedHighActivationPercent: 12,
  coordinatedHighTrailingPercent: 10,
  coordinatedProgressiveTrailingEnabled: true,
  coordinatedTrailingMode: 'tightening',
  coordinatedTrailingStepGainPercent: 10,
  coordinatedTrailingStepTightenPercent: 1,
  coordinatedTrailingMinPercent: 8,
  coordinatedTrailingVolatilityGatePercent: 8,
  coordinatedElasticActivationPercent: 5,
  coordinatedElasticMinActivationCents: 3,
  coordinatedElasticTrailingStartPercent: 6,
  coordinatedElasticTrailingStepGainPercent: 10,
  coordinatedElasticTrailingStepWidenPercent: 1,
  coordinatedElasticTrailingMaxPercent: 10,
  coordinatedTrailingSpreadMultiplier: 2,
  coordinatedLossLadderEnabled: true,
  coordinatedLossLadder: [{ loss_percent: 12, quantity_mode: 'percent_original', quantity: 10, confirmations: 2 }],
  fillConfirmationTimeoutSeconds: 180,
  exitRepriceIntervalSeconds: 5,
  profitExitRepriceIntervalSeconds: 12,
  reversalExitEnabled: true,
  reversalWarningConfirmations: 2,
  reversalConfirmedConfirmations: 4,
  reversalWarningSellPercent: 25,
  reversalPremiumDrawdownPercent: 12,
  reversalReduceMinReturnPercent: 5,
  reversalReduceMinMfePercent: 20,
  adaptiveTrailingEnabled: true,
  adaptiveTrailingMinPercent: 8,
  adaptiveTrailingMaxPercent: 35,
  zeroDteLiquidationEnabled: true,
  zeroDteLiquidationTime: '15:40',
  stopLossEnabled: true,
  stopLossPercentage: 30,
  stopLossOrderType: 'market',
  takeProfitEnabled: true,
  takeProfitPercentage: 50,
  takeProfitSellPercentage: 50,
  multiLevelTakeProfit: true,
  breakEvenEnabled: true,
  breakEvenActivationType: 'percent',
  breakEvenActivationPercentage: 10,
  breakEvenActivationCents: 15,
  trailingStopEnabled: true,
  trailingStopType: 'percent',
  trailingStopPercent: 25,
  trailingStopActivationPercent: 10,
  trailingStopCents: 0.25,
  trailingHours: 4,
  autoShutdownEnabled: true,
  maxConsecutiveLosses: 3,
  maxDailyLosses: 5,
  maxDailyLossAmount: 500,
  maxDrawdownPercent: 20,
  maxPositionsPerTicker: 3,
  maxPositionsPerSector: 3,
};

test('normalizes string booleans from risk settings responses', () => {
  const state = normalizeRiskSettingsState({
    defaults,
    base: {
      max_position_size: '2500',
      default_quantity: '2',
      risk_per_trade: '1.5',
      smart_sizing_enabled: 'false',
      smart_sizing_agreement_percent: '90',
      smart_sizing_mixed_percent: '45',
      smart_sizing_conflict_percent: '20',
      entry_slippage_sizing_enabled: 'false',
      entry_slippage_mode: 'binary',
      entry_slippage_warning_percent: '11',
      entry_slippage_severe_percent: '21',
      entry_slippage_warning_size_percent: '45',
      entry_slippage_severe_size_percent: '20',
      marketable_entry_enabled: 'false',
      risk_budget_sizing_enabled: 'false',
      max_loss_per_trade: '375',
      coordinated_exit_enabled: 'true',
      coordinated_exit_quote_max_age_seconds: '12',
      coordinated_normal_stop_loss_percent: '34',
      coordinated_high_risk_stop_loss_percent: '48',
      coordinated_high_risk_size_percent: '20',
      coordinated_emergency_stop_loss_percent: '55',
      coordinated_stop_required_confirmations: '3',
      coordinated_stop_confirmation_interval_seconds: '2',
      coordinated_runner_reserve_quantity: '2',
      coordinated_profit_stage_1_percent: '24',
      coordinated_profit_stage_1_sell_percent: '45',
      coordinated_profit_stage_2_percent: '36',
      coordinated_profit_stage_2_sell_percent: '30',
      coordinated_fast_scalp_profit_stage_1_percent: '12',
      coordinated_fast_scalp_profit_stage_2_percent: '22',
      coordinated_low_activation_percent: '26',
      coordinated_low_trailing_percent: '19',
      coordinated_medium_activation_percent: '21',
      coordinated_medium_trailing_percent: '16',
      coordinated_high_activation_percent: '13',
      coordinated_high_trailing_percent: '11',
      coordinated_progressive_trailing_enabled: 'false',
      coordinated_trailing_mode: 'elastic',
      coordinated_trailing_step_gain_percent: '12',
      coordinated_trailing_step_tighten_percent: '0.5',
      coordinated_trailing_min_percent: '7',
      coordinated_trailing_volatility_gate_percent: '9',
      coordinated_elastic_activation_percent: '6',
      coordinated_elastic_min_activation_cents: '4',
      coordinated_elastic_trailing_start_percent: '7',
      coordinated_elastic_trailing_step_gain_percent: '11',
      coordinated_elastic_trailing_step_widen_percent: '0.5',
      coordinated_elastic_trailing_max_percent: '12',
      coordinated_trailing_spread_multiplier: '2.5',
      coordinated_loss_ladder_enabled: 'true',
      coordinated_loss_ladder: [{ loss_percent: 15, quantity_mode: 'fixed', quantity: 2, confirmations: 3 }],
      fill_confirmation_timeout_seconds: '240',
      exit_reprice_interval_seconds: '4',
      profit_exit_reprice_interval_seconds: '14',
      reversal_exit_enabled: 'false',
      reversal_warning_confirmations: '3',
      reversal_confirmed_confirmations: '5',
      reversal_warning_sell_percent: '30',
      reversal_premium_drawdown_percent: '14',
      reversal_reduce_min_return_percent: '6',
      reversal_reduce_min_mfe_percent: '22',
      adaptive_trailing_enabled: 'false',
      adaptive_trailing_min_percent: '9',
      adaptive_trailing_max_percent: '30',
      zero_dte_liquidation_enabled: 'false',
      zero_dte_liquidation_time: '15:35',
      trailing_hours: '6',
      max_drawdown_percent: '15',
      max_positions_per_sector: '4',
    },
    risk: {
      stop_loss_enabled: 'false',
      stop_loss_percentage: '20',
      stop_loss_order_type: 'limit',
      take_profit_enabled: '0',
      take_profit_percentage: '40',
      take_profit_sell_percentage: '50',
      bracket_order_enabled: 'false',
      break_even_enabled: 'true',
      break_even_activation_type: 'cents',
      break_even_activation_percentage: '15',
      break_even_activation_cents: '20',
    },
    trailing: {
      trailing_stop_enabled: 'false',
      trailing_stop_type: 'cents',
      trailing_stop_percent: '12',
      trailing_stop_activation_percent: '18',
      trailing_stop_cents: '0.15',
    },
    shutdown: {
      auto_shutdown_enabled: 'false',
      max_consecutive_losses: '2',
      max_daily_losses: '4',
      max_daily_loss_amount: '350',
    },
    correlation: {
      max_positions_per_ticker: '1',
    },
  });

  assert.equal(state.stopLossEnabled, false);
  assert.equal(state.entrySlippageMode, 'binary');
  assert.equal(state.coordinatedTrailingMode, 'elastic');
  assert.equal(state.coordinatedElasticTrailingMaxPercent, 12);
  assert.deepEqual(state.coordinatedLossLadder, [{ loss_percent: 15, quantity_mode: 'fixed', quantity: 2, confirmations: 3 }]);
  assert.equal(state.exitRepriceIntervalSeconds, 4);
  assert.equal(state.profitExitRepriceIntervalSeconds, 14);
  assert.equal(state.reversalReduceMinReturnPercent, 6);
  assert.equal(state.reversalReduceMinMfePercent, 22);
  assert.equal(state.takeProfitEnabled, false);
  assert.equal(state.multiLevelTakeProfit, false);
  assert.equal(state.breakEvenEnabled, true);
  assert.equal(state.breakEvenActivationType, 'cents');
  assert.equal(state.trailingStopEnabled, false);
  assert.equal(state.autoShutdownEnabled, false);
  assert.equal(state.maxPositionSize, 2500);
  assert.equal(state.defaultQuantity, 2);
  assert.equal(state.riskPerTrade, 1.5);
  assert.equal(state.smartSizingEnabled, false);
  assert.equal(state.smartSizingAgreementPercent, 90);
  assert.equal(state.smartSizingMixedPercent, 45);
  assert.equal(state.smartSizingConflictPercent, 20);
  assert.equal(state.entrySlippageSizingEnabled, false);
  assert.equal(state.entrySlippageWarningPercent, 11);
  assert.equal(state.entrySlippageSeverePercent, 21);
  assert.equal(state.entrySlippageWarningSizePercent, 45);
  assert.equal(state.entrySlippageSevereSizePercent, 20);
  assert.equal(state.marketableEntryEnabled, false);
  assert.equal(state.riskBudgetSizingEnabled, false);
  assert.equal(state.maxLossPerTrade, 375);
  assert.equal(state.coordinatedExitEnabled, true);
  assert.equal(state.coordinatedExitQuoteMaxAgeSeconds, 12);
  assert.equal(state.coordinatedNormalStopLossPercent, 34);
  assert.equal(state.coordinatedHighRiskStopLossPercent, 48);
  assert.equal(state.coordinatedHighRiskSizePercent, 20);
  assert.equal(state.coordinatedEmergencyStopLossPercent, 55);
  assert.equal(state.coordinatedStopRequiredConfirmations, 3);
  assert.equal(state.coordinatedStopConfirmationIntervalSeconds, 2);
  assert.equal(state.coordinatedRunnerReserveQuantity, 2);
  assert.equal(state.coordinatedProfitStage1Percent, 24);
  assert.equal(state.coordinatedProfitStage1SellPercent, 45);
  assert.equal(state.coordinatedProfitStage2Percent, 36);
  assert.equal(state.coordinatedProfitStage2SellPercent, 30);
  assert.equal(state.coordinatedFastScalpProfitStage1Percent, 12);
  assert.equal(state.coordinatedFastScalpProfitStage2Percent, 22);
  assert.equal(state.coordinatedLowActivationPercent, 26);
  assert.equal(state.coordinatedLowTrailingPercent, 19);
  assert.equal(state.coordinatedMediumActivationPercent, 21);
  assert.equal(state.coordinatedMediumTrailingPercent, 16);
  assert.equal(state.coordinatedHighActivationPercent, 13);
  assert.equal(state.coordinatedHighTrailingPercent, 11);
  assert.equal(state.coordinatedProgressiveTrailingEnabled, false);
  assert.equal(state.coordinatedTrailingStepGainPercent, 12);
  assert.equal(state.coordinatedTrailingStepTightenPercent, 0.5);
  assert.equal(state.coordinatedTrailingMinPercent, 7);
  assert.equal(state.coordinatedTrailingVolatilityGatePercent, 9);
  assert.equal(state.fillConfirmationTimeoutSeconds, 240);
  assert.equal(state.reversalExitEnabled, false);
  assert.equal(state.reversalWarningConfirmations, 3);
  assert.equal(state.reversalConfirmedConfirmations, 5);
  assert.equal(state.reversalWarningSellPercent, 30);
  assert.equal(state.reversalPremiumDrawdownPercent, 14);
  assert.equal(state.adaptiveTrailingEnabled, false);
  assert.equal(state.adaptiveTrailingMinPercent, 9);
  assert.equal(state.adaptiveTrailingMaxPercent, 30);
  assert.equal(state.zeroDteLiquidationEnabled, false);
  assert.equal(state.zeroDteLiquidationTime, '15:35');
  assert.equal(state.stopLossPercentage, 20);
  assert.equal(state.takeProfitPercentage, 40);
  assert.equal(state.takeProfitSellPercentage, 50);
  assert.equal(state.breakEvenActivationPercentage, 15);
  assert.equal(state.breakEvenActivationCents, 20);
  assert.equal(state.trailingStopType, 'cents');
  assert.equal(state.trailingStopPercent, 12);
  assert.equal(state.trailingStopActivationPercent, 18);
  assert.equal(state.trailingStopCents, 0.15);
  assert.equal(state.trailingHours, 6);
  assert.equal(state.maxConsecutiveLosses, 2);
  assert.equal(state.maxDailyLosses, 4);
  assert.equal(state.maxDailyLossAmount, 350);
  assert.equal(state.maxDrawdownPercent, 15);
  assert.equal(state.maxPositionsPerTicker, 1);
  assert.equal(state.maxPositionsPerSector, 4);
});

test('keeps fallback defaults for missing or invalid risk settings values', () => {
  const state = normalizeRiskSettingsState({
    defaults,
    base: { max_position_size: 'not-a-number' },
    risk: { stop_loss_order_type: '' },
    trailing: { trailing_stop_type: '' },
  });

  assert.equal(state.maxPositionSize, defaults.maxPositionSize);
  assert.equal(state.smartSizingEnabled, defaults.smartSizingEnabled);
  assert.equal(state.smartSizingAgreementPercent, defaults.smartSizingAgreementPercent);
  assert.equal(state.smartSizingMixedPercent, defaults.smartSizingMixedPercent);
  assert.equal(state.smartSizingConflictPercent, defaults.smartSizingConflictPercent);
  assert.equal(state.reversalExitEnabled, defaults.reversalExitEnabled);
  assert.equal(state.reversalWarningConfirmations, defaults.reversalWarningConfirmations);
  assert.equal(state.reversalConfirmedConfirmations, defaults.reversalConfirmedConfirmations);
  assert.equal(state.reversalWarningSellPercent, defaults.reversalWarningSellPercent);
  assert.equal(state.reversalPremiumDrawdownPercent, defaults.reversalPremiumDrawdownPercent);
  assert.equal(state.adaptiveTrailingEnabled, defaults.adaptiveTrailingEnabled);
  assert.equal(state.adaptiveTrailingMinPercent, defaults.adaptiveTrailingMinPercent);
  assert.equal(state.adaptiveTrailingMaxPercent, defaults.adaptiveTrailingMaxPercent);
  assert.equal(state.zeroDteLiquidationEnabled, defaults.zeroDteLiquidationEnabled);
  assert.equal(state.zeroDteLiquidationTime, defaults.zeroDteLiquidationTime);
  assert.equal(state.stopLossOrderType, defaults.stopLossOrderType);
  assert.equal(state.trailingStopType, defaults.trailingStopType);
  assert.equal(state.stopLossEnabled, false);
  assert.equal(state.takeProfitEnabled, false);
  assert.equal(state.breakEvenEnabled, false);
  assert.equal(state.breakEvenActivationType, defaults.breakEvenActivationType);
  assert.equal(state.breakEvenActivationPercentage, defaults.breakEvenActivationPercentage);
  assert.equal(state.breakEvenActivationCents, defaults.breakEvenActivationCents);
});
