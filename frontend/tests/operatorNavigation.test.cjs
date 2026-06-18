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

const {
  OPERATOR_TABS,
  getActiveOperatorTab,
  getOperatorRoutePath,
  shouldShowOperatorTabs,
} = require('../utils/operatorNavigation.ts');

test('exposes the primary operator workflows in bottom navigation order', () => {
  assert.deepEqual(
    OPERATOR_TABS.map((tab) => [tab.name, tab.label]),
    [
      ['index', 'Dashboard'],
      ['alerts', 'Alerts'],
      ['trades', 'Trades'],
      ['positions', 'Positions'],
      ['strike-selection', 'Strikes'],
      ['trading-settings', 'Trading'],
      ['risk-settings', 'Risk'],
      ['discord-settings', 'Discord'],
      ['broker-config', 'Broker'],
      ['profiles', 'Profiles'],
      ['settings', 'Settings'],
    ]
  );
});

test('maps tab names to Expo route paths', () => {
  assert.equal(getOperatorRoutePath('index'), '/');
  assert.equal(getOperatorRoutePath('broker-config'), '/broker-config');
  assert.equal(getOperatorRoutePath('profiles'), '/profiles');
});

test('normalizes the current route into the active tab name', () => {
  assert.equal(getActiveOperatorTab('/'), 'index');
  assert.equal(getActiveOperatorTab('/strike-selection'), 'strike-selection');
  assert.equal(getActiveOperatorTab('/broker-config'), 'broker-config');
  assert.equal(getActiveOperatorTab('/unknown'), null);
});

test('shows operator tabs only on known operator routes', () => {
  assert.equal(shouldShowOperatorTabs('/profiles'), true);
  assert.equal(shouldShowOperatorTabs('/broker-config'), true);
  assert.equal(shouldShowOperatorTabs('/+not-found'), false);
});
