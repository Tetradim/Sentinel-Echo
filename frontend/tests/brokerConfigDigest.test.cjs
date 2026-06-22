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

const { getBrokerConnectionResult, summarizeBrokerConfig } = require('../utils/brokerConfigDigest.ts');

const brokers = [
  {
    id: 'ibkr',
    name: 'Interactive Brokers',
    supports_options: true,
    requires_gateway: true,
    config_fields: [
      { key: 'gateway_url', label: 'Gateway URL', type: 'text' },
      { key: 'account_id', label: 'Account ID', type: 'text' },
    ],
  },
  {
    id: 'alpaca',
    name: 'Alpaca',
    supports_options: true,
    requires_gateway: false,
    config_fields: [
      { key: 'api_key', label: 'API Key', type: 'password' },
      { key: 'secret_key', label: 'Secret Key', type: 'password' },
    ],
  },
];

const configs = {
  ibkr: { gateway_url: 'https://localhost:5000', account_id: 'DU12345' },
  alpaca: { api_key: 'key', secret_key: 'secret' },
};

test('summarizes a configured active broker as ready', () => {
  const digest = summarizeBrokerConfig(brokers, 'ibkr', 'ibkr', configs, configs);

  assert.equal(digest.primaryStatus.title, 'Broker Ready');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.selectedBrokerName, 'Interactive Brokers');
  assert.equal(digest.configuredFields, 2);
  assert.equal(digest.totalFields, 2);
  assert.equal(digest.configuredBrokerCount, 2);
  assert.equal(digest.readinessPercent, 100);
  assert.deepEqual(digest.warningItems, []);
});

test('prioritizes missing fields on the selected broker', () => {
  const digest = summarizeBrokerConfig(
    brokers,
    'ibkr',
    'alpaca',
    { ...configs, alpaca: { api_key: 'key', secret_key: '' } },
    configs
  );

  assert.equal(digest.primaryStatus.title, 'Keys Needed');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.selectedBrokerName, 'Alpaca');
  assert.equal(digest.configuredFields, 1);
  assert.equal(digest.totalFields, 2);
  assert.equal(digest.readinessPercent, 50);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Secret Key missing', 'Selected broker inactive']
  );
});

test('surfaces unsaved broker edits before inactive broker warnings', () => {
  const digest = summarizeBrokerConfig(
    brokers,
    'ibkr',
    'alpaca',
    { ...configs, alpaca: { api_key: 'changed', secret_key: 'secret' } },
    configs
  );

  assert.equal(digest.primaryStatus.title, 'Unsaved Changes');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.unsavedBrokerCount, 1);
  assert.equal(digest.readinessPercent, 100);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Unsaved broker keys', 'Selected broker inactive']
  );
});

test('returns an idle digest when no brokers are available', () => {
  const digest = summarizeBrokerConfig([], null, null, {}, {});

  assert.equal(digest.primaryStatus.title, 'No Brokers');
  assert.equal(digest.primaryStatus.tone, 'idle');
  assert.equal(digest.selectedBrokerName, 'None');
  assert.equal(digest.readinessPercent, 0);
});

test('parses serialized broker connection check responses', () => {
  assert.deepEqual(getBrokerConnectionResult({
    connected: 'false',
    message: 'Broker rejected credentials',
  }), {
    connected: false,
    title: 'Not Connected',
    message: 'Broker rejected credentials',
  });

  assert.deepEqual(getBrokerConnectionResult({
    connected: '1',
    message: 'Broker connected',
  }), {
    connected: true,
    title: 'Connected!',
    message: 'Broker connected',
  });
});
