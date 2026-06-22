const DEFAULTS = {
  enabled: false,
  targetUrl: DEFAULT_MESSAGE_URL,
  heartbeatUrl: DEFAULT_HEARTBEAT_URL,
  apiKey: "",
  targets: [],
  forwardExistingOnEnable: false,
  autoRestartEnabled: true,
  lastForwardStatus: "",
  lastForwardAt: "",
  lastForwardEventId: "",
  lastForwardTargets: [],
  lastHeartbeatStatus: "",
  lastHeartbeatAt: "",
  lastHeartbeatTargets: [],
  lastRestartStatus: "",
  nextRestartAt: "",
};

const enabled = document.getElementById("enabled");
const forwardExistingOnEnable = document.getElementById("forwardExistingOnEnable");
const autoRestartEnabled = document.getElementById("autoRestartEnabled");
const targetUrl = document.getElementById("targetUrl");
const heartbeatUrl = document.getElementById("heartbeatUrl");
const apiKey = document.getElementById("apiKey");
const targetsJson = document.getElementById("targetsJson");
const status = document.getElementById("status");

chrome.storage.local.get(DEFAULTS, (settings) => {
  const targets = normalizeBridgeTargets(settings);
  const firstTarget = targets[0] || normalizeBridgeTargets(DEFAULTS)[0];
  enabled.checked = Boolean(settings.enabled);
  forwardExistingOnEnable.checked = Boolean(settings.forwardExistingOnEnable);
  autoRestartEnabled.checked = settings.autoRestartEnabled !== false;
  targetUrl.value = firstTarget.messageUrl;
  heartbeatUrl.value = firstTarget.heartbeatUrl || heartbeatUrlFor(firstTarget.messageUrl);
  apiKey.value = firstTarget.apiKey || "";
  targetsJson.value = JSON.stringify(targets, null, 2);
  renderStatus(settings);
});

document.getElementById("save").addEventListener("click", () => {
  let parsedTargets;
  try {
    parsedTargets = targetsJson.value.trim() ? JSON.parse(targetsJson.value) : [];
  } catch (error) {
    status.textContent = `Targets JSON is invalid: ${error.message}`;
    return;
  }

  const targets = normalizeBridgeTargets({ ...DEFAULTS, targets: Array.isArray(parsedTargets) ? parsedTargets : [] });
  const fallbackTarget = normalizeBridgeTargets({
    targetUrl: targetUrl.value.trim() || DEFAULTS.targetUrl,
    heartbeatUrl: heartbeatUrl.value.trim() || heartbeatUrlFor(targetUrl.value.trim() || DEFAULTS.targetUrl),
    apiKey: apiKey.value.trim(),
  })[0];
  if (targets.length === 0) {
    targets.push(fallbackTarget);
  } else {
    targets[0] = {
      ...targets[0],
      messageUrl: targetUrl.value.trim() || targets[0].messageUrl,
      heartbeatUrl: heartbeatUrl.value.trim() || heartbeatUrlFor(targetUrl.value.trim() || targets[0].messageUrl),
      apiKey: apiKey.value.trim(),
    };
  }

  chrome.storage.local.set(
    {
      enabled: enabled.checked,
      forwardExistingOnEnable: forwardExistingOnEnable.checked,
      autoRestartEnabled: autoRestartEnabled.checked,
      targetUrl: targets[0].messageUrl,
      heartbeatUrl: targets[0].heartbeatUrl || heartbeatUrlFor(targets[0].messageUrl),
      apiKey: targets[0].apiKey || "",
      targets,
    },
    () => {
      targetsJson.value = JSON.stringify(targets, null, 2);
      status.textContent = enabled.checked ? "Bridge enabled." : "Bridge disabled.";
    },
  );
});

enabled.addEventListener("change", () => {
  chrome.storage.local.set({ enabled: enabled.checked }, () => {
    status.textContent = enabled.checked ? "Bridge enabled." : "Bridge disabled.";
  });
});

autoRestartEnabled.addEventListener("change", () => {
  chrome.storage.local.set({ autoRestartEnabled: autoRestartEnabled.checked }, () => {
    status.textContent = autoRestartEnabled.checked ? "Auto-restart enabled." : "Auto-restart disabled.";
  });
});

function renderStatus(settings) {
  if (!settings.lastForwardAt) {
    status.textContent = settings.enabled ? "Enabled. Waiting for Discord messages." : "Disabled.";
    return;
  }
  status.textContent = `Last: ${settings.lastForwardStatus} at ${new Date(settings.lastForwardAt).toLocaleTimeString()}`;
  if (Array.isArray(settings.lastForwardTargets) && settings.lastForwardTargets.length > 0) {
    status.textContent += ` to ${settings.lastForwardTargets.map((target) => target.name || target.id).join(", ")}`;
  }
  if (settings.lastHeartbeatAt) {
    status.textContent += `; health ${settings.lastHeartbeatStatus} at ${new Date(settings.lastHeartbeatAt).toLocaleTimeString()}`;
  }
  if (settings.nextRestartAt) {
    status.textContent += `; retry ${new Date(settings.nextRestartAt).toLocaleTimeString()}`;
  }
}
