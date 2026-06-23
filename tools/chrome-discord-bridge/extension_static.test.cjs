const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = __dirname;
const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
const serviceWorker = fs.readFileSync(path.join(root, "service_worker.js"), "utf8");
const content = fs.readFileSync(path.join(root, "content.js"), "utf8");
const popup = fs.readFileSync(path.join(root, "popup.html"), "utf8");

assert.deepEqual(manifest.content_scripts[0].js, ["bridge_config.js", "content.js"]);
assert.match(serviceWorker, /importScripts\("bridge_config\.js"\)/);
assert.match(serviceWorker, /targetsForDiscordChannel/);
assert.match(serviceWorker, /enabledBridgeTargets/);
assert.match(serviceWorker, /discord-bridge:discord-message/);
assert.match(serviceWorker, /files: \["bridge_config\.js", "content\.js"\]/);
assert.match(content, /targetsForDiscordChannel/);
assert.match(content, /channel_url: channelUrlFromLocation\(\)/);
assert.match(content, /discord-bridge:bridge-heartbeat/);
assert.match(content, /discord-bridge:discord-message/);
assert.match(content, /forwardPayloadDirectly/);
assert.match(content, /runtime message failed; falling back to direct heartbeat forward/);
assert.match(content, /runtime message failed; falling back to direct message forward/);
assert.match(popup, /bridge_config\.js/);
assert.match(popup, /targetsJson/);
assert.match(popup, /autoRestartEnabled/);
assert.match(serviceWorker, /autoRestartEnabled/);

console.log("ok - chrome bridge extension static wiring");
