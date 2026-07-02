(function bridgeConfigModule(root) {
  const DEFAULT_MESSAGE_URL = "http://127.0.0.1:8003/api/discord/chrome-bridge/message";
  const DEFAULT_HEARTBEAT_URL = "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat";
  const LOCAL_SENTINEL_ECHO_FALLBACK_PORTS = ["8010", "8003"];

  function heartbeatUrlFor(messageUrl) {
    return String(messageUrl || DEFAULT_MESSAGE_URL).replace(/\/message$/, "/heartbeat");
  }

  function canonicalDiscordChannelUrl(value) {
    if (!value) return "";
    const text = String(value).trim();
    const match = text.match(/^https:\/\/(?:canary\.|ptb\.)?discord\.com\/channels\/(@me|\d+)\/(\d+)/i);
    if (!match) return "";
    return `https://discord.com/channels/${match[1]}/${match[2]}`;
  }

  function channelIdFromDiscordUrl(value) {
    const canonical = canonicalDiscordChannelUrl(value);
    const match = canonical.match(/\/channels\/(?:@me|\d+)\/(\d+)$/);
    return match ? match[1] : "";
  }

  function splitList(value) {
    if (Array.isArray(value)) {
      return value.flatMap((item) => splitList(item));
    }
    if (value === null || value === undefined) return [];
    return String(value)
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function coerceEnabled(value, fallback = true) {
    if (value === null || value === undefined || value === "") return fallback;
    if (typeof value === "boolean") return value;
    const text = String(value).trim().toLowerCase();
    if (["1", "true", "yes", "on", "enabled"].includes(text)) return true;
    if (["0", "false", "no", "off", "disabled"].includes(text)) return false;
    return fallback;
  }

  function normalizeBridgeTarget(rawTarget, index = 0) {
    const raw = rawTarget && typeof rawTarget === "object" ? rawTarget : {};
    const messageUrl = String(raw.messageUrl || raw.targetUrl || "").trim();
    if (!messageUrl) return null;

    const allowedChannelUrls = splitList(raw.allowedChannelUrls || raw.channelUrls)
      .map(canonicalDiscordChannelUrl)
      .filter(Boolean);
    const idsFromUrls = allowedChannelUrls.map(channelIdFromDiscordUrl).filter(Boolean);
    const allowedChannelIds = Array.from(
      new Set([...splitList(raw.allowedChannelIds || raw.channelIds), ...idsFromUrls].map(String)),
    );

    return {
      id: String(raw.id || raw.name || `target-${index + 1}`).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-"),
      name: String(raw.name || raw.id || `Target ${index + 1}`).trim(),
      enabled: coerceEnabled(raw.enabled, true),
      messageUrl,
      heartbeatUrl: String(raw.heartbeatUrl || heartbeatUrlFor(messageUrl)).trim(),
      apiKey: String(raw.apiKey || ""),
      allowedChannelUrls,
      allowedChannelIds,
    };
  }

  function legacySentinelEchoTarget(settings) {
    const raw = settings && typeof settings === "object" ? settings : {};
    return normalizeBridgeTarget(
      {
        id: "sentinel-echo",
        name: "Sentinel Echo",
        enabled: true,
        messageUrl: raw.targetUrl || DEFAULT_MESSAGE_URL,
        heartbeatUrl: raw.heartbeatUrl || heartbeatUrlFor(raw.targetUrl || DEFAULT_MESSAGE_URL),
        apiKey: raw.apiKey || "",
      },
      0,
    );
  }

  function normalizeBridgeTargets(settings) {
    const raw = settings && typeof settings === "object" ? settings : {};
    const configuredTargets = Array.isArray(raw.targets) ? raw.targets : [];
    const normalized = configuredTargets
      .map((target, index) => normalizeBridgeTarget(target, index))
      .filter(Boolean);
    if (normalized.length > 0) return normalized;
    return [legacySentinelEchoTarget(raw)].filter(Boolean);
  }

  function targetMatchesDiscordChannel(target, url, channelId) {
    if (!target || !target.enabled) return false;
    const allowedUrls = target.allowedChannelUrls || [];
    const allowedIds = target.allowedChannelIds || [];
    if (allowedUrls.length === 0 && allowedIds.length === 0) return true;

    const canonicalUrl = canonicalDiscordChannelUrl(url);
    const resolvedChannelId = String(channelId || channelIdFromDiscordUrl(url) || "");
    return (
      (canonicalUrl && allowedUrls.includes(canonicalUrl)) ||
      (resolvedChannelId && allowedIds.includes(resolvedChannelId))
    );
  }

  function targetsForDiscordChannel(settings, url, channelId) {
    return normalizeBridgeTargets(settings).filter((target) => targetMatchesDiscordChannel(target, url, channelId));
  }

  function enabledBridgeTargets(settings) {
    return normalizeBridgeTargets(settings).filter((target) => target.enabled);
  }

  function localSentinelEchoFallbackUrls(target, kind, primaryUrl) {
    if (!isLocalSentinelEchoTarget(target)) return [];

    let url;
    try {
      url = new URL(String(primaryUrl || ""));
    } catch {
      return [];
    }

    if (!isLocalHost(url.hostname) || !url.pathname.endsWith(`/chrome-bridge/${kind}`)) {
      return [];
    }

    const primaryPort = url.port || (url.protocol === "https:" ? "443" : "80");
    return LOCAL_SENTINEL_ECHO_FALLBACK_PORTS
      .filter((port) => port !== primaryPort)
      .map((port) => {
        const fallback = new URL(url.href);
        fallback.port = port;
        return fallback.href;
      });
  }

  function isLocalSentinelEchoTarget(target) {
    if (!target || target.enabled === false) return false;
    const id = String(target.id || "").toLowerCase();
    const name = String(target.name || "").toLowerCase();
    const messageUrl = String(target.messageUrl || target.targetUrl || "");
    if (!id.includes("sentinel-echo") && !name.includes("sentinel-echo")) return false;
    try {
      const url = new URL(messageUrl);
      return isLocalHost(url.hostname);
    } catch {
      return false;
    }
  }

  function isLocalHost(hostname) {
    return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1" || hostname === "[::1]";
  }

  const api = {
    DEFAULT_MESSAGE_URL,
    DEFAULT_HEARTBEAT_URL,
    canonicalDiscordChannelUrl,
    channelIdFromDiscordUrl,
    enabledBridgeTargets,
    heartbeatUrlFor,
    localSentinelEchoFallbackUrls,
    normalizeBridgeTarget,
    normalizeBridgeTargets,
    targetMatchesDiscordChannel,
    targetsForDiscordChannel,
  };

  Object.assign(root, api);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
