const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ts = require('typescript');

require.extensions['.ts'] = function loadTs(module, filename) {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  module._compile(output, filename);
};

const {
  TRADING_TEST_PRESETS,
  applyTradingTestPreset,
  diffTradingTestPreset,
  getTradingTestPreset,
  matchesTradingTestPreset,
} = require('../utils/tradingTestPresets.ts');

test('exposes the five approved trading test presets', () => {
  assert.deepEqual(
    TRADING_TEST_PRESETS.map((preset) => preset.id),
    ['runner_capture', 'take_profit_50', 'no_downside_stop', 'mike_directed', 'wide_risk_control'],
  );
});

test('every preset preserves analyst exits and mandatory 0DTE liquidation without overriding the trim choice', () => {
  for (const preset of TRADING_TEST_PRESETS) {
    assert.equal(preset.payload.sell_alert_listening_enabled, true, preset.id);
    assert.equal(Object.hasOwn(preset.payload, 'trim_alert_listening_enabled'), false, preset.id);
    assert.equal(preset.payload.zero_dte_liquidation_enabled, true, preset.id);
    assert.equal(preset.payload.zero_dte_liquidation_time, '15:40', preset.id);
    assert.equal(preset.payload.core_runner_zero_dte_liquidation_enabled, true, preset.id);
    assert.equal(preset.payload.core_runner_zero_dte_liquidation_time, '15:40', preset.id);
    assert.equal(preset.payload.bracket_order_enabled, false, preset.id);
  }
});

test('full take profit preset isolates a complete exit at plus 50 percent', () => {
  const payload = getTradingTestPreset('take_profit_50').payload;

  assert.equal(payload.take_profit_enabled, true);
  assert.equal(payload.take_profit_percentage, 50);
  assert.equal(payload.take_profit_sell_percentage, 100);
  assert.equal(payload.stop_loss_enabled, false);
  assert.equal(payload.break_even_enabled, false);
  assert.equal(payload.trailing_stop_enabled, false);
  assert.equal(payload.coordinated_exit_enabled, false);
  assert.equal(payload.coordinated_loss_ladder_enabled, false);
  assert.equal(payload.core_runner_enabled, false);
  assert.equal(payload.reversal_exit_enabled, false);
  assert.equal(payload.adaptive_trailing_enabled, false);
});

test('no downside stop preserves upside management without a price loss exit', () => {
  const payload = getTradingTestPreset('no_downside_stop').payload;

  assert.equal(payload.take_profit_enabled, false);
  assert.equal(payload.stop_loss_enabled, false);
  assert.equal(payload.break_even_enabled, false);
  assert.equal(payload.trailing_stop_enabled, false);
  assert.equal(payload.coordinated_exit_enabled, true);
  assert.equal(payload.coordinated_loss_ladder_enabled, false);
  assert.equal(payload.coordinated_normal_stop_loss_percent, 100);
  assert.equal(payload.coordinated_high_risk_stop_loss_percent, 100);
  assert.equal(payload.coordinated_emergency_stop_loss_percent, 100);
  assert.equal(payload.core_runner_enabled, true);
  assert.equal(payload.core_runner_catastrophic_stop_percent, 0);
  assert.equal(payload.core_runner_trailing_enabled, true);
  assert.equal(payload.core_runner_trailing_mode, 'tiered');
  assert.equal(payload.coordinated_profit_stage_1_percent, 25);
  assert.equal(payload.coordinated_profit_stage_2_percent, 50);
});

test('applying and diffing a preset clones nested settings without mutating definitions', () => {
  const current = {
    coordinated_loss_ladder: [{ loss_percent: 5, quantity: 100 }],
    core_runner_trailing_tiers: [{ mfe_percent: 50, trail_percent: 10 }],
    stop_loss_enabled: true,
  };
  const draft = applyTradingTestPreset(current, 'runner_capture');
  const changes = diffTradingTestPreset(current, 'runner_capture');

  draft.core_runner_trailing_tiers[0].trail_percent = 99;
  draft.coordinated_loss_ladder[0].loss_percent = 99;

  assert.equal(getTradingTestPreset('runner_capture').payload.core_runner_trailing_tiers[0].trail_percent, 35);
  assert.equal(getTradingTestPreset('runner_capture').payload.coordinated_loss_ladder[0].loss_percent, 15);
  assert.ok(changes.some((change) => change.key === 'stop_loss_enabled'));
  assert.equal(matchesTradingTestPreset(applyTradingTestPreset({}, 'runner_capture'), 'runner_capture'), true);
});

