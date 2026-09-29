const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'trades.tsx'), 'utf8');

test('trades screen uses a cross-platform modal for clean slate confirmation', () => {
  assert.match(source, /cleanSlateTrades/);
  assert.match(source, /Clean Slate/);
  assert.match(source, /const \[showCleanSlate, setShowCleanSlate\]/);
  assert.match(source, /<Modal\s+visible=\{showCleanSlate\}/);
  assert.match(source, /onPress=\{executeCleanSlate\}/);
  assert.doesNotMatch(source, /Alert\.alert\(\s*'Clean Slate',/);
  assert.match(source, /fetchTrades\(\)/);
});
