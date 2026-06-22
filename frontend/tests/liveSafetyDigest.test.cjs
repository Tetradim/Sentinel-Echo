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

const { summarizeLiveSafety } = require('../utils/liveSafetyDigest.ts');

test('live safety digest prioritizes blockers', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: false,
    blocking_issues: [{ code: 'simulation_mode_enabled', summary: 'Simulation mode is enabled.' }],
  });

  assert.equal(digest.title, 'Live Blocked');
  assert.equal(digest.tone, 'blocked');
  assert.equal(digest.blockerCount, 1);
  assert.equal(digest.canArm, false);
});

test('live safety digest exposes armed state', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: true,
    blocking_issues: [],
    checks: {
      runtime: {
        live_trading_armed: true,
        live_trading_armed_until: '2099-01-01T00:00:00+00:00',
      },
    },
  });

  assert.equal(digest.title, 'Live Armed');
  assert.equal(digest.primaryAction, 'disarm');
  assert.equal(digest.isArmed, true);
});

test('live safety digest allows arming when ready and unarmed', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: true,
    blocking_issues: [],
    checks: {
      runtime: { live_trading_armed: false },
      broker: { active_broker: 'alpaca' },
      trading: { simulation_mode: false },
    },
  });

  assert.equal(digest.title, 'Ready To Arm');
  assert.equal(digest.canArm, true);
  assert.equal(digest.primaryAction, 'arm');
});
