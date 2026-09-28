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

const { summarizeSettings } = require('../utils/settingsDigest.ts');

const guardedSettings = {
  discord_token: 'token',
  discord_channel_ids: ['111', '222'],
  active_broker: 'IBKR',
  auto_trading_enabled: true,
  simulation_mode: true,
  take_profit_enabled: true,
  stop_loss_enabled: true,
  trailing_stop_enabled: true,
  auto_shutdown_enabled: true,
  premium_buffer_enabled: true,
  sms_enabled: false,
};

const guardedPatterns = {
  buy_patterns: ['BTO', 'BUY'],
  sell_patterns: ['STC', 'SELL'],
  partial_sell_patterns: ['TRIM'],
  average_down_patterns: ['AVG DOWN'],
  stop_loss_patterns: ['STOP'],
  take_profit_patterns: ['TARGET'],
  ignore_patterns: ['WATCHLIST', 'PAPER'],
  case_sensitive: false,
};

test('summarizes a simulated guarded configuration as ready', () => {
  const digest = summarizeSettings(guardedSettings, guardedPatterns);

  assert.equal(digest.primaryStatus.title, 'Simulation Guarded');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.guardrailCount, 5);
  assert.equal(digest.guardrailCoveragePercent, 100);
  assert.equal(digest.notificationLabel, 'In-app only');
  assert.deepEqual(digest.warningItems, []);
});

test('leaves Discord and parser setup to the Discord readiness screen', () => {
  const digest = summarizeSettings({
    ...guardedSettings,
    discord_token: '',
    discord_channel_ids: [],
    stop_loss_enabled: false,
  }, {
    ...guardedPatterns,
    buy_patterns: [],
    ignore_patterns: [],
  });

  assert.equal(digest.primaryStatus.title, 'Guardrail Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Stop loss disabled']
  );
});

test('flags live automation as an operator review even when guardrails are present', () => {
  const digest = summarizeSettings({
    ...guardedSettings,
    simulation_mode: false,
  }, guardedPatterns);

  assert.equal(digest.primaryStatus.title, 'Live Auto Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.modeLabel, 'Live auto');
  assert.deepEqual(digest.warningItems.map((item) => item.title), ['Live auto trading']);
});

test('treats string false settings flags as disabled', () => {
  const digest = summarizeSettings({
    ...guardedSettings,
    auto_trading_enabled: 'false',
    simulation_mode: 'false',
    take_profit_enabled: 'false',
    stop_loss_enabled: 'false',
    auto_shutdown_enabled: 'false',
    premium_buffer_enabled: 'false',
    sms_enabled: 'false',
    sms_phone_number: '555-111-2222',
  }, guardedPatterns);

  assert.equal(digest.primaryStatus.title, 'Guardrail Review');
  assert.equal(digest.modeLabel, 'Manual');
  assert.equal(digest.guardrailCount, 0);
  assert.equal(digest.guardrailCoveragePercent, 0);
  assert.equal(digest.notificationLabel, 'In-app only');
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    [
      'Stop loss disabled',
      'Take profit disabled',
      'Auto shutdown disabled',
      'Premium buffer disabled',
    ]
  );
});

test('does not surface parser coverage in the general settings digest', () => {
  const digest = summarizeSettings(guardedSettings, {
    ...guardedPatterns,
    sell_patterns: [],
    ignore_patterns: [],
  });

  assert.equal(digest.primaryStatus.title, 'Simulation Guarded');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.deepEqual(digest.warningItems, []);
});
