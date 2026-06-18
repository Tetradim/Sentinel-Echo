const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const screens = [
  { file: 'app/alerts.tsx', forbiddenDemoIdentifier: 'DEMO_ALERTS' },
  { file: 'app/trades.tsx', forbiddenDemoIdentifier: 'DEMO_TRADES' },
  { file: 'app/positions.tsx', forbiddenDemoIdentifier: 'DEMO_POSITIONS' },
];

function catchBlocksUsingIdentifier(filePath, identifier) {
  const source = fs.readFileSync(filePath, 'utf8');
  const ast = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const offenders = [];

  function nodeContainsIdentifier(node) {
    if (ts.isIdentifier(node) && node.text === identifier) return true;
    return ts.forEachChild(node, nodeContainsIdentifier) || false;
  }

  function visit(node) {
    if (ts.isCatchClause(node) && nodeContainsIdentifier(node.block)) {
      offenders.push({
        line: ast.getLineAndCharacterOfPosition(node.getStart(ast)).line + 1,
        identifier,
      });
    }
    ts.forEachChild(node, visit);
  }

  visit(ast);
  return offenders;
}

test('live API failures do not silently replace operator data with demo datasets', () => {
  for (const screen of screens) {
    const filePath = path.join(__dirname, '..', screen.file);
    assert.deepEqual(
      catchBlocksUsingIdentifier(filePath, screen.forbiddenDemoIdentifier),
      [],
      `${screen.file} catch blocks must not reference ${screen.forbiddenDemoIdentifier}`
    );
  }
});
