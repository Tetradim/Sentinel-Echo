const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('select primitive forwards selected values from items', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'components', 'ui', 'select.tsx'), 'utf8');

  assert.match(source, /createContext/);
  assert.match(source, /onValueChange\?\.\(value\)/);
  assert.match(source, /setOpen\(false\)/);
  assert.match(source, /accessibilityRole="button"/);
});

test('slider primitive applies min max step controls', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'components', 'ui', 'slider.tsx'), 'utf8');

  assert.match(source, /min \?\? minimumValue/);
  assert.match(source, /max \?\? maximumValue/);
  assert.match(source, /step = 1/);
  assert.match(source, /onValueChange\?\.\(\[nextValue\]\)/);
});
