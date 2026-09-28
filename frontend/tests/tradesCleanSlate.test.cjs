const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'trades.tsx'), 'utf8');

test('trades screen exposes a destructive clean slate action', () => {
  assert.match(source, /cleanSlateTrades/);
  assert.match(source, /Clean Slate/);
  assert.match(source, /Alert\.alert\(\s*'Clean Slate'/);
  assert.match(source, /style: 'destructive'/);
  assert.match(source, /fetchTrades\(\)/);
});
