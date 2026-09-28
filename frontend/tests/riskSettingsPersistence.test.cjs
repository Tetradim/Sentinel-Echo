const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('risk settings screen loads and saves backend configuration', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'risk-settings.tsx'), 'utf8');

  assert.match(source, /import \{ api \} from '\.\.\/utils\/api'/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/risk-management-settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/trailing-stop-settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/auto-shutdown-settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/correlation-settings`\)/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/risk-management-settings`/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/trailing-stop-settings`/);
  assert.match(source, /trailing_stop_activation_percent:\s*settings\.trailingStopActivationPercent/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/auto-shutdown-settings`/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/correlation-settings\?/);
  assert.match(source, /smart_sizing_enabled:\s*settings\.smartSizingEnabled/);
  assert.match(source, /smart_sizing_agreement_percent:\s*settings\.smartSizingAgreementPercent/);
  assert.match(source, /smart_sizing_mixed_percent:\s*settings\.smartSizingMixedPercent/);
  assert.match(source, /smart_sizing_conflict_percent:\s*settings\.smartSizingConflictPercent/);
  assert.match(source, /entry_slippage_sizing_enabled:\s*settings\.entrySlippageSizingEnabled/);
  assert.match(source, /entry_slippage_mode:\s*settings\.entrySlippageMode/);
  assert.match(source, /entry_slippage_warning_percent:\s*settings\.entrySlippageWarningPercent/);
  assert.match(source, /entry_slippage_severe_percent:\s*settings\.entrySlippageSeverePercent/);
  assert.match(source, /entry_slippage_warning_size_percent:\s*settings\.entrySlippageWarningSizePercent/);
  assert.match(source, /entry_slippage_severe_size_percent:\s*settings\.entrySlippageSevereSizePercent/);
  assert.match(source, /marketable_entry_enabled:\s*settings\.marketableEntryEnabled/);
  assert.match(source, /coordinated_fast_scalp_profit_stage_1_percent:\s*settings\.coordinatedFastScalpProfitStage1Percent/);
  assert.match(source, /coordinated_fast_scalp_profit_stage_2_percent:\s*settings\.coordinatedFastScalpProfitStage2Percent/);
  assert.match(source, /coordinated_emergency_stop_loss_percent:\s*settings\.coordinatedEmergencyStopLossPercent/);
  assert.match(source, /coordinated_stop_required_confirmations:\s*settings\.coordinatedStopRequiredConfirmations/);
  assert.match(source, /coordinated_stop_confirmation_interval_seconds:\s*settings\.coordinatedStopConfirmationIntervalSeconds/);
  assert.match(source, /coordinated_runner_reserve_quantity:\s*settings\.coordinatedRunnerReserveQuantity/);
  assert.match(source, /coordinated_progressive_trailing_enabled:\s*settings\.coordinatedProgressiveTrailingEnabled/);
  assert.match(source, /coordinated_trailing_mode:\s*settings\.coordinatedTrailingMode/);
  assert.match(source, /coordinated_elastic_activation_percent:\s*settings\.coordinatedElasticActivationPercent/);
  assert.match(source, /coordinated_loss_ladder_enabled:\s*settings\.coordinatedLossLadderEnabled/);
  assert.match(source, /coordinated_loss_ladder:\s*settings\.coordinatedLossLadder/);
  assert.match(source, /coordinated_trailing_step_gain_percent:\s*settings\.coordinatedTrailingStepGainPercent/);
  assert.match(source, /coordinated_trailing_step_tighten_percent:\s*settings\.coordinatedTrailingStepTightenPercent/);
  assert.match(source, /coordinated_trailing_min_percent:\s*settings\.coordinatedTrailingMinPercent/);
  assert.match(source, /coordinated_trailing_volatility_gate_percent:\s*settings\.coordinatedTrailingVolatilityGatePercent/);
  assert.match(source, /fill_confirmation_timeout_seconds:\s*settings\.fillConfirmationTimeoutSeconds/);
  assert.match(source, /exit_reprice_interval_seconds:\s*settings\.exitRepriceIntervalSeconds/);
  assert.match(source, /profit_exit_reprice_interval_seconds:\s*settings\.profitExitRepriceIntervalSeconds/);
  assert.match(source, /reversal_exit_enabled:\s*settings\.reversalExitEnabled/);
  assert.match(source, /reversal_warning_confirmations:\s*settings\.reversalWarningConfirmations/);
  assert.match(source, /reversal_confirmed_confirmations:\s*settings\.reversalConfirmedConfirmations/);
  assert.match(source, /reversal_warning_sell_percent:\s*settings\.reversalWarningSellPercent/);
  assert.match(source, /reversal_premium_drawdown_percent:\s*settings\.reversalPremiumDrawdownPercent/);
  assert.match(source, /reversal_reduce_min_return_percent:\s*settings\.reversalReduceMinReturnPercent/);
  assert.match(source, /reversal_reduce_min_mfe_percent:\s*settings\.reversalReduceMinMfePercent/);
  assert.match(source, /adaptive_trailing_enabled:\s*settings\.adaptiveTrailingEnabled/);
  assert.match(source, /adaptive_trailing_min_percent:\s*settings\.adaptiveTrailingMinPercent/);
  assert.match(source, /adaptive_trailing_max_percent:\s*settings\.adaptiveTrailingMaxPercent/);
  assert.match(source, /zero_dte_liquidation_enabled:\s*settings\.zeroDteLiquidationEnabled/);
  assert.match(source, /zero_dte_liquidation_time:\s*settings\.zeroDteLiquidationTime/);
});

test('risk settings cannot save defaults before a successful backend load', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'risk-settings.tsx'), 'utf8');

  assert.match(source, /const \[settingsLoaded, setSettingsLoaded\] = useState\(false\)/);
  assert.match(source, /setSettingsLoaded\(true\)/);
  assert.match(source, /if \(!settingsLoaded\) \{/);
  assert.match(source, /disabled=\{saving \|\| !settingsLoaded \|\| hasInvalidSettings\}/);
});
