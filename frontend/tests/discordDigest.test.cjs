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

const { summarizeDiscordSettings } = require('../utils/discordDigest.ts');

const community = {
  id: 'main',
  name: 'Main Trading Server',
  channelId: '123456789',
  enabled: true,
  preset: 'default',
  autoTrade: false,
  simulation: true,
};

const patterns = {
  buyKeywords: 'BUY,ENTRY,LONG,BTO,OPENING',
  sellKeywords: 'SELL,EXIT,CLOSE,STC,TRIM',
  avgDownKeywords: 'AVERAGE DOWN,AVG DOWN,AVERAGING,ADD TO',
  ignoreKeywords: 'WATCHLIST,WATCHING,MIGHT,PAPER',
  tickerPattern: '\\$([A-Z]{1,5})\\b',
  requireTicker: true,
  requireExpiration: true,
  requirePrice: true,
};

const filters = {
  listenToUsers: '',
  ignoreUsers: '',
  listenToChannels: '',
  minPrice: 0.01,
  maxPrice: 100,
};

test('summarizes a guarded Discord parser configuration as live', () => {
  const digest = summarizeDiscordSettings([community], patterns, filters);

  assert.equal(digest.primaryStatus.title, 'Parser Guarded');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.enabledCommunities, 1);
  assert.equal(digest.requiredFields, 3);
  assert.equal(digest.autoTradeCommunities, 0);
  assert.equal(digest.priceRangeLabel, '$0.01-$100');
  assert.deepEqual(digest.warningItems, []);
});

test('prioritizes enabled communities that do not have a channel id', () => {
  const digest = summarizeDiscordSettings([
    { ...community, channelId: '' },
  ], patterns, filters);

  assert.equal(digest.primaryStatus.title, 'Channel Setup');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.missingChannels, 1);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Channel ID missing']
  );
});

test('flags live auto trading with loose parser requirements', () => {
  const digest = summarizeDiscordSettings([
    { ...community, autoTrade: true, simulation: false },
  ], {
    ...patterns,
    ignoreKeywords: '',
    requireExpiration: false,
    requirePrice: false,
  }, filters);

  assert.equal(digest.primaryStatus.title, 'Live Auto Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.equal(digest.autoTradeCommunities, 1);
  assert.equal(digest.requiredFields, 1);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Live auto trading', 'Expiration optional', 'Price optional', 'Ignore list empty']
  );
});

test('parses string booleans for Discord community enablement and automation', () => {
  const digest = summarizeDiscordSettings([
    { ...community, id: 'disabled', channelId: '', enabled: 'false', autoTrade: 'true', simulation: 'false' },
    { ...community, id: 'paper-auto', channelId: 'paper', enabled: 'true', autoTrade: 'true', simulation: 'true' },
    { ...community, id: 'manual-live', channelId: 'manual', enabled: 'true', autoTrade: 'false', simulation: 'false' },
  ], patterns, filters);

  assert.equal(digest.primaryStatus.title, 'Parser Guarded');
  assert.equal(digest.enabledCommunities, 2);
  assert.equal(digest.missingChannels, 0);
  assert.equal(digest.autoTradeCommunities, 1);
  assert.deepEqual(digest.warningItems, []);
});

test('parses string booleans for Discord parser required fields', () => {
  const digest = summarizeDiscordSettings([community], {
    ...patterns,
    requireTicker: 'false',
    requireExpiration: 'true',
    requirePrice: '0',
  }, filters);

  assert.equal(digest.primaryStatus.title, 'Parser Review');
  assert.equal(digest.requiredFields, 1);
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Ticker optional', 'Price optional']
  );
});
