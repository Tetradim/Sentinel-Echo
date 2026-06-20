const DEFAULTS = {
  enabled: false,
  targetUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
  heartbeatUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat",
  apiKey: "",
  forwardExistingOnEnable: false,
  lastForwardStatus: "",
  lastForwardAt: "",
  lastForwardEventId: "",
  lastHeartbeatStatus: "",
  lastHeartbeatAt: "",
};

const enabled = document.getElementById("enabled");
const forwardExistingOnEnable = document.getElementById("forwardExistingOnEnable");
const targetUrl = document.getElementById("targetUrl");
const heartbeatUrl = document.getElementById("heartbeatUrl");
const apiKey = document.getElementById("apiKey");
const status = document.getElementById("status");

chrome.storage.local.get(DEFAULTS, (settings) => {
  enabled.checked = Boolean(settings.enabled);
  forwardExistingOnEnable.checked = Boolean(settings.forwardExistingOnEnable);
  targetUrl.value = settings.targetUrl;
  heartbeatUrl.value = settings.heartbeatUrl || heartbeatUrlFor(settings.targetUrl);
  apiKey.value = settings.apiKey || "";
  renderStatus(settings);
});

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set(
    {
      enabled: enabled.checked,
      forwardExistingOnEnable: forwardExistingOnEnable.checked,
      targetUrl: targetUrl.value.trim() || DEFAULTS.targetUrl,
      heartbeatUrl: heartbeatUrl.value.trim() || heartbeatUrlFor(targetUrl.value.trim() || DEFAULTS.targetUrl),
      apiKey: apiKey.value.trim(),
    },
    () => {
      status.textContent = enabled.checked ? "Bridge enabled." : "Bridge disabled.";
    },
  );
});

enabled.addEventListener("change", () => {
  chrome.storage.local.set({ enabled: enabled.checked }, () => {
    status.textContent = enabled.checked ? "Bridge enabled." : "Bridge disabled.";
  });
});

function renderStatus(settings) {
  if (!settings.lastForwardAt) {
    status.textContent = settings.enabled ? "Enabled. Waiting for Discord messages." : "Disabled.";
    return;
  }
  status.textContent = `Last: ${settings.lastForwardStatus} at ${new Date(settings.lastForwardAt).toLocaleTimeString()}`;
  if (settings.lastHeartbeatAt) {
    status.textContent += `; health ${settings.lastHeartbeatStatus} at ${new Date(settings.lastHeartbeatAt).toLocaleTimeString()}`;
  }
}

function heartbeatUrlFor(target) {
  return String(target || DEFAULTS.targetUrl).replace(/\/message$/, "/heartbeat");
}
