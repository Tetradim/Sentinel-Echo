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
  if (!message || (message.type !== "discord-bridge:bridge-ping" && message.type !== "consolidation:bridge-ping")) {
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
      chrome.runtime.sendMessage({
        type: "discord-bridge:bridge-heartbeat",
        payload: {
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
        },
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

  chrome.runtime.sendMessage({ type: "discord-bridge:discord-message", payload }, (response) => {
    if (chrome.runtime.lastError) {
      console.warn(BRIDGE_LOG_PREFIX, chrome.runtime.lastError.message);
      publishHeartbeat("forward_error", { error: chrome.runtime.lastError.message });
      return;
    }
    if (!response || !response.ok) {
      console.warn(BRIDGE_LOG_PREFIX, response && response.error ? response.error : "forward failed");
      publishHeartbeat("forward_error", { error: response && response.error ? response.error : "forward failed" });
      return;
    }
    publishHeartbeat("ok", { last_event_id: payload.event_id });
  });
}

function stableEventId(node) {
  const listId = node.getAttribute("data-list-item-id");
  if (listId) return listId;
  const id = node.id;
  if (id) return id;
  const content = contentFromNode(node);
  if (!content) return "";
  return `dom:${channelIdFromLocation()}:${hashText(`${authorNameFromNode(node)}:${content}`)}`;
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
