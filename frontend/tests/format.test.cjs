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

const { finiteNumber, formatCurrency } = require('../utils/format.ts');

test('formatCurrency renders missing trade prices without throwing', () => {
  assert.equal(formatCurrency(undefined), '--');
  assert.equal(formatCurrency(null), '--');
  assert.equal(formatCurrency(''), '--');
  assert.equal(formatCurrency('not-a-number'), '--');
});

test('formatCurrency renders numeric API values consistently', () => {
  assert.equal(formatCurrency(0.59), '$0.59');
  assert.equal(formatCurrency('1.2'), '$1.20');
  assert.equal(finiteNumber('1.2'), 1.2);
  assert.equal(finiteNumber(undefined), null);
});
