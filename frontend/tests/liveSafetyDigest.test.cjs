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

test('live safety digest explains source policy blockers', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: false,
    blocking_issues: [
      { code: 'no_live_source', summary: 'No enabled source can submit live orders automatically.' },
    ],
    checks: {
      source_policy: {
        blocked_sources: [
          { key: 'paper', reasons: ['paper_only'] },
          { key: 'manual', reasons: ['manual_confirm_required'] },
          { key: 'disabled', reasons: ['disabled'] },
        ],
      },
    },
  });

  assert.equal(digest.title, 'Live Blocked');
  assert.match(digest.detail, /paper is paper-only/);
  assert.match(digest.detail, /manual requires manual confirmation/);
  assert.match(digest.detail, /disabled is disabled/);
});

test('live safety digest explains metadata-only OCO blockers', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: false,
    blocking_issues: [
      {
        code: 'position_oco_unprotected',
        summary: 'Open live positions are missing position-level OCO exit protection.',
      },
    ],
    checks: {
      exit_automation: {
        metadata_only_open_position_count: 1,
        metadata_only_open_position_ids: ['pos-live-metadata-only'],
      },
    },
  });

  assert.equal(digest.title, 'Live Blocked');
  assert.match(digest.detail, /metadata-only OCO/);
  assert.match(digest.detail, /pos-live-metadata-only/);
  assert.match(digest.detail, /Broker child orders/);
});

test('live safety digest explains unprotected OCO position blockers', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: false,
    blocking_issues: [
      {
        code: 'position_oco_unprotected',
        summary: 'Open live positions are missing position-level OCO exit protection.',
      },
    ],
    checks: {
      exit_automation: {
        unprotected_open_position_count: 1,
        unprotected_open_position_ids: ['pos-live-unprotected'],
        metadata_only_open_position_count: 0,
        metadata_only_open_position_ids: [],
      },
    },
  });

  assert.equal(digest.title, 'Live Blocked');
  assert.match(digest.detail, /missing broker OCO child orders/);
  assert.match(digest.detail, /pos-live-unprotected/);
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

test('live safety digest treats string false armed flag as unarmed', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: true,
    blocking_issues: [],
    checks: {
      runtime: {
        live_trading_armed: 'false',
        live_trading_armed_until: '2099-01-01T00:00:00+00:00',
      },
      broker: { active_broker: 'alpaca' },
      trading: { simulation_mode: false },
    },
  });

  assert.equal(digest.title, 'Ready To Arm');
  assert.equal(digest.isArmed, false);
  assert.equal(digest.canArm, true);
  assert.equal(digest.primaryAction, 'arm');
});

test('live safety digest treats string false readiness as not ready', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: 'false',
    blocking_issues: [],
    checks: {
      runtime: { live_trading_armed: false },
      broker: { active_broker: 'alpaca' },
      trading: { simulation_mode: false },
    },
  });

  assert.equal(digest.title, 'Safety Idle');
  assert.equal(digest.canArm, false);
  assert.equal(digest.primaryAction, 'review');
});

test('live safety digest treats string false simulation flag as off', () => {
  const digest = summarizeLiveSafety({
    ready_for_live: true,
    blocking_issues: [],
    checks: {
      runtime: { live_trading_armed: false },
      broker: { active_broker: 'alpaca' },
      trading: { simulation_mode: 'false' },
    },
  });

  assert.equal(digest.title, 'Ready To Arm');
  assert.match(digest.detail, /simulation is off/);
});
