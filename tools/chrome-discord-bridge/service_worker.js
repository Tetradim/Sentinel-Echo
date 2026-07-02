importScripts("bridge_config.js");

const DEFAULTS = {
  enabled: false,
  targetUrl: DEFAULT_MESSAGE_URL,
  heartbeatUrl: DEFAULT_HEARTBEAT_URL,
  apiKey: "",
  targets: [],
  forwardExistingOnEnable: false,
  autoRestartEnabled: true,
  bridgeRestartAttempt: 0,
};

const HEARTBEAT_ALARM_NAME = "sentinel-echo-bridge-heartbeat";
const SUPERVISOR_ALARM_NAME = "sentinel-echo-bridge-supervisor";
const RESTART_RETRY_ALARM_NAME = "sentinel-echo-bridge-restart-retry";
const MIN_RESTART_BACKOFF_SECONDS = 5;
const MAX_RESTART_BACKOFF_SECONDS = 300;
const BRIDGE_FETCH_TIMEOUT_MS = 5000;
const DISCORD_TAB_URLS = ["https://discord.com/*", "https://*.discord.com/*"];

ensureBridgeAlarms();
publishServiceWorkerHeartbeat("ok", { reason: "service_worker_loaded" }).catch((error) => {
  console.warn("[Discord Alert Bridge]", "service-worker load heartbeat failed", errorMessage(error));
});
superviseDiscordTabs("service_worker_loaded").catch((error) => {
  console.warn("[Discord Alert Bridge]", "service-worker load supervision failed", errorMessage(error));
});

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

  if (message.type === "discord-bridge:discord-message" || message.type === "sentinel-echo:discord-message") {
    forwardObservedMessage(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }

  if (message.type === "discord-bridge:bridge-heartbeat" || message.type === "sentinel-echo:bridge-heartbeat") {
    forwardHeartbeat(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }

  return false;
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (changes.enabled || changes.autoRestartEnabled || changes.targets || changes.targetUrl || changes.heartbeatUrl || changes.apiKey) {
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
    const matchingTabs = tabs.filter((tab) => targetsForDiscordChannel(settings, tab.url || "").length > 0);
    if (matchingTabs.length === 0) {
      const status = tabs.length === 0 ? "no_discord_tabs" : "no_matching_discord_tabs";
      await publishServiceWorkerHeartbeat(status, {
        reason,
        discord_tabs: tabs.length,
        configured_targets: enabledBridgeTargets(settings).length,
      });
      await scheduleRestartRetry(tabs.length === 0 ? "no Discord tabs are open" : "no matching Discord channel tabs are open");
      return;
    }

    const results = [];
    for (const tab of matchingTabs) {
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
      { type: "discord-bridge:bridge-ping", restart },
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
        files: ["bridge_config.js", "content.js"],
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
    details: {
      source: "service_worker",
      targets: enabledBridgeTargets(settings).map((target) => ({
        id: target.id,
        name: target.name,
        messageUrl: target.messageUrl,
      })),
      ...details,
    },
  };
}

async function forwardHeartbeat(payload) {
  const settings = await getSettings();
  const targets = targetsForPayload(settings, payload);
  if (targets.length === 0) {
    await chrome.storage.local.set({
      lastHeartbeatStatus: "no_matching_target",
      lastHeartbeatAt: new Date().toISOString(),
    });
    return { status: "skipped", skip_reason: "no matching bridge target" };
  }

  const results = await forwardPayloadToTargets(targets, payload, "heartbeat");
  await chrome.storage.local.set({
    lastHeartbeatStatus: results.status,
    lastHeartbeatAt: new Date().toISOString(),
    lastHeartbeatTargets: results.targets,
  });
  return results;
}

async function forwardObservedMessage(payload) {
  const settings = await getSettings();
  if (!settings.enabled) {
    return { status: "disabled" };
  }

  const targets = targetsForPayload(settings, payload);
  if (targets.length === 0) {
    await chrome.storage.local.set({
      lastForwardStatus: "no_matching_target",
      lastForwardAt: new Date().toISOString(),
      lastForwardEventId: payload.event_id,
    });
    return { status: "skipped", skip_reason: "no matching bridge target" };
  }

  try {
    const result = await forwardPayloadToTargets(targets, payload, "message");
    await chrome.storage.local.set({
      lastForwardStatus: result.status,
      lastForwardAt: new Date().toISOString(),
      lastForwardEventId: payload.event_id,
      lastForwardTargets: result.targets,
    });
    if (result.failures.length > 0) {
      await scheduleRestartRetry(`message forward partially failed: ${result.failures[0].error}`);
    }
    return result;
  } catch (error) {
    await scheduleRestartRetry(`message forward failed: ${errorMessage(error)}`);
    throw error;
  }
}

async function forwardPayloadToTargets(targets, payload, kind) {
  const successes = [];
  const failures = [];
  for (const target of targets) {
    try {
      const body = await forwardPayloadToTarget(target, payload, kind);
      successes.push({
        id: target.id,
        name: target.name,
        status: body.status || (kind === "heartbeat" ? "healthy" : "accepted"),
        body,
      });
    } catch (error) {
      failures.push({
        id: target.id,
        name: target.name,
        error: errorMessage(error),
      });
    }
  }

  if (successes.length === 0 && failures.length > 0) {
    throw new Error(failures.map((failure) => `${failure.name}: ${failure.error}`).join("; "));
  }

  return {
    status: failures.length > 0 ? "partial" : (kind === "heartbeat" ? "healthy" : "accepted"),
    targets: successes,
    failures,
  };
}

async function forwardPayloadToTarget(target, payload, kind) {
  const headers = { "Content-Type": "application/json" };
  if (target.apiKey) {
    headers["X-API-Key"] = target.apiKey;
  }

  const primaryUrl = kind === "heartbeat" ? target.heartbeatUrl || heartbeatUrlFor(target.messageUrl) : target.messageUrl;
  const requestBody = JSON.stringify({
    ...payload,
    bridge_target_id: target.id,
    bridge_target_name: target.name,
  });
  const urls = [primaryUrl, ...localSentinelEchoFallbackUrls(target, kind, primaryUrl)];
  const failures = [];

  for (const url of urls) {
    try {
      const body = await postBridgeJson(url, headers, requestBody, kind);
      if (url !== primaryUrl && body && typeof body === "object" && !Array.isArray(body)) {
        body.bridge_fallback_url = url;
      }
      return body;
    } catch (error) {
      failures.push(`${url}: ${errorMessage(error)}`);
    }
  }

  throw new Error(failures.join("; ") || `${kind} request failed`);
}

async function postBridgeJson(url, headers, requestBody, kind) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BRIDGE_FETCH_TIMEOUT_MS);
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: requestBody,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  const text = await response.text();
  let responseBody = {};
  if (text) {
    try {
      responseBody = JSON.parse(text);
    } catch {
      responseBody = { text };
    }
  }

  if (!response.ok) {
    throw new Error(responseBody.detail || responseBody.text || `${kind} request failed with HTTP ${response.status}`);
  }

  return responseBody;
}

function targetsForPayload(settings, payload) {
  if (payload && canonicalDiscordChannelUrl(payload.url || "")) {
    return targetsForDiscordChannel(settings, payload.url, payload.channel_id);
  }
  return enabledBridgeTargets(settings);
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
