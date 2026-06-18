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

const { buildDashboardReadiness } = require('../utils/dashboardReadiness.ts');

const readyInput = {
  status: {
    discord_connected: true,
    broker_connected: true,
    auto_trading_enabled: true,
  },
  simMode: false,
  autoShutdownEnabled: true,
  shutdownTriggered: false,
  takeProfitEnabled: true,
  stopLossEnabled: true,
  trailingStopEnabled: true,
  premiumBufferEnabled: true,
};

test('flags configured exit guards when active automation support is missing', () => {
  const readiness = buildDashboardReadiness(readyInput);

  assert.equal(readiness.tone, 'attention');
  assert.equal(readiness.title, 'Needs Review');
  assert.match(readiness.summary, /Exit guard settings are configured/);
  assert.equal(readiness.primaryAction.label, 'Tune Risk');
});

test('marks the dashboard live-ready when active exit automation support is explicit', () => {
  const readiness = buildDashboardReadiness({
    ...readyInput,
    liveExitAutomationSupported: true,
  });

  assert.equal(readiness.tone, 'live');
  assert.equal(readiness.score, 100);
  assert.equal(readiness.title, 'Ready');
  assert.match(readiness.summary, /Live trading path/);
  assert.equal(readiness.primaryAction.label, 'View Trading');
});

test('prioritizes a broker configuration action when the broker is disconnected', () => {
  const readiness = buildDashboardReadiness({
    ...readyInput,
    status: {
      ...readyInput.status,
      broker_connected: false,
    },
  });

  assert.equal(readiness.tone, 'blocked');
  assert.equal(readiness.title, 'Intervention Needed');
  assert.equal(readiness.primaryAction.label, 'Configure Broker');
  assert.equal(readiness.primaryAction.target, '/broker-config');
});

test('surfaces shutdown review before lower priority warnings', () => {
  const readiness = buildDashboardReadiness({
    ...readyInput,
    shutdownTriggered: true,
    takeProfitEnabled: false,
    stopLossEnabled: false,
  });

  assert.equal(readiness.tone, 'blocked');
  assert.equal(readiness.primaryAction.label, 'Review Shutdown');
  assert.equal(readiness.primaryAction.target, '/risk-settings');
  assert.equal(readiness.items[0].id, 'shutdown');
});

test('flags missing exit guards while keeping the bot in review state', () => {
  const readiness = buildDashboardReadiness({
    ...readyInput,
    takeProfitEnabled: false,
    stopLossEnabled: false,
    trailingStopEnabled: false,
    premiumBufferEnabled: false,
  });

  const guardItem = readiness.items.find((item) => item.id === 'guards');

  assert.equal(readiness.tone, 'attention');
  assert.equal(guardItem.state, 'attention');
  assert.equal(guardItem.actionLabel, 'Tune Risk');
});
