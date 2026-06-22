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

const { filterTrades, summarizeTrades } = require('../utils/tradeDigest.ts');

const trades = [
  {
    id: 'open-win',
    ticker: 'AAPL',
    quantity: 2,
    status: 'executed',
    simulated: false,
    realized_pnl: null,
    unrealized_pnl: 120,
  },
  {
    id: 'open-loss',
    ticker: 'TSLA',
    quantity: 1,
    status: 'executed',
    simulated: false,
    realized_pnl: null,
    unrealized_pnl: -80,
  },
  {
    id: 'closed-win',
    ticker: 'NVDA',
    quantity: 1,
    status: 'closed',
    simulated: false,
    realized_pnl: 300,
    unrealized_pnl: null,
  },
  {
    id: 'failed',
    ticker: 'MSFT',
    quantity: 1,
    status: 'failed',
    simulated: false,
    realized_pnl: null,
    unrealized_pnl: null,
  },
  {
    id: 'paper',
    ticker: 'SPY',
    quantity: 1,
    status: 'executed',
    simulated: true,
    realized_pnl: null,
    unrealized_pnl: 25,
  },
];

test('summarizes trade flow, exposure, and attention counts', () => {
  const digest = summarizeTrades(trades);

  assert.equal(digest.total, 5);
  assert.equal(digest.open, 3);
  assert.equal(digest.closed, 1);
  assert.equal(digest.failed, 1);
  assert.equal(digest.simulated, 1);
  assert.equal(digest.attention, 2);
  assert.equal(digest.netPnl, 365);
  assert.equal(digest.openQuantity, 4);
  assert.equal(digest.bestTicker, 'NVDA');
  assert.equal(digest.worstTicker, 'TSLA');
  assert.equal(digest.primaryStatus.title, 'Needs Review');
});

test('filters trades by open, closed, attention, and simulated views', () => {
  assert.deepEqual(filterTrades(trades, 'open').map((trade) => trade.id), ['open-win', 'open-loss', 'paper']);
  assert.deepEqual(filterTrades(trades, 'closed').map((trade) => trade.id), ['closed-win', 'failed']);
  assert.deepEqual(filterTrades(trades, 'attention').map((trade) => trade.id), ['open-loss', 'failed']);
  assert.deepEqual(filterTrades(trades, 'simulated').map((trade) => trade.id), ['paper']);
});

test('parses string booleans for simulated trade state', () => {
  const stringBackedTrades = [
    { ...trades[0], id: 'live-string', simulated: 'false' },
    { ...trades[1], id: 'paper-string', simulated: 'true' },
    { ...trades[2], id: 'numeric-paper', simulated: '1' },
  ];

  const digest = summarizeTrades(stringBackedTrades);

  assert.equal(digest.simulated, 2);
  assert.deepEqual(filterTrades(stringBackedTrades, 'simulated').map((trade) => trade.id), [
    'paper-string',
    'numeric-paper',
  ]);
});

test('returns an idle digest for no trades', () => {
  const digest = summarizeTrades([]);

  assert.equal(digest.total, 0);
  assert.equal(digest.netPnl, 0);
  assert.equal(digest.primaryStatus.title, 'No Trades');
  assert.equal(digest.primaryStatus.tone, 'empty');
});
