const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const settingsSource = fs.readFileSync(path.join(__dirname, '..', 'app', 'settings.tsx'), 'utf8');
const discordSource = fs.readFileSync(path.join(__dirname, '..', 'app', 'discord-settings.tsx'), 'utf8');

test('general Settings screen does not expose Discord edit controls', () => {
  assert.doesNotMatch(settingsSource, /SectionTitle icon="logo-discord" label="Discord"/);
  assert.doesNotMatch(settingsSource, /discord_token:\s*settings\.discord_token/);
  assert.doesNotMatch(settingsSource, /discord_channel_ids:\s*channelIds/);
  assert.doesNotMatch(settingsSource, /api\.post\(`\$\{BACKEND_URL\}\/api\/discord\/start`/);
  assert.doesNotMatch(settingsSource, /api\.post\(`\$\{BACKEND_URL\}\/api\/discord\/test-connection`/);
  assert.doesNotMatch(settingsSource, /api\.post\(`\$\{BACKEND_URL\}\/api\/discord\/alert-patterns\/\$\{patternType\}\/add/);
  assert.doesNotMatch(settingsSource, /Customize Discord keywords/);
});

test('general Settings readiness does not include Discord-specific labels', () => {
  assert.doesNotMatch(settingsSource, /DigestStat label="Discord"/);
  assert.doesNotMatch(settingsSource, /DigestStat label="Parser"/);
  assert.doesNotMatch(settingsSource, /api\.get\(`\$\{BACKEND_URL\}\/api\/discord\/alert-patterns`\)/);
  assert.match(settingsSource, /summarizeSettings\(settings, null\)/);
});

test('Discord settings tab owns Discord readiness and bot connection actions', () => {
  assert.match(discordSource, /SIGNAL READINESS/);
  assert.match(discordSource, /Bot Connection/);
  assert.match(discordSource, /Start Bot/);
  assert.match(discordSource, /api\.post\(`\$\{BACKEND_URL\}\/api\/discord\/start`/);
  assert.match(discordSource, /api\.post\(`\$\{BACKEND_URL\}\/api\/discord\/test-connection`/);
});
