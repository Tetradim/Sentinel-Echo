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
  compareStrikeStrategies,
  summarizeStrikeSelection,
} = require('../utils/strikeSelectionDigest.ts');

const chain = {
  underlying: 450,
  calls: [
    { strike: 430, bid: 21.5, ask: 22.5, iv: 28, delta: 0.72, theta: -0.15, oi: 8500 },
    { strike: 440, bid: 14.2, ask: 15.0, iv: 26, delta: 0.55, theta: -0.12, oi: 12000 },
    { strike: 450, bid: 8.8, ask: 9.5, iv: 25, delta: 0.33, theta: -0.1, oi: 15000 },
    { strike: 460, bid: 4.5, ask: 5.0, iv: 26, delta: 0.2, theta: -0.08, oi: 11000 },
    { strike: 470, bid: 2.1, ask: 2.5, iv: 29, delta: 0.09, theta: -0.05, oi: 9000 },
  ],
  puts: [
    { strike: 430, bid: 2.0, ask: 2.5, iv: 27, delta: -0.08, theta: -0.05, oi: 7500 },
    { strike: 440, bid: 4.2, ask: 5.0, iv: 26, delta: -0.18, theta: -0.08, oi: 10000 },
    { strike: 450, bid: 8.5, ask: 9.5, iv: 25, delta: -0.32, theta: -0.1, oi: 14000 },
    { strike: 460, bid: 14.0, ask: 15.5, iv: 26, delta: -0.48, theta: -0.12, oi: 11000 },
    { strike: 470, bid: 21.0, ask: 23.0, iv: 28, delta: -0.65, theta: -0.15, oi: 8000 },
  ],
};

test('summarizes an at-the-money call as ready with liquidity and spread labels', () => {
  const digest = summarizeStrikeSelection({
    chain,
    optionType: 'CALL',
    strategy: 'ATM',
  });

  assert.equal(digest.primaryStatus.title, 'Strike Ready');
  assert.equal(digest.primaryStatus.tone, 'live');
  assert.equal(digest.selectedStrike, 450);
  assert.equal(digest.selectedPremiumLabel, '$9.15');
  assert.equal(digest.spreadLabel, '$0.70');
  assert.equal(digest.deltaLabel, '0.33');
  assert.equal(digest.moneynessLabel, 'ATM');
  assert.equal(digest.liquidityLabel, '15,000 OI');
  assert.deepEqual(digest.warningItems, []);
});

test('selects the closest target delta contract for puts', () => {
  const digest = summarizeStrikeSelection({
    chain,
    optionType: 'PUT',
    strategy: 'DELTA',
    targetDelta: 0.3,
  });

  assert.equal(digest.selectedStrike, 450);
  assert.equal(digest.deltaLabel, '-0.32');
  assert.equal(digest.primaryStatus.title, 'Strike Ready');
});

test('flags wide spreads and thin liquidity before a strike can be trusted', () => {
  const digest = summarizeStrikeSelection({
    chain: {
      underlying: 100,
      calls: [
        { strike: 105, bid: 0.9, ask: 1.5, iv: 40, delta: 0.2, theta: -0.04, oi: 140 },
      ],
      puts: [],
    },
    optionType: 'CALL',
    strategy: 'OTM',
  });

  assert.equal(digest.primaryStatus.title, 'Execution Review');
  assert.equal(digest.primaryStatus.tone, 'attention');
  assert.deepEqual(
    digest.warningItems.map((item) => item.title),
    ['Wide bid/ask spread', 'Thin open interest']
  );
});

test('compares deterministic strategy selections without random returns', () => {
  const rows = compareStrikeStrategies(chain, 'CALL');

  assert.deepEqual(
    rows.map((row) => [row.strategy, row.strike]),
    [
      ['ATM', 450],
      ['OTM', 470],
      ['ITM', 430],
      ['DELTA', 450],
      ['RISK', 460],
      ['IV', 470],
      ['LIQ', 450],
    ]
  );
  assert.equal(rows[0].scoreLabel, 'Balanced');
  assert.equal(rows[4].scoreLabel, 'Risk weighted');
});
