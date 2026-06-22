const DEFAULTS = {
  enabled: false,
  targetUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
  heartbeatUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat",
  apiKey: "",
  forwardExistingOnEnable: false,
  autoRestartEnabled: true,
  bridgeRestartAttempt: 0,
};

const HEARTBEAT_ALARM_NAME = "consolidation-bridge-heartbeat";
const SUPERVISOR_ALARM_NAME = "consolidation-bridge-supervisor";
const RESTART_RETRY_ALARM_NAME = "consolidation-bridge-restart-retry";
const MIN_RESTART_BACKOFF_SECONDS = 5;
const MAX_RESTART_BACKOFF_SECONDS = 300;
const DISCORD_TAB_URLS = ["https://discord.com/*", "https://*.discord.com/*"];

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(DEFAULTS, (settings) => {
    chrome.storage.local.set({ ...DEFAULTS, ...settings }, () => {
      ensureBridgeAlarms();
      publishServiceWorkerHeartbeat("ok", { reason: "installed" });
      superviseDiscordTabs("installed");
    });
  });
});

chrome.runtime.onStartup.addListener(() => {
  ensureBridgeAlarms();
  publishServiceWorkerHeartbeat("ok", { reason: "startup" });
  superviseDiscordTabs("startup");
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === HEARTBEAT_ALARM_NAME) {
    publishServiceWorkerHeartbeat("ok", { reason: "alarm" });
    return;
  }
  if (alarm.name === SUPERVISOR_ALARM_NAME || alarm.name === RESTART_RETRY_ALARM_NAME) {
    superviseDiscordTabs(alarm.name);
  }
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

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (changes.enabled || changes.autoRestartEnabled) {
    ensureBridgeAlarms();
    superviseDiscordTabs("settings_changed");
  }
});

function ensureBridgeAlarms() {
  chrome.alarms.create(HEARTBEAT_ALARM_NAME, { periodInMinutes: 1 });
  chrome.alarms.create(SUPERVISOR_ALARM_NAME, { periodInMinutes: 1 });
}

async function publishServiceWorkerHeartbeat(status = "ok", details = {}) {
  try {
    const payload = await buildServiceWorkerHeartbeat(status, details);
    return await forwardHeartbeat(payload);
  } catch (error) {
    await scheduleRestartRetry(`heartbeat failed: ${errorMessage(error)}`);
    await chrome.storage.local.set({
      lastHeartbeatStatus: errorMessage(error),
      lastHeartbeatAt: new Date().toISOString(),
    });
    return null;
  }
}

async function superviseDiscordTabs(reason = "supervisor") {
  const settings = await getSettings();
  if (!settings.autoRestartEnabled || !settings.enabled) {
    await publishServiceWorkerHeartbeat("disabled", { reason, supervisor: "disabled" });
    return;
  }

  try {
    const tabs = await queryDiscordTabs();
    if (tabs.length === 0) {
      await publishServiceWorkerHeartbeat("no_discord_tabs", { reason });
      await scheduleRestartRetry("no Discord tabs are open");
      return;
    }

    const results = [];
    for (const tab of tabs) {
      results.push(await ensureBridgeContentScript(tab.id));
    }

    const failures = results.filter((result) => !result.ok);
    if (failures.length > 0) {
      await publishServiceWorkerHeartbeat("restart_error", {
        reason,
        failures: failures.map((failure) => failure.error).slice(0, 5),
      });
      await scheduleRestartRetry(failures[0].error || "content script restart failed");
      return;
    }

    await resetRestartBackoff("content script healthy");
    await publishServiceWorkerHeartbeat("ok", {
      reason,
      supervised_tabs: results.length,
      restarted_tabs: results.filter((result) => result.restarted).length,
    });
  } catch (error) {
    await publishServiceWorkerHeartbeat("restart_error", { reason, error: errorMessage(error) });
    await scheduleRestartRetry(errorMessage(error));
  }
}

async function ensureBridgeContentScript(tabId) {
  const ping = await pingContentScript(tabId);
  if (ping.ok) {
    return { ok: true, restarted: false };
  }

  try {
    await executeContentScript(tabId);
  } catch (error) {
    return { ok: false, restarted: false, error: errorMessage(error) };
  }

  const restartedPing = await pingContentScript(tabId, true);
  if (!restartedPing.ok) {
    return { ok: false, restarted: true, error: restartedPing.error || "content script did not respond after restart" };
  }
  return { ok: true, restarted: true };
}

function pingContentScript(tabId, restart = false) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(
      tabId,
      { type: "consolidation:bridge-ping", restart },
      (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve({ ok: Boolean(response && response.ok), error: response && response.error });
      },
    );
  });
}

function executeContentScript(tabId) {
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript(
      {
        target: { tabId },
        files: ["content.js"],
      },
      () => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve();
      },
    );
  });
}

function queryDiscordTabs() {
  return new Promise((resolve, reject) => {
    chrome.tabs.query({ url: DISCORD_TAB_URLS }, (tabs) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve((tabs || []).filter((tab) => typeof tab.id === "number"));
    });
  });
}

async function scheduleRestartRetry(reason) {
  const settings = await getSettings();
  if (!settings.autoRestartEnabled) return;

  const attempt = Number(settings.bridgeRestartAttempt || 0);
  const delaySeconds = Math.min(
    MAX_RESTART_BACKOFF_SECONDS,
    MIN_RESTART_BACKOFF_SECONDS * Math.pow(2, attempt),
  );
  const nextRestartAt = Date.now() + delaySeconds * 1000;
  await chrome.storage.local.set({
    bridgeRestartAttempt: attempt + 1,
    lastRestartStatus: String(reason || "restart scheduled"),
    lastRestartRetryAt: new Date().toISOString(),
    nextRestartAt: new Date(nextRestartAt).toISOString(),
  });
  chrome.alarms.create(RESTART_RETRY_ALARM_NAME, { when: nextRestartAt });
}

async function resetRestartBackoff(status) {
  await chrome.storage.local.set({
    bridgeRestartAttempt: 0,
    lastRestartStatus: status || "healthy",
    nextRestartAt: "",
  });
  chrome.alarms.clear(RESTART_RETRY_ALARM_NAME);
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

  let response;
  try {
    response = await fetch(settings.targetUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  } catch (error) {
    await scheduleRestartRetry(`message forward failed: ${errorMessage(error)}`);
    throw error;
  }

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
    await scheduleRestartRetry(body.detail || body.text || `Bridge request failed with HTTP ${response.status}`);
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

function errorMessage(error) {
  return String(error && error.message ? error.message : error || "unknown error");
}
