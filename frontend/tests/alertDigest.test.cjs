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
  filterAlerts,
  getAlertActionSummary,
  getAlertExecutionStatus,
  getAlertReasonLabel,
  getAlertSourceSummary,
  getExitTriggerLabel,
  summarizeAlerts,
} = require('../utils/alertDigest.ts');

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
    skip_reason: 'blocked: max positions per ticker',
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
  {
    id: '4',
    ticker: 'SPY',
    processed: true,
    trade_executed: true,
    alert_type: 'sell',
    sell_percentage: 80,
    exit_trigger: 'sell_alert',
    source_name: 'MikesTrades mirror-alerts',
    channel_name: 'mirror-alerts',
    author_name: 'MikeInvesting',
    trade_result: 'sold 80%',
    received_at: '2026-06-18T14:05:00Z',
  },
];

test('summarizes alert execution and review counts', () => {
  const digest = summarizeAlerts(alerts);

  assert.equal(digest.total, 4);
  assert.equal(digest.executed, 2);
  assert.equal(digest.needsReview, 2);
  assert.equal(digest.unparsed, 1);
  assert.equal(digest.skipped, 1);
  assert.equal(digest.exits, 1);
  assert.equal(digest.executionRate, 50);
  assert.equal(digest.topTicker, 'SPY');
  assert.equal(digest.primaryStatus.title, 'Parser Review');
});

test('filters alerts by execution, review, and unparsed states', () => {
  assert.equal(filterAlerts(alerts, 'all').length, 4);
  assert.equal(filterAlerts(alerts, 'executed').length, 2);
  assert.deepEqual(filterAlerts(alerts, 'review').map((alert) => alert.id), ['2', '3']);
  assert.deepEqual(filterAlerts(alerts, 'skipped').map((alert) => alert.id), ['2']);
  assert.deepEqual(filterAlerts(alerts, 'unparsed').map((alert) => alert.id), ['3']);
  assert.deepEqual(filterAlerts(alerts, 'exits').map((alert) => alert.id), ['4']);
});

test('parses string booleans for alert execution and parsing states', () => {
  const stringBackedAlerts = [
    { id: 'string-executed', ticker: 'QQQ', processed: 'true', trade_executed: 'true' },
    { id: 'string-review', ticker: 'QQQ', processed: 'true', trade_executed: 'false' },
    { id: 'string-unparsed', ticker: 'IWM', processed: 'false', trade_executed: 'false' },
  ];

  const digest = summarizeAlerts(stringBackedAlerts);

  assert.equal(digest.executed, 1);
  assert.equal(digest.needsReview, 2);
  assert.equal(digest.unparsed, 1);
  assert.equal(digest.executionRate, 33);
  assert.deepEqual(filterAlerts(stringBackedAlerts, 'executed').map((alert) => alert.id), ['string-executed']);
  assert.deepEqual(filterAlerts(stringBackedAlerts, 'review').map((alert) => alert.id), ['string-review', 'string-unparsed']);
  assert.deepEqual(filterAlerts(stringBackedAlerts, 'unparsed').map((alert) => alert.id), ['string-unparsed']);
});

test('builds row status from parsed alert booleans', () => {
  assert.equal(getAlertExecutionStatus({
    id: 'skipped',
    processed: 'true',
    trade_executed: 'false',
    skip_reason: 'sell alert listening disabled',
  }).label, 'Skipped');

  assert.equal(getAlertExecutionStatus({
    id: 'review',
    processed: 'true',
    trade_executed: 'false',
  }).label, 'Review');

  assert.equal(getAlertExecutionStatus({
    id: 'unparsed',
    processed: 'false',
    trade_executed: 'false',
  }).label, 'Unparsed');

  assert.equal(getAlertExecutionStatus({
    id: 'executed',
    processed: 'true',
    trade_executed: '1',
  }).label, 'Executed');
});

test('builds enriched alert source, action, reason, and exit trigger labels', () => {
  const exitAlert = alerts[3];

  assert.equal(getAlertSourceSummary(exitAlert), 'MikesTrades mirror-alerts / MikeInvesting');
  assert.equal(getAlertActionSummary(exitAlert), 'Exit 80%');
  assert.equal(getExitTriggerLabel(exitAlert), 'Sell alert');
  assert.equal(getAlertReasonLabel(alerts[1]), 'blocked: max positions per ticker');
  assert.equal(getAlertReasonLabel(exitAlert), 'sold 80%');
});

test('returns a calm empty digest for no alerts', () => {
  const digest = summarizeAlerts([]);

  assert.equal(digest.total, 0);
  assert.equal(digest.executionRate, 0);
  assert.equal(digest.topTicker, null);
  assert.equal(digest.primaryStatus.title, 'Listening');
});
