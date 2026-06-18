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

const { summarizeRiskSettings } = require('../utils/riskDigest.ts');

const guardedSettings = {
  maxPositionSize: 1000,
  defaultQuantity: 1,
  riskPerTrade: 1,
  stopLossEnabled: true,
  stopLossPercentage: 30,
  takeProfitEnabled: true,
  takeProfitPercentage: 50,
  trailingStopEnabled: true,
  trailingStopPercent: 25,
  autoShutdownEnabled: true,
  maxConsecutiveLosses: 3,
  maxDailyLosses: 5,
  maxDailyLossAmount: 500,
  maxDrawdownPercent: 20,
  maxPositionsPerTicker: 3,
  maxPositionsPerSector: 3,
};

test('summarizes fully guarded risk settings as ready', () => {
  const digest = summarizeRiskSettings(guardedSettings);

  assert.equal(digest.primaryStatus.title, 'Guarded');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.enabledGuards, 6);
  assert.equal(digest.guardCoveragePercent, 100);
  assert.equal(digest.riskPerTradeLabel, '1%');
  assert.deepEqual(digest.warningItems, []);
});

test('flags missing exits and shutdown controls as guardrail gaps', () => {
  const digest = summarizeRiskSettings({
    ...guardedSettings,
    stopLossEnabled: false,
    takeProfitEnabled: false,
    trailingStopEnabled: false,
    autoShutdownEnabled: false,
    maxPositionsPerTicker: 0,
    maxPositionsPerSector: 0,
  });

  assert.equal(digest.primaryStatus.title, 'Needs Guardrails');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.enabledGuards, 0);
  assert.equal(digest.guardCoveragePercent, 0);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    [
      'Stop loss disabled',
      'Take profit disabled',
      'Trailing stop disabled',
      'Auto shutdown disabled',
      'Ticker cap missing',
      'Sector cap missing',
    ]
  );
});

test('prioritizes sizing risk when allocation settings are too aggressive', () => {
  const digest = summarizeRiskSettings({
    ...guardedSettings,
    riskPerTrade: 3.5,
    maxPositionSize: 7500,
  });

  assert.equal(digest.primaryStatus.title, 'Sizing Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.guardCoveragePercent, 100);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Risk per trade high', 'Position size high']
  );
});
