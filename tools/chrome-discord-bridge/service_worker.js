const DEFAULTS = {
  enabled: false,
  targetUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
  heartbeatUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat",
  apiKey: "",
  forwardExistingOnEnable: false,
};

const HEARTBEAT_ALARM_NAME = "consolidation-bridge-heartbeat";

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(DEFAULTS, (settings) => {
    chrome.storage.local.set({ ...DEFAULTS, ...settings }, () => {
      ensureHeartbeatAlarm();
      publishServiceWorkerHeartbeat("ok", { reason: "installed" });
    });
  });
});

chrome.runtime.onStartup.addListener(() => {
  ensureHeartbeatAlarm();
  publishServiceWorkerHeartbeat("ok", { reason: "startup" });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== HEARTBEAT_ALARM_NAME) return;
  publishServiceWorkerHeartbeat("ok", { reason: "alarm" });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message) {
    return false;
  }

  if (message.type === "consolidation:discord-message") {
    forwardObservedMessage(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }

  if (message.type === "consolidation:bridge-heartbeat") {
    forwardHeartbeat(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }

  return false;
});

function ensureHeartbeatAlarm() {
  chrome.alarms.create(HEARTBEAT_ALARM_NAME, { periodInMinutes: 1 });
}

async function publishServiceWorkerHeartbeat(status = "ok", details = {}) {
  try {
    const payload = await buildServiceWorkerHeartbeat(status, details);
    return await forwardHeartbeat(payload);
  } catch (error) {
    await chrome.storage.local.set({
      lastHeartbeatStatus: String(error && error.message ? error.message : error),
      lastHeartbeatAt: new Date().toISOString(),
    });
    return null;
  }
}

async function buildServiceWorkerHeartbeat(status, details) {
  const settings = await getSettings();
  return {
    status,
    bridge_enabled: Boolean(settings.enabled),
    url: "chrome-extension://service-worker",
    channel_id: "chrome-extension-service-worker",
    channel_name: "Chrome Extension",
    observed_at: new Date().toISOString(),
    last_forward_at: settings.lastForwardAt || "",
    last_forward_status: settings.lastForwardStatus || "",
    details: { source: "service_worker", ...details },
  };
}

async function forwardHeartbeat(payload) {
  const settings = await getSettings();
  const headers = { "Content-Type": "application/json" };
  if (settings.apiKey) {
    headers["X-API-Key"] = settings.apiKey;
  }

  const response = await fetch(settings.heartbeatUrl || heartbeatUrlFor(settings.targetUrl), {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { text };
    }
  }

  if (!response.ok) {
    throw new Error(body.detail || body.text || `Heartbeat request failed with HTTP ${response.status}`);
  }

  await chrome.storage.local.set({
    lastHeartbeatStatus: body.status || "healthy",
    lastHeartbeatAt: new Date().toISOString(),
  });
  return body;
}

async function forwardObservedMessage(payload) {
  const settings = await getSettings();
  if (!settings.enabled) {
    return { status: "disabled" };
  }

  const headers = { "Content-Type": "application/json" };
  if (settings.apiKey) {
    headers["X-API-Key"] = settings.apiKey;
  }

  const response = await fetch(settings.targetUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { text };
    }
  }

  if (!response.ok) {
    throw new Error(body.detail || body.text || `Bridge request failed with HTTP ${response.status}`);
  }

  await chrome.storage.local.set({
    lastForwardStatus: body.status || "accepted",
    lastForwardAt: new Date().toISOString(),
    lastForwardEventId: payload.event_id,
  });
  return body;
}

function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULTS, (settings) => resolve({ ...DEFAULTS, ...settings }));
  });
}

function heartbeatUrlFor(targetUrl) {
  return String(targetUrl || DEFAULTS.targetUrl).replace(/\/message$/, "/heartbeat");
}
