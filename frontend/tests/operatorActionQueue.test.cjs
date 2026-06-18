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

const { buildOperatorActionQueue } = require('../utils/operatorActionQueue.ts');

const baseReadiness = {
  title: 'Needs Review',
  summary: 'Some setup requires attention.',
  tone: 'attention',
  score: 70,
  primaryAction: {
    label: 'Open Trading',
    target: '/trading-settings',
  },
  items: [
    {
      id: 'broker',
      label: 'Broker',
      detail: 'Broker route is connected.',
      state: 'ready',
      icon: 'briefcase',
    },
    {
      id: 'discord',
      label: 'Discord',
      detail: 'Discord alert ingestion is offline.',
      state: 'attention',
      icon: 'chatbubbles-outline',
      actionLabel: 'Open Discord',
      actionTarget: '/discord-settings',
    },
    {
      id: 'guards',
      label: 'Exit Guards',
      detail: 'No take-profit, stop-loss, or trailing stop guard is enabled.',
      state: 'attention',
      icon: 'shield-outline',
      actionLabel: 'Tune Risk',
      actionTarget: '/risk-settings',
    },
  ],
};

test('builds a ranked action queue from readiness issues', () => {
  const queue = buildOperatorActionQueue({
    ...baseReadiness,
    items: [
      ...baseReadiness.items,
      {
        id: 'shutdown',
        label: 'Shutdown',
        detail: 'Loss limits paused automation.',
        state: 'blocked',
        icon: 'warning',
        actionLabel: 'Review Shutdown',
        actionTarget: '/risk-settings',
      },
    ],
  });

  assert.deepEqual(
    queue.map((action) => [action.label, action.target, action.tone]),
    [
      ['Review Shutdown', '/risk-settings', 'blocked'],
      ['Open Discord', '/discord-settings', 'attention'],
      ['Tune Risk', '/risk-settings', 'attention'],
    ]
  );
});

test('uses high-value monitoring workflows when the bot is ready', () => {
  const queue = buildOperatorActionQueue({
    title: 'Ready',
    summary: 'Live trading path is ready.',
    tone: 'live',
    score: 100,
    primaryAction: {
      label: 'View Trading',
      target: '/trading-settings',
    },
    items: baseReadiness.items.map((item) => ({
      ...item,
      state: 'ready',
      actionLabel: undefined,
      actionTarget: undefined,
    })),
  });

  assert.deepEqual(
    queue.map((action) => [action.label, action.target, action.tone]),
    [
      ['Scan Strikes', '/strike-selection', 'live'],
      ['Review Trades', '/trades', 'live'],
      ['Tune Profiles', '/profiles', 'live'],
    ]
  );
});

test('limits the dashboard queue to three actions', () => {
  const queue = buildOperatorActionQueue({
    ...baseReadiness,
    items: [
      ...baseReadiness.items,
      {
        id: 'automation',
        label: 'Automation',
        detail: 'Auto trading is paused.',
        state: 'attention',
        icon: 'flash-outline',
        actionLabel: 'Open Trading',
        actionTarget: '/trading-settings',
      },
      {
        id: 'broker',
        label: 'Broker',
        detail: 'Broker is offline or not configured.',
        state: 'blocked',
        icon: 'briefcase-outline',
        actionLabel: 'Configure Broker',
        actionTarget: '/broker-config',
      },
    ],
  });

  assert.equal(queue.length, 3);
});
