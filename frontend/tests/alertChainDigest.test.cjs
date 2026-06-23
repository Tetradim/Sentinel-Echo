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

const { summarizeAlertChains } = require('../utils/alertChainDigest.ts');

test('alert chain digest summarizes deterministic proof stages', () => {
  const digest = summarizeAlertChains({
    summary: {
      total: 2,
      seen_count: 2,
      parsed_count: 2,
      accepted_count: 1,
      alert_inserted_count: 1,
      trade_requested_count: 1,
      trade_linked_count: 1,
      position_linked_count: 1,
      attention_count: 1,
      deterministic: false,
    },
    rows: [
      {
        chain_key: 'bridge:accepted',
        source: 'chrome_bridge',
        channel_id: 'chrome-alerts',
        channel_url: 'https://discord.com/channels/1/chrome-alerts',
        author_id: 'mike',
        source_key: 'chrome-alerts',
        source_override_matched: true,
        parser_confidence: 'medium',
        min_parser_confidence: 'medium',
        ticker: 'SPY',
        strike: 500,
        option_type: 'CALL',
        expiration: '6/21',
        entry_price: 1.25,
        alert_id: 'alert-1',
        trade_id: 'trade-1',
        position_id: 'position-1',
        status: 'reconciled',
        deterministic: true,
      },
      {
        chain_key: 'bridge:attention',
        source: 'chrome_bridge',
        ticker: 'QQQ',
        status: 'attention',
        attention_reason: 'accepted bridge alert missing alert id',
        deterministic: 'false',
      },
    ],
  });

  assert.equal(digest.title, 'Alert Chain Review');
  assert.equal(digest.stateLabel, 'Review');
  assert.equal(digest.total, 2);
  assert.equal(digest.attentionCount, 1);
  assert.equal(digest.stageCounts.seen, 2);
  assert.equal(digest.stageCounts.placed, 1);
  assert.equal(digest.stageCounts.reconciled, 1);
  assert.equal(digest.rows[0].tickerLabel, 'SPY 500 CALL 6/21');
  assert.equal(digest.rows[0].sourceEvidenceLabel, 'chrome-alerts / mike / source chrome-alerts verified / parser medium>=medium');
  assert.equal(digest.rows[1].deterministic, false);
  assert.equal(digest.rows[1].attentionReason, 'accepted bridge alert missing alert id');
});

test('alert chain digest reports idle state for empty or malformed reports', () => {
  const digest = summarizeAlertChains('not a report');

  assert.equal(digest.title, 'No Alert Chains');
  assert.equal(digest.stateLabel, 'Idle');
  assert.equal(digest.total, 0);
  assert.equal(digest.detail, 'No alert chain proof rows are in the current report window.');
});
