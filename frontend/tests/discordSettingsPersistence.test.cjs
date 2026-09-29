const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'discord-settings.tsx'), 'utf8');

test('Discord settings screen loads persisted backend settings and patterns', () => {
  assert.match(source, /from 'react';/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/settings`\)/);
  assert.match(source, /api\.get\(`\$\{BACKEND_URL\}\/api\/discord\/alert-patterns`\)/);
  assert.match(source, /setCommunities\(/);
  assert.match(source, /setPatterns\(/);
});

test('Discord settings screen saves communities, filters, and alert patterns', () => {
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/settings`/);
  assert.match(source, /api\.put\(`\$\{BACKEND_URL\}\/api\/discord\/alert-patterns`/);
  assert.match(source, /discord_channel_ids/);
  assert.match(source, /source_overrides/);
  assert.match(source, /discord_communities/);
  assert.match(source, /discord_filters/);
});

test('Discord settings screen exposes behavior toggles', () => {
  assert.match(source, /type TabType = 'communities' \| 'patterns' \| 'filters' \| 'behaviors'/);
  assert.match(source, /processFollowupUpdates/);
  assert.match(source, /process_actionable_edits/);
  assert.match(source, /allow_single_position_inferred_sell/);
  assert.match(source, /protect_trailing_armed_from_contextual_exits/);
  assert.match(source, /trailing_context_exit_override_enabled/);
  assert.match(source, /trailing_context_exit_override_percent/);
  assert.match(source, /dedupe_by_channel_url/);
  assert.match(source, /ignore_followup_messages/);
  assert.match(source, /allow_fresh_entry_after_close/);
  assert.match(source, /trim_alert_listening_enabled/);
  assert.match(source, /exit_profile/);
  assert.match(source, /Honor Trim Alerts/);
  assert.match(source, /Swing Exit Profile/);
});
