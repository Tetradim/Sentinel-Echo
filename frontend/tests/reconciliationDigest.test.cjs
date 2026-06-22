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

const { summarizeReconciliation } = require('../utils/reconciliationDigest.ts');

test('reconciliation digest counts attention and pending chains', () => {
  const digest = summarizeReconciliation([
    { alert_id: 'a1', trade_status: 'pending', simulated: false, attention_reason: 'order pending fill' },
    { alert_id: 'a2', trade_status: 'simulated', simulated: true, attention_reason: '' },
  ]);

  assert.equal(digest.title, 'Reconciliation Review');
  assert.equal(digest.total, 2);
  assert.equal(digest.attentionCount, 1);
  assert.equal(digest.pendingCount, 1);
  assert.equal(digest.liveCount, 1);
});

test('reconciliation digest reports clear state', () => {
  const digest = summarizeReconciliation([
    { alert_id: 'a1', trade_status: 'filled', simulated: false, attention_reason: '' },
  ]);

  assert.equal(digest.title, 'Reconciliation Clear');
  assert.equal(digest.attentionCount, 0);
});
