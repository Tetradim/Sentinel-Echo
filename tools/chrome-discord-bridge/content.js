const BRIDGE_LOG_PREFIX = "[Consolidation Bridge]";
const observedIds = new Set();
const observedOrder = [];
const MAX_OBSERVED = 2000;

let enabled = false;
let forwardExistingOnEnable = false;
let observer = null;

chrome.storage.local.get({ enabled: false, forwardExistingOnEnable: false }, (settings) => {
  enabled = Boolean(settings.enabled);
  forwardExistingOnEnable = Boolean(settings.forwardExistingOnEnable);
  startObserver();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (changes.forwardExistingOnEnable) {
    forwardExistingOnEnable = Boolean(changes.forwardExistingOnEnable.newValue);
  }
  if (changes.enabled) {
    enabled = Boolean(changes.enabled.newValue);
    if (enabled) {
      if (forwardExistingOnEnable) {
        scanVisibleMessages();
      } else {
        primeVisibleMessages();
      }
    }
  }
});

function startObserver() {
  if (observer) return;
  observer = new MutationObserver((records) => {
    if (!enabled) return;
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          scanNode(node);
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  if (enabled && forwardExistingOnEnable) {
    scanVisibleMessages();
  } else {
    primeVisibleMessages();
  }
  console.info(BRIDGE_LOG_PREFIX, "observer ready");
}

function primeVisibleMessages() {
  for (const node of document.querySelectorAll(messageSelector())) {
    const eventId = stableEventId(node);
    if (eventId) rememberSeen(eventId);
  }
}

function scanVisibleMessages() {
  if (!enabled) return;
  for (const node of document.querySelectorAll(messageSelector())) {
    captureMessage(node);
  }
}

function scanNode(node) {
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
    observed_at: new Date().toISOString(),
    source: "chrome-discord-bridge",
  };

  if (!payload.content && payload.embeds.length === 0) return;

  chrome.runtime.sendMessage({ type: "consolidation:discord-message", payload }, (response) => {
    if (chrome.runtime.lastError) {
      console.warn(BRIDGE_LOG_PREFIX, chrome.runtime.lastError.message);
      return;
    }
    if (!response || !response.ok) {
      console.warn(BRIDGE_LOG_PREFIX, response && response.error ? response.error : "forward failed");
    }
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
  const match = location.pathname.match(/\/channels\/(?:@me|\d+)\/(\d+)/);
  return match ? match[1] : "chrome-visible-discord";
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
