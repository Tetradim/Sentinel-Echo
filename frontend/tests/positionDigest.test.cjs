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

const { filterPositions, summarizePositions } = require('../utils/positionDigest.ts');

const positions = [
  {
    id: 'open-win',
    ticker: 'AAPL',
    status: 'open',
    expiration: '2026-06-26',
    entry_price: 2,
    remaining_quantity: 2,
    total_cost: 400,
    realized_pnl: 0,
    unrealized_pnl: 120,
  },
  {
    id: 'open-loss',
    ticker: 'TSLA',
    status: 'partial',
    expiration: '2026-06-20',
    entry_price: 3,
    remaining_quantity: 1,
    total_cost: 300,
    realized_pnl: 40,
    unrealized_pnl: -90,
  },
  {
    id: 'closed',
    ticker: 'NVDA',
    status: 'closed',
    expiration: '2026-06-14',
    entry_price: 5,
    remaining_quantity: 0,
    total_cost: 500,
    realized_pnl: 250,
    unrealized_pnl: 0,
  },
];

test('summarizes open exposure and attention conditions', () => {
  const digest = summarizePositions(positions, '2026-06-18T12:00:00Z');

  assert.equal(digest.total, 3);
  assert.equal(digest.open, 2);
  assert.equal(digest.closed, 1);
  assert.equal(digest.partial, 1);
  assert.equal(digest.losingOpen, 1);
  assert.equal(digest.expiringSoon, 1);
  assert.equal(digest.totalUnrealized, 30);
  assert.equal(digest.totalRealized, 290);
  assert.equal(digest.openExposure, 700);
  assert.equal(digest.topExposureTicker, 'AAPL');
  assert.equal(digest.primaryStatus.title, 'Expiry Watch');
});

test('filters positions by open, closed, and attention views', () => {
  assert.deepEqual(filterPositions(positions, 'open', '2026-06-18T12:00:00Z').map((position) => position.id), ['open-win', 'open-loss']);
  assert.deepEqual(filterPositions(positions, 'closed', '2026-06-18T12:00:00Z').map((position) => position.id), ['closed']);
  assert.deepEqual(filterPositions(positions, 'attention', '2026-06-18T12:00:00Z').map((position) => position.id), ['open-loss']);
  assert.equal(filterPositions(positions, 'all', '2026-06-18T12:00:00Z').length, 3);
});

test('returns an idle digest when there are no positions', () => {
  const digest = summarizePositions([], '2026-06-18T12:00:00Z');

  assert.equal(digest.total, 0);
  assert.equal(digest.openExposure, 0);
  assert.equal(digest.primaryStatus.title, 'Flat');
  assert.equal(digest.primaryStatus.tone, 'empty');
});
