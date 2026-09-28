const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ts = require('typescript');

require.extensions['.ts'] = function loadTs(module, filename) {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  module._compile(output, filename);
};

const {
  normalizeRunnerSettings,
  toRunnerSettingsPayload,
  validateRunnerSettings,
} = require('../utils/runnerSettingsState.ts');

test('normalizes string booleans, zero stop, and tiers', () => {
  const state = normalizeRunnerSettings({
    core_runner_enabled: 'true',
    core_runner_catastrophic_stop_percent: 0,
    core_runner_trailing_tiers: [{ mfe_percent: '100', trail_percent: '35' }],
  });

  assert.equal(state.enabled, true);
  assert.equal(state.catastrophicStopPercent, 0);
  assert.deepEqual(state.trailingTiers, [{ mfe_percent: 100, trail_percent: 35 }]);
});

test('serializes the complete runner settings contract', () => {
  const state = normalizeRunnerSettings({ core_runner_enabled: true });
  const payload = toRunnerSettingsPayload(state);

  assert.equal(payload.core_runner_enabled, true);
  assert.equal(payload.core_runner_catastrophic_stop_percent, 65);
  assert.equal(payload.core_runner_trailing_mode, 'tiered');
  assert.equal(payload.core_runner_loss_ladder_consumes_candidates, true);
});

test('validates allocation and strictly increasing trail tiers', () => {
  const state = normalizeRunnerSettings({
    core_runner_allocation_percent: 120,
    core_runner_trailing_tiers: [
      { mfe_percent: 100, trail_percent: 35 },
      { mfe_percent: 100, trail_percent: 20 },
    ],
  });

  const errors = validateRunnerSettings(state);
  assert.ok(errors.some((error) => error.includes('Allocation percent')));
  assert.ok(errors.some((error) => error.includes('strictly increasing')));
});

