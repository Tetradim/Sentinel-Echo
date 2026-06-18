const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const screens = [
  { file: 'alerts.tsx', retryHandler: 'retryFetchAlerts' },
  { file: 'trades.tsx', retryHandler: 'retryFetchTrades' },
  { file: 'positions.tsx', retryHandler: 'retryFetchPositions' },
  { file: 'profiles.tsx', retryHandler: 'retryFetchProfiles' },
];

test('live data error banners expose an explicit retry action', () => {
  for (const screen of screens) {
    const source = fs.readFileSync(path.join(__dirname, '..', 'app', screen.file), 'utf8');

    assert.match(source, new RegExp(`const ${screen.retryHandler} = useCallback`), screen.file);
    assert.match(source, /accessibilityRole="button"/, screen.file);
    assert.match(source, /style=\{(?:s|styles)\.errorBannerRetry\}/, screen.file);
    assert.match(source, />Retry</, screen.file);
  }
});
