const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const BRIDGE_DIR = path.resolve(__dirname, "..");

test("manifest permits background heartbeat alarms", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(BRIDGE_DIR, "manifest.json"), "utf8"),
  );

  assert.ok(manifest.permissions.includes("storage"));
  assert.ok(manifest.permissions.includes("alarms"));
});

test("service worker schedules and publishes background heartbeats", () => {
  const source = fs.readFileSync(path.join(BRIDGE_DIR, "service_worker.js"), "utf8");

  assert.match(source, /chrome\.alarms\.create\(/);
  assert.match(source, /chrome\.alarms\.onAlarm\.addListener\(/);
  assert.match(source, /chrome-extension-service-worker/);
  assert.match(source, /publishServiceWorkerHeartbeat/);
});
