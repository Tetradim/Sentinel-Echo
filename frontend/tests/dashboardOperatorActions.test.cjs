const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const dashboardPath = path.join(__dirname, '..', 'app', 'index.tsx');

test('dashboard renders the operator action queue from readiness', () => {
  const source = fs.readFileSync(dashboardPath, 'utf8');

  assert.match(source, /buildOperatorActionQueue/);
  assert.match(source, /operatorActions\s*=\s*buildOperatorActionQueue\(readiness\)/);
  assert.match(source, /Next Actions/);
  assert.match(source, /operatorActions\.map/);
});
