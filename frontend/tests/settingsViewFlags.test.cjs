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

const { parseSettingsViewFlags } = require('../utils/settingsViewFlags.ts');

test('parses string booleans for settings screen switches and panels', () => {
  const flags = parseSettingsViewFlags({
    auto_trading_enabled: 'false',
    simulation_mode: 'false',
    premium_buffer_enabled: '0',
    averaging_down_enabled: 'no',
    take_profit_enabled: 'false',
    bracket_order_enabled: 'false',
    stop_loss_enabled: 'false',
    trailing_stop_enabled: 'false',
    auto_shutdown_enabled: 'false',
    sms_enabled: 'false',
  });

  assert.deepEqual(flags, {
    autoTradingEnabled: false,
    simulationMode: false,
    premiumBufferEnabled: false,
    averagingDownEnabled: false,
    takeProfitEnabled: false,
    bracketOrderEnabled: false,
    stopLossEnabled: false,
    trailingStopEnabled: false,
    autoShutdownEnabled: false,
    smsEnabled: false,
  });
});

test('defaults missing settings screen flags to false', () => {
  assert.deepEqual(parseSettingsViewFlags(null), {
    autoTradingEnabled: false,
    simulationMode: false,
    premiumBufferEnabled: false,
    averagingDownEnabled: false,
    takeProfitEnabled: false,
    bracketOrderEnabled: false,
    stopLossEnabled: false,
    trailingStopEnabled: false,
    autoShutdownEnabled: false,
    smsEnabled: false,
  });
});
