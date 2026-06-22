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

const { parseBooleanFlag } = require('../utils/booleanFlags.ts');

test('boolean flag parser handles common true values', () => {
  for (const value of [true, 1, 'true', '1', 'yes', 'Y', ' on ']) {
    assert.equal(parseBooleanFlag(value), true);
  }
});

test('boolean flag parser handles common false values', () => {
  for (const value of [false, 0, 'false', '0', 'no', 'N', ' off ']) {
    assert.equal(parseBooleanFlag(value), false);
  }
});

test('boolean flag parser falls back for ambiguous values', () => {
  assert.equal(parseBooleanFlag(undefined), false);
  assert.equal(parseBooleanFlag('enabled'), false);
  assert.equal(parseBooleanFlag('enabled', true), true);
  assert.equal(parseBooleanFlag(2, true), true);
});
