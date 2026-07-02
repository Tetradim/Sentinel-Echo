const BRIDGE_LOG_PREFIX = "[Discord Alert Bridge]";
const STORAGE_DEFAULTS = {
  enabled: false,
  targetUrl: DEFAULT_MESSAGE_URL,
  heartbeatUrl: DEFAULT_HEARTBEAT_URL,
  apiKey: "",
  targets: [],
  forwardExistingOnEnable: false,
};
const observedIds = new Set();
const observedOrder = [];
const MAX_OBSERVED = 2000;
const BRIDGE_FETCH_TIMEOUT_MS = 5000;

let enabled = false;
let forwardExistingOnEnable = false;
let bridgeSettings = { ...STORAGE_DEFAULTS };
let lastChannelUrl = "";
let observer = null;
let heartbeatTimer = null;

chrome.storage.local.get(STORAGE_DEFAULTS, (settings) => {
  applySettings(settings);
  startObserver();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  chrome.storage.local.get(STORAGE_DEFAULTS, (settings) => {
    const wasEnabled = enabled;
    applySettings(settings);
    publishHeartbeat();
    if (enabled && (!wasEnabled || changes.targets || changes.targetUrl || changes.heartbeatUrl || changes.apiKey || changes.forwardExistingOnEnable)) {
      prepareCurrentChannel(true);
    }
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || (message.type !== "discord-bridge:bridge-ping" && message.type !== "sentinel-echo:bridge-ping")) {
    return false;
  }
  if (message.restart) {
    restartObserver();
  } else {
    startObserver();
  }
  sendResponse({
    ok: true,
    enabled,
    observer_ready: Boolean(observer),
    heartbeat_running: Boolean(heartbeatTimer),
    matching_target: isCurrentChannelEnabled(),
    channel_id: channelIdFromLocation(),
    channel_url: channelUrlFromLocation(),
  });
  return false;
});

function applySettings(settings) {
  bridgeSettings = { ...STORAGE_DEFAULTS, ...settings };
  enabled = Boolean(bridgeSettings.enabled);
  forwardExistingOnEnable = Boolean(bridgeSettings.forwardExistingOnEnable);
}

function startObserver() {
  if (observer) return;
  if (!document.body) {
    setTimeout(startObserver, 1000);
    return;
  }
  observer = new MutationObserver((records) => {
    if (!enabled) return;
    if (refreshChannelState()) {
      prepareCurrentChannel(true);
      return;
    }
    if (!isCurrentChannelEnabled()) return;
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          scanNode(node);
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  prepareCurrentChannel(true);
  console.info(BRIDGE_LOG_PREFIX, "observer ready");
  startHeartbeat();
}

function restartObserver() {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  startObserver();
  publishHeartbeat("ok", { reason: "content_script_restart" });
}

function isCurrentChannelEnabled() {
  return enabled && targetsForDiscordChannel(bridgeSettings, location.href, channelIdFromLocation()).length > 0;
}

function prepareCurrentChannel(force = false) {
  if (!enabled) return;
  const changed = refreshChannelState(force);
  if (!changed && !force) return;
  if (!isCurrentChannelEnabled()) {
    publishHeartbeat("no_matching_target", { channel_url: channelUrlFromLocation() });
    return;
  }
  if (forwardExistingOnEnable) {
    scanVisibleMessages();
  } else {
    primeVisibleMessages();
  }
}

function refreshChannelState(force = false) {
  const current = channelUrlFromLocation();
  if (!force && current === lastChannelUrl) return false;
  lastChannelUrl = current;
  return true;
}

function startHeartbeat() {
  if (heartbeatTimer) return;
  publishHeartbeat();
  heartbeatTimer = setInterval(publishHeartbeat, 30000);
}

function publishHeartbeat(status = "ok", details = {}) {
  chrome.storage.local.get(
    { lastForwardAt: "", lastForwardStatus: "" },
    (settings) => {
      const payload = {
        status,
        bridge_enabled: enabled,
        url: location.href,
        channel_id: channelIdFromLocation(),
        channel_url: channelUrlFromLocation(),
        channel_name: channelNameFromPage(),
        observed_at: new Date().toISOString(),
        last_forward_at: settings.lastForwardAt || "",
        last_forward_status: settings.lastForwardStatus || "",
        details,
      };
      sendBridgeRuntimeMessage("discord-bridge:bridge-heartbeat", payload, "heartbeat").catch((error) => {
        console.warn(BRIDGE_LOG_PREFIX, errorMessage(error));
      });
    },
  );
}

function primeVisibleMessages() {
  if (!isCurrentChannelEnabled()) return;
  for (const node of document.querySelectorAll(messageSelector())) {
    const eventId = stableEventId(node);
    if (eventId) rememberSeen(eventId);
  }
}

function scanVisibleMessages() {
  if (!isCurrentChannelEnabled()) return;
  for (const node of document.querySelectorAll(messageSelector())) {
    captureMessage(node);
  }
}

function scanNode(node) {
  if (!isCurrentChannelEnabled()) return;
  if (node.matches && node.matches(messageSelector())) {
    captureMessage(node);
  }
  if (node.querySelectorAll) {
    for (const messageNode of node.querySelectorAll(messageSelector())) {
      captureMessage(messageNode);
    }
  }
}

function messageSelector() {
  return '[data-list-item-id^="chat-messages___"], [id^="chat-messages-"]';
}

function captureMessage(node) {
  if (!isCurrentChannelEnabled()) return;
  const eventId = stableEventId(node);
  if (!eventId || rememberSeen(eventId)) return;

  const payload = {
    event_id: eventId,
    channel_id: channelIdFromLocation(),
    channel_name: channelNameFromPage(),
    author_id: authorIdFromNode(node),
    author_name: authorNameFromNode(node),
    content: contentFromNode(node),
    embeds: embedsFromNode(node),
    url: location.href,
    channel_url: channelUrlFromLocation(),
    observed_at: new Date().toISOString(),
    source: "chrome-discord-bridge",
  };

  if (!payload.content && payload.embeds.length === 0) return;

  sendBridgeRuntimeMessage("discord-bridge:discord-message", payload, "message").then(() => {
    publishHeartbeat("ok", { last_event_id: payload.event_id });
  }).catch((error) => {
    const message = errorMessage(error);
    console.warn(BRIDGE_LOG_PREFIX, message);
    publishHeartbeat("forward_error", { error: message });
  });
}

function sendBridgeRuntimeMessage(type, payload, kind) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type, payload }, (response) => {
      if (chrome.runtime.lastError) {
        console.warn(
          BRIDGE_LOG_PREFIX,
          directFallbackSummary(kind),
          chrome.runtime.lastError.message,
        );
        forwardPayloadDirectly(payload, kind).then(resolve).catch(reject);
        return;
      }
      if (!response || !response.ok) {
        reject(new Error(response && response.error ? response.error : "forward failed"));
        return;
      }
      resolve(response.result);
    });
  });
}

async function forwardPayloadDirectly(payload, kind) {
  const targets = targetsForDirectPayload(payload);
  if (targets.length === 0) {
    throw new Error("no matching bridge target");
  }

  const successes = [];
  const failures = [];
  for (const target of targets) {
    try {
      const body = await forwardPayloadDirectlyToTarget(target, payload, kind);
      successes.push({ id: target.id, name: target.name, status: body.status || "accepted", body });
    } catch (error) {
      failures.push({ id: target.id, name: target.name, error: errorMessage(error) });
    }
  }
  if (successes.length === 0 && failures.length > 0) {
    throw new Error(failures.map((failure) => `${failure.name}: ${failure.error}`).join("; "));
  }

  const result = {
    status: failures.length > 0 ? "partial" : (kind === "heartbeat" ? "healthy" : "accepted"),
    targets: successes,
    failures,
  };
  await recordDirectForwardResult(kind, payload, result);
  return result;
}

function targetsForDirectPayload(payload) {
  if (payload && canonicalDiscordChannelUrl(payload.url || "")) {
    return targetsForDiscordChannel(bridgeSettings, payload.url, payload.channel_id);
  }
  return enabledBridgeTargets(bridgeSettings);
}

function directFallbackSummary(kind) {
  return kind === "heartbeat"
    ? "runtime message failed; falling back to direct heartbeat forward"
    : "runtime message failed; falling back to direct message forward";
}

async function forwardPayloadDirectlyToTarget(target, payload, kind) {
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

  const textBody = await response.text();
  let body = {};
  if (textBody) {
    try {
      body = JSON.parse(textBody);
    } catch {
      body = { text: textBody };
    }
  }
  if (!response.ok) {
    throw new Error(body.detail || body.text || `${kind} request failed with HTTP ${response.status}`);
  }
  return body;
}

function recordDirectForwardResult(kind, payload, result) {
  const now = new Date().toISOString();
  const updates = kind === "heartbeat"
    ? {
      lastHeartbeatStatus: result.status,
      lastHeartbeatAt: now,
      lastHeartbeatTargets: result.targets,
    }
    : {
      lastForwardStatus: result.status,
      lastForwardAt: now,
      lastForwardEventId: payload.event_id,
      lastForwardTargets: result.targets,
    };
  return new Promise((resolve) => chrome.storage.local.set(updates, resolve));
}

function stableEventId(node) {
  const listId = node.getAttribute("data-list-item-id");
  if (listId) return canonicalMessageEventId(listId);
  const id = node.id;
  if (id) return canonicalMessageEventId(id);
  const content = contentFromNode(node);
  if (!content) return "";
  return `dom:${channelIdFromLocation()}:${hashText(`${authorNameFromNode(node)}:${content}`)}`;
}

function canonicalMessageEventId(value) {
  const raw = String(value || "");
  const match = raw.match(/chat-messages-(\d+)-(\d+)/);
  if (match) return `chat-messages-${match[1]}-${match[2]}`;
  return raw;
}

function rememberSeen(eventId) {
  if (observedIds.has(eventId)) return true;
  observedIds.add(eventId);
  observedOrder.push(eventId);
  while (observedOrder.length > MAX_OBSERVED) {
    const old = observedOrder.shift();
    observedIds.delete(old);
  }
  return false;
}

function channelIdFromLocation() {
  return channelIdFromDiscordUrl(location.href) || "chrome-visible-discord";
}

function channelUrlFromLocation() {
  return canonicalDiscordChannelUrl(location.href) || location.href;
}

function channelNameFromPage() {
  const ariaHeading = document.querySelector('[data-list-id="chat-messages"] [role="heading"], [aria-label*="Channel header"] h1');
  const titleText = ariaHeading ? text(ariaHeading) : "";
  if (titleText) return titleText.replace(/^#\s*/, "");
  const title = document.title || "";
  return title.split("|")[0].replace(/^#/, "").trim() || channelIdFromLocation();
}

function authorIdFromNode(node) {
  const avatar = node.querySelector('img[src*="/avatars/"], img[src*="/embed/avatars/"]');
  if (!avatar) return null;
  const match = avatar.src.match(/\/avatars\/(\d+)\//);
  return match ? match[1] : null;
}

function authorNameFromNode(node) {
  const selectors = [
    '[class*="username"]',
    'h3 [role="button"]',
    'h3 span',
    '[data-slate-node="element"] strong',
  ];
  for (const selector of selectors) {
    const found = node.querySelector(selector);
    const value = text(found);
    if (value) return value;
  }
  return "Discord User";
}

function contentFromNode(node) {
  const selectors = [
    '[id^="message-content-"]',
    '[class*="markup"]',
  ];
  const parts = [];
  for (const selector of selectors) {
    for (const found of node.querySelectorAll(selector)) {
      const value = text(found);
      if (value && !parts.includes(value)) parts.push(value);
    }
    if (parts.length > 0) break;
  }
  return parts.join("\n").trim();
}

function embedsFromNode(node) {
  const embeds = [];
  for (const embedNode of node.querySelectorAll('[class*="embedWrapper"], article')) {
    const embedText = text(embedNode);
    if (!embedText) continue;
    embeds.push({
      title: "",
      description: embedText,
      fields: [],
      footer_text: "",
    });
  }
  return embeds.slice(0, 5);
}

function text(node) {
  return node && node.innerText ? node.innerText.replace(/\s+\n/g, "\n").trim() : "";
}

function hashText(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function errorMessage(error) {
  return String(error && error.message ? error.message : error || "unknown error");
}
