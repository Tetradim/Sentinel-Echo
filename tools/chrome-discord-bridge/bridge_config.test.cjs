const assert = require("node:assert/strict");

const {
  canonicalDiscordChannelUrl,
  channelIdFromDiscordUrl,
  normalizeBridgeTargets,
  targetsForDiscordChannel,
} = require("./bridge_config.js");

function test(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("canonicalDiscordChannelUrl keeps only guild and channel", () => {
  assert.equal(
    canonicalDiscordChannelUrl("https://discord.com/channels/111/222/333?jump=1#frag"),
    "https://discord.com/channels/111/222",
  );
  assert.equal(
    canonicalDiscordChannelUrl("https://canary.discord.com/channels/@me/444"),
    "https://discord.com/channels/@me/444",
  );
});

test("channelIdFromDiscordUrl extracts the channel id", () => {
  assert.equal(channelIdFromDiscordUrl("https://discord.com/channels/111/222/333"), "222");
  assert.equal(channelIdFromDiscordUrl("https://discord.com/app"), "");
});

test("normalizeBridgeTargets migrates legacy Consolidation settings", () => {
  const targets = normalizeBridgeTargets({
    targetUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
    heartbeatUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/heartbeat",
    apiKey: "local-key",
  });

  assert.equal(targets.length, 1);
  assert.equal(targets[0].id, "consolidation");
  assert.equal(targets[0].name, "Consolidation");
  assert.equal(targets[0].enabled, true);
  assert.equal(targets[0].apiKey, "local-key");
});

test("targetsForDiscordChannel filters by channel URL and channel id", () => {
  const settings = {
    targets: [
      {
        id: "consolidation",
        enabled: true,
        messageUrl: "http://127.0.0.1:8003/api/discord/chrome-bridge/message",
        allowedChannelUrls: ["https://discord.com/channels/111/222"],
      },
      {
        id: "sentinel-edge",
        enabled: true,
        messageUrl: "http://127.0.0.1:8010/api/discord/chrome-bridge/message",
        allowedChannelIds: ["333"],
      },
      {
        id: "crypto-bot",
        enabled: false,
        messageUrl: "http://127.0.0.1:8020/api/discord/chrome-bridge/message",
      },
    ],
  };

  assert.deepEqual(
    targetsForDiscordChannel(settings, "https://discord.com/channels/111/222/999").map((target) => target.id),
    ["consolidation"],
  );
  assert.deepEqual(
    targetsForDiscordChannel(settings, "https://discord.com/channels/111/333").map((target) => target.id),
    ["sentinel-edge"],
  );
});

test("targetsForDiscordChannel allows enabled targets without filters", () => {
  const settings = {
    targets: [
      {
        id: "simulation",
        enabled: true,
        messageUrl: "http://127.0.0.1:9200/api/discord/chrome-bridge/message",
      },
    ],
  };

  assert.deepEqual(
    targetsForDiscordChannel(settings, "https://discord.com/channels/111/222").map((target) => target.id),
    ["simulation"],
  );
});
