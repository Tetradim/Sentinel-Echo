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

const { summarizeTradingSettings } = require('../utils/tradingSettingsDigest.ts');

const guardedSettings = {
  simulationMode: true,
  autoTradingEnabled: true,
  priceBufferEnabled: true,
  priceBufferPercentage: 3,
  orderTimeout: 30,
  retryFilledCheck: true,
  retryInterval: 2,
  activeBroker: 'IBKR',
  brokerGatewayUrl: 'https://localhost:5000',
  brokerAccountId: 'DU12345',
  orderType: 'LIMIT',
};

test('summarizes simulated auto trading with broker safeguards as ready', () => {
  const digest = summarizeTradingSettings(guardedSettings);

  assert.equal(digest.primaryStatus.title, 'Sim Auto-Ready');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.safeguardCount, 5);
  assert.equal(digest.safeguardCoveragePercent, 100);
  assert.equal(digest.modeLabel, 'Simulation');
  assert.equal(digest.bufferLabel, '3%');
  assert.deepEqual(digest.warningItems, []);
});

test('prioritizes broker setup before live auto trading can be trusted', () => {
  const digest = summarizeTradingSettings({
    ...guardedSettings,
    simulationMode: false,
    brokerGatewayUrl: '',
    brokerAccountId: '',
  });

  assert.equal(digest.primaryStatus.title, 'Broker Setup');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.safeguardCoveragePercent, 60);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Broker account missing', 'Gateway URL missing', 'Live auto trading']
  );
});

test('flags unbuffered market execution as an execution review', () => {
  const digest = summarizeTradingSettings({
    ...guardedSettings,
    priceBufferEnabled: false,
    retryFilledCheck: false,
    orderType: 'MARKET',
  });

  assert.equal(digest.primaryStatus.title, 'Execution Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.safeguardCount, 2);
  assert.equal(digest.safeguardCoveragePercent, 40);
  assert.equal(digest.bufferLabel, 'Off');
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Price buffer disabled', 'Fill retry disabled', 'Market orders enabled']
  );
});
