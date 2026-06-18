const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('risk settings screen loads and saves backend configuration', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'risk-settings.tsx'), 'utf8');

  assert.match(source, /import \{ api \} from '\.\.\/utils\/api'/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/risk-management-settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/trailing-stop-settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/auto-shutdown-settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/correlation-settings`\)/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/risk-management-settings`/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/trailing-stop-settings`/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/auto-shutdown-settings`/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/correlation-settings\?/);
});
