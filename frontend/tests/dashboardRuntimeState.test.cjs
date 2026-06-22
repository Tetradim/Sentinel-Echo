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

const { normalizeDashboardRuntimeState } = require('../utils/dashboardRuntimeState.ts');

test('normalizes string booleans from dashboard settings responses', () => {
  const state = normalizeDashboardRuntimeState({
    status: { auto_trading_enabled: 'false' },
    settings: { simulation_mode: 'false' },
    averagingDown: { averaging_down_enabled: 'false' },
    risk: {
      take_profit_enabled: 'false',
      stop_loss_enabled: '0',
      take_profit_percentage: '55',
      stop_loss_percentage: '20',
    },
    trailing: { trailing_stop_enabled: 'false', trailing_stop_percent: '12' },
    shutdown: {
      auto_shutdown_enabled: 'false',
      max_consecutive_losses: '4',
      max_daily_losses: '6',
      max_daily_loss_amount: '750',
      consecutive_losses: '1',
      daily_losses: '2',
      shutdown_triggered: 'false',
      shutdown_reason: 'operator reset',
    },
    premium: { premium_buffer_enabled: 'false', premium_buffer_amount: '15' },
  });

  assert.equal(state.autoTrading, false);
  assert.equal(state.simMode, false);
  assert.equal(state.avgDown, false);
  assert.equal(state.takeProfit, false);
  assert.equal(state.stopLoss, false);
  assert.equal(state.trailingStop, false);
  assert.equal(state.autoShutdown, false);
  assert.equal(state.shutdownSettings.shutdown_triggered, false);
  assert.equal(state.premiumBuffer, false);
  assert.equal(state.premiumBufferAmt, 15);
  assert.deepEqual(state.riskSettings, {
    take_profit_percentage: 55,
    stop_loss_percentage: 20,
  });
  assert.deepEqual(state.trailingSettings, { trailing_stop_percent: 12 });
  assert.deepEqual(state.shutdownSettings, {
    max_consecutive_losses: 4,
    max_daily_losses: 6,
    max_daily_loss_amount: 750,
    consecutive_losses: 1,
    daily_losses: 2,
    shutdown_triggered: false,
    shutdown_reason: 'operator reset',
  });
});

test('prefers status simulation mode and falls back to settings when absent', () => {
  assert.equal(normalizeDashboardRuntimeState({
    status: { simulation_mode: 'false' },
    settings: { simulation_mode: 'true' },
  }).simMode, false);

  assert.equal(normalizeDashboardRuntimeState({
    status: {},
    settings: { simulation_mode: 'true' },
  }).simMode, true);
});
