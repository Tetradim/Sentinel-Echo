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

const { summarizeProfiles } = require('../utils/profilesDigest.ts');

const profiles = [
  {
    id: 'day',
    name: 'Day Trading',
    description: '',
    active_brokers: ['ibkr'],
    created_at: '2026-06-18T12:00:00Z',
    is_active: true,
  },
  {
    id: 'swing',
    name: 'Swing',
    description: '',
    active_brokers: [],
    created_at: '2026-06-18T12:00:00Z',
    is_active: false,
  },
];

const guardedSettings = {
  day: {
    ibkr: {
      broker_id: 'ibkr',
      enabled: true,
      auto_trading_enabled: true,
      alerts_only: false,
      premium_buffer_enabled: true,
      take_profit_enabled: true,
      take_profit_percentage: 50,
      bracket_order_enabled: true,
      stop_loss_enabled: true,
      stop_loss_percentage: 30,
      trailing_stop_enabled: true,
      trailing_stop_percent: 25,
      averaging_down_enabled: false,
      auto_shutdown_enabled: true,
      max_consecutive_losses: 3,
    },
  },
};

test('summarizes the active profile as ready when enabled brokers are guarded', () => {
  const digest = summarizeProfiles(profiles, guardedSettings);

  assert.equal(digest.primaryStatus.title, 'Profile Ready');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.activeProfileName, 'Day Trading');
  assert.equal(digest.enabledBrokers, 1);
  assert.equal(digest.autoTradingBrokers, 1);
  assert.equal(digest.guardedBrokers, 1);
  assert.equal(digest.profileCoveragePercent, 100);
  assert.deepEqual(digest.warningItems, []);
});

test('asks for an active profile before broker settings can matter', () => {
  const digest = summarizeProfiles(
    profiles.map((profile) => ({ ...profile, is_active: false })),
    guardedSettings
  );

  assert.equal(digest.primaryStatus.title, 'Activate Profile');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.activeProfileName, 'None');
  assert.equal(digest.profileCoveragePercent, 0);
  assert.deepEqual(digest.warningItems.map((item) => item.title), ['No active profile']);
});

test('flags an active profile without enabled broker routes', () => {
  const digest = summarizeProfiles(profiles, { day: {} });

  assert.equal(digest.primaryStatus.title, 'No Active Brokers');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.enabledBrokers, 0);
  assert.deepEqual(digest.warningItems.map((item) => item.title), ['No brokers enabled']);
});

test('prioritizes auto trading brokers that are missing exits', () => {
  const digest = summarizeProfiles(profiles, {
    day: {
      ibkr: {
        ...guardedSettings.day.ibkr,
        take_profit_enabled: false,
        stop_loss_enabled: false,
      },
    },
  });

  assert.equal(digest.primaryStatus.title, 'Guardrail Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.enabledBrokers, 1);
  assert.equal(digest.guardedBrokers, 0);
  assert.equal(digest.profileCoveragePercent, 0);
  assert.deepEqual(digest.warningItems.map((item) => item.title), ['Auto broker missing exits']);
});
