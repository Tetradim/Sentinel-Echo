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

const { buildPremiumBufferSettingsParams } = require('../utils/settingsPayload.ts');

test('premium buffer save params include enabled flag and amount', () => {
  assert.deepEqual(
    buildPremiumBufferSettingsParams({
      premium_buffer_enabled: false,
      premium_buffer_amount: 15,
    }),
    {
      premium_buffer_enabled: false,
      premium_buffer_amount: 15,
    }
  );
});

test('premium buffer save params parse string false as disabled', () => {
  assert.deepEqual(
    buildPremiumBufferSettingsParams({
      premium_buffer_enabled: 'false',
      premium_buffer_amount: '15',
    }),
    {
      premium_buffer_enabled: false,
      premium_buffer_amount: 15,
    }
  );
});
