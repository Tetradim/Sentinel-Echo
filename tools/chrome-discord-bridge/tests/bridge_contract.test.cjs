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

test("manifest permits bridge supervisor reinjection into Discord tabs", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(BRIDGE_DIR, "manifest.json"), "utf8"),
  );

  assert.ok(manifest.permissions.includes("scripting"));
  assert.ok(manifest.permissions.includes("tabs"));
});

test("service worker schedules and publishes background heartbeats", () => {
  const source = fs.readFileSync(path.join(BRIDGE_DIR, "service_worker.js"), "utf8");

  assert.match(source, /chrome\.alarms\.create\(/);
  assert.match(source, /chrome\.alarms\.onAlarm\.addListener\(/);
  assert.match(source, /chrome-extension-service-worker/);
  assert.match(source, /publishServiceWorkerHeartbeat/);
});

test("service worker supervises Discord tabs and retries restart with exponential backoff", () => {
  const source = fs.readFileSync(path.join(BRIDGE_DIR, "service_worker.js"), "utf8");

  assert.match(source, /SUPERVISOR_ALARM_NAME/);
  assert.match(source, /RESTART_RETRY_ALARM_NAME/);
  assert.match(source, /Math\.pow\(2,\s*attempt/);
  assert.match(source, /chrome\.tabs\.query/);
  assert.match(source, /chrome\.scripting\.executeScript/);
  assert.match(source, /scheduleRestartRetry/);
});

test("content script exposes restartable bridge ping for supervisor", () => {
  const source = fs.readFileSync(path.join(BRIDGE_DIR, "content.js"), "utf8");

  assert.match(source, /sentinel-echo:bridge-ping/);
  assert.match(source, /restartObserver/);
  assert.match(source, /observer\.disconnect\(\)/);
  assert.match(source, /clearInterval\(heartbeatTimer\)/);
});
