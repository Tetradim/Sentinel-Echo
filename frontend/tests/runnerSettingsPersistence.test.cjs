const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

test('runner screen loads and saves through the settings API', () => {
  const screen = fs.readFileSync(require.resolve('../app/runner-settings.tsx'), 'utf8');
  const state = fs.readFileSync(require.resolve('../utils/runnerSettingsState.ts'), 'utf8');

  assert.match(screen, /api\.get\(`\$\{BACKEND_URL\}\/api\/settings`\)/);
  assert.match(screen, /api\.put\(`\$\{BACKEND_URL\}\/api\/settings`/);
  assert.match(state, /core_runner_catastrophic_stop_percent/);
  assert.match(screen, /Full premium at risk/);
});

test('trading presets remain draft-only until the runner settings save action', () => {
  const screen = fs.readFileSync(require.resolve('../app/runner-settings.tsx'), 'utf8');

  assert.match(screen, /Trading test presets/);
  assert.match(screen, /TRADING_TEST_PRESETS/);
  assert.match(screen, /selectedPresetId/);
  assert.match(screen, /applyTradingTestPreset/);
  assert.match(screen, /diffTradingTestPreset/);
  assert.match(screen, /Draft only/);
  assert.match(screen, /Review changes/);
  assert.match(screen, /presetPayload/);

  const putCalls = screen.match(/api\.put\(`/g) || [];
  assert.equal(putCalls.length, 1);
});
