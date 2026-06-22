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
  stopLossEnabled: true,
  stopLossPercentage: 30,
  stopLossOrderType: 'market',
  takeProfitEnabled: true,
  takeProfitPercentage: 50,
  multiLevelTakeProfit: true,
  trailingStopEnabled: true,
  trailingStopType: 'percent',
  trailingStopPercent: 25,
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
      bracket_order_enabled: 'false',
    },
    trailing: {
      trailing_stop_enabled: 'false',
      trailing_stop_type: 'cents',
      trailing_stop_percent: '12',
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
  assert.equal(state.takeProfitEnabled, false);
  assert.equal(state.multiLevelTakeProfit, false);
  assert.equal(state.trailingStopEnabled, false);
  assert.equal(state.autoShutdownEnabled, false);
  assert.equal(state.maxPositionSize, 2500);
  assert.equal(state.defaultQuantity, 2);
  assert.equal(state.riskPerTrade, 1.5);
  assert.equal(state.stopLossPercentage, 20);
  assert.equal(state.takeProfitPercentage, 40);
  assert.equal(state.trailingStopType, 'cents');
  assert.equal(state.trailingStopPercent, 12);
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
  assert.equal(state.stopLossOrderType, defaults.stopLossOrderType);
  assert.equal(state.trailingStopType, defaults.trailingStopType);
  assert.equal(state.stopLossEnabled, false);
  assert.equal(state.takeProfitEnabled, false);
});
