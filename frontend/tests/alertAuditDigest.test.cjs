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

const { summarizeBridgeAlertDecisions } = require('../utils/alertAuditDigest.ts');

test('bridge alert digest summarizes accepted and skipped audit events', () => {
  const digest = summarizeBridgeAlertDecisions([
    {
      id: 'evt-skip',
      timestamp: '2026-06-22T14:23:00Z',
      action: 'bridge_alert_decision',
      summary: 'Chrome bridge alert skipped: parser confidence low below required medium',
      severity: 'warning',
      details: {
        channel: { name: 'mike-alerts', url: 'https://discord.com/channels/1/2' },
        author: { name: 'MikeInvesting', id: 'mike' },
        parsed: { ticker: 'SPY', option_type: 'PUT', strike: 744, expiration: '2026-06-22' },
        parser: { confidence: 'low' },
        source: { key: 'mike-alerts', name: 'MikeInvesting' },
        decision: { status: 'skipped', skip_reason: 'parser confidence low below required medium' },
      },
    },
    {
      id: 'evt-accept',
      timestamp: '2026-06-22T14:26:00Z',
      action: 'bridge_alert_decision',
      summary: 'Chrome bridge alert accepted.',
      severity: 'info',
      details: {
        channel: { id: '2' },
        author: { id: 'mike' },
        parsed: { ticker: 'QQQ' },
        parser: { confidence: 'high' },
        decision: { status: 'inserted', trade_requested: true },
      },
    },
    {
      id: 'evt-other',
      timestamp: '2026-06-22T14:27:00Z',
      action: 'test_alert_created',
      summary: 'ignore',
    },
  ]);

  assert.equal(digest.total, 2);
  assert.equal(digest.acceptedCount, 1);
  assert.equal(digest.skippedCount, 1);
  assert.equal(digest.title, 'Bridge Alerts Need Review');
  assert.equal(digest.stateLabel, 'Review');
  assert.match(digest.detail, /1 skipped/);
  assert.equal(digest.rows[0].status, 'skipped');
  assert.equal(digest.rows[0].tickerLabel, 'SPY 744 PUT 2026-06-22');
  assert.equal(digest.rows[0].channelLabel, 'mike-alerts');
  assert.equal(digest.rows[0].sourceLabel, 'MikeInvesting');
  assert.equal(digest.rows[1].status, 'accepted');
  assert.equal(digest.rows[1].channelLabel, '2');
});

test('bridge alert digest reports quiet state when no audit events exist', () => {
  const digest = summarizeBridgeAlertDecisions([]);

  assert.equal(digest.total, 0);
  assert.equal(digest.title, 'No Bridge Alerts');
  assert.equal(digest.stateLabel, 'Idle');
  assert.equal(digest.detail, 'No Chrome bridge alert decisions are in the current event window.');
});
