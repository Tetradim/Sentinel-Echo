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

const { filterAlerts, summarizeAlerts } = require('../utils/alertDigest.ts');

const alerts = [
  {
    id: '1',
    ticker: 'SPY',
    processed: true,
    trade_executed: true,
    channel_name: 'alerts',
    received_at: '2026-06-18T14:30:00Z',
  },
  {
    id: '2',
    ticker: 'SPY',
    processed: true,
    trade_executed: false,
    channel_name: 'alerts',
    received_at: '2026-06-18T14:20:00Z',
  },
  {
    id: '3',
    ticker: 'AAPL',
    processed: false,
    trade_executed: false,
    channel_name: 'swing',
    received_at: '2026-06-18T14:10:00Z',
  },
];

test('summarizes alert execution and review counts', () => {
  const digest = summarizeAlerts(alerts);

  assert.equal(digest.total, 3);
  assert.equal(digest.executed, 1);
  assert.equal(digest.needsReview, 2);
  assert.equal(digest.unparsed, 1);
  assert.equal(digest.executionRate, 33);
  assert.equal(digest.topTicker, 'SPY');
  assert.equal(digest.primaryStatus.title, 'Parser Review');
});

test('filters alerts by execution, review, and unparsed states', () => {
  assert.equal(filterAlerts(alerts, 'all').length, 3);
  assert.equal(filterAlerts(alerts, 'executed').length, 1);
  assert.deepEqual(filterAlerts(alerts, 'review').map((alert) => alert.id), ['2', '3']);
  assert.deepEqual(filterAlerts(alerts, 'unparsed').map((alert) => alert.id), ['3']);
});

test('returns a calm empty digest for no alerts', () => {
  const digest = summarizeAlerts([]);

  assert.equal(digest.total, 0);
  assert.equal(digest.executionRate, 0);
  assert.equal(digest.topTicker, null);
  assert.equal(digest.primaryStatus.title, 'Listening');
});
