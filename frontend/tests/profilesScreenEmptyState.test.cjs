const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('profiles screen exposes a create-profile empty state', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'profiles.tsx'), 'utf8');

  assert.match(source, /profiles\.length === 0/);
  assert.match(source, /styles\.emptyState/);
  assert.match(source, /Create Profile/);
  assert.match(source, /setShowCreateModal\(true\)/);
});
