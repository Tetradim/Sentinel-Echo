const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const screenPath = path.join(__dirname, '..', 'app', 'operator-lab.tsx');

test('operator lab exposes safe backend action endpoints', () => {
  const source = fs.readFileSync(screenPath, 'utf8');

  assert.match(source, /getOperatorEvents/);
  assert.match(source, /createOperatorTestAlert/);
  assert.match(source, /simulateOperatorExit/);
  assert.match(source, /getLiveReadiness/);
  assert.match(source, /armLiveTrading/);
  assert.match(source, /disarmLiveTrading/);
  assert.match(source, /panicStop/);
  assert.match(source, /getReconciliation/);
});

test('operator lab renders the expected action surface', () => {
  const source = fs.readFileSync(screenPath, 'utf8');

  assert.match(source, /Create Test Alert/);
  assert.match(source, /Sell 50% Test Position/);
  assert.match(source, /Arm Live/);
  assert.match(source, /Disarm/);
  assert.match(source, /Panic Stop/);
  assert.match(source, /Reconciliation/);
  assert.match(source, /Activity Log/);
  assert.match(source, /Open Positions/);
});
