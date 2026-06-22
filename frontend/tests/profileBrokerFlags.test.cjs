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

const {
  getProfileBrokerSummary,
  parseProfileBrokerFlags,
} = require('../utils/profileBrokerFlags.ts');

test('parses string booleans for profile broker settings', () => {
  const flags = parseProfileBrokerFlags({
    enabled: 'false',
    auto_trading_enabled: 'true',
    alerts_only: 'false',
    premium_buffer_enabled: 'false',
    take_profit_enabled: '0',
    bracket_order_enabled: 'false',
    stop_loss_enabled: 'no',
    trailing_stop_enabled: 'false',
    averaging_down_enabled: 'false',
    auto_shutdown_enabled: 'false',
  });

  assert.deepEqual(flags, {
    enabled: false,
    autoTradingEnabled: true,
    alertsOnly: false,
    premiumBufferEnabled: false,
    takeProfitEnabled: false,
    bracketOrderEnabled: false,
    stopLossEnabled: false,
    trailingStopEnabled: false,
    averagingDownEnabled: false,
    autoShutdownEnabled: false,
  });
  assert.equal(getProfileBrokerSummary({ enabled: 'false', auto_trading_enabled: 'true' }), null);
});

test('builds broker summary from parsed flags', () => {
  assert.equal(getProfileBrokerSummary({
    enabled: 'true',
    alerts_only: 'false',
    auto_trading_enabled: 'true',
    bracket_order_enabled: 'false',
    trailing_stop_enabled: 'true',
    take_profit_enabled: 'true',
    stop_loss_enabled: 'false',
  }), 'Auto • Trail • TP');

  assert.equal(getProfileBrokerSummary({
    enabled: 'true',
    alerts_only: 'true',
    auto_trading_enabled: 'true',
    take_profit_enabled: 'false',
  }), 'Alerts Only');
});
