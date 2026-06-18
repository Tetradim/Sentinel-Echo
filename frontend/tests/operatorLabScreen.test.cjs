const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const screenPath = path.join(__dirname, '..', 'app', 'operator-lab.tsx');

test('operator lab exposes safe backend action endpoints', () => {
  const source = fs.readFileSync(screenPath, 'utf8');

  assert.match(source, /\/api\/operator\/events\?limit=/);
  assert.match(source, /\/api\/operator\/test-alert/);
  assert.match(source, /\/api\/operator\/simulate-exit/);
});

test('operator lab renders the expected action surface', () => {
  const source = fs.readFileSync(screenPath, 'utf8');

  assert.match(source, /Create Test Alert/);
  assert.match(source, /Sell 50% Test Position/);
  assert.match(source, /Activity Log/);
  assert.match(source, /Open Positions/);
});
