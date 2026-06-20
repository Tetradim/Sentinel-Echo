const DEFAULTS = {
  enabled: false,
  targetUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
  apiKey: "",
  forwardExistingOnEnable: false,
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(DEFAULTS, (settings) => {
    chrome.storage.local.set({ ...DEFAULTS, ...settings });
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "consolidation:discord-message") {
    return false;
  }

  forwardObservedMessage(message.payload)
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
  return true;
});

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
