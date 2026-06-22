const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '..', 'utils', 'apiClient.ts'), 'utf8');

test('api client centralizes critical operator and trading routes', () => {
  [
    'getLiveReadiness',
    'armLiveTrading',
    'disarmLiveTrading',
    'panicStop',
    'getReconciliation',
    'sellPosition',
    'closeTrade',
    'updateTradePrice',
    'switchBroker',
    'checkBroker',
  ].forEach((name) => assert.match(source, new RegExp(`function ${name}\\b`)));

  [
    '/api/operator/live-readiness',
    '/api/operator/live-arm',
    '/api/operator/live-disarm',
    '/api/operator/panic-stop',
    '/api/operator/reconciliation',
    '/api/positions',
    '/api/trades/',
    '/api/broker/switch',
    '/api/broker/check',
  ].forEach((route) => assert.match(source, new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))));
});
