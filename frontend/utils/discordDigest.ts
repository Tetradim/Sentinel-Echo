import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export type DiscordDigestTone = 'live' | 'attention' | 'idle';

export interface DigestCommunity {
  id: string;
  name?: string | null;
  channelId?: string | null;
  enabled?: BooleanLike;
  autoTrade?: BooleanLike;
  simulation?: BooleanLike;
}

export interface DigestPatterns {
  buyKeywords?: string | null;
  sellKeywords?: string | null;
  ignoreKeywords?: string | null;
  requireTicker?: BooleanLike;
  requireExpiration?: BooleanLike;
  requirePrice?: BooleanLike;
}

export interface DigestFilters {
  minPrice?: number | null;
  maxPrice?: number | null;
}

export interface DiscordDigestStatus {
  title: string;
  detail: string;
  tone: DiscordDigestTone;
}

export interface DiscordDigestWarning {
  title: string;
  detail: string;
}

export interface DiscordDigest {
  primaryStatus: DiscordDigestStatus;
  warningItems: DiscordDigestWarning[];
  totalCommunities: number;
  enabledCommunities: number;
  autoTradeCommunities: number;
  missingChannels: number;
  requiredFields: number;
  priceRangeLabel: string;
}

function hasText(value: string | null | undefined): boolean {
  return String(value || '').trim().length > 0;
}

function toNumber(value: number | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCurrency(value: number): string {
  if (value < 1 && value > 0) return `$${value.toFixed(2)}`;
  return `$${Number.isInteger(value) ? value : value.toFixed(2)}`;
}

export function summarizeDiscordSettings(
  communities: DigestCommunity[],
  patterns: DigestPatterns,
  filters: DigestFilters
): DiscordDigest {
  const requireTicker = parseBooleanFlag(patterns.requireTicker);
  const requireExpiration = parseBooleanFlag(patterns.requireExpiration);
  const requirePrice = parseBooleanFlag(patterns.requirePrice);

  const enabledCommunities = communities.filter((community) => parseBooleanFlag(community.enabled));
  const autoTradeCommunities = enabledCommunities.filter((community) => parseBooleanFlag(community.autoTrade)).length;
  const missingChannels = enabledCommunities.filter((community) => !hasText(community.channelId)).length;
  const liveAutoCommunities = enabledCommunities.filter(
    (community) => parseBooleanFlag(community.autoTrade) && !parseBooleanFlag(community.simulation)
  ).length;
  const requiredFields = [requireTicker, requireExpiration, requirePrice].filter(Boolean).length;

  const channelWarnings: DiscordDigestWarning[] = [];
  if (missingChannels > 0) {
    channelWarnings.push({
      title: 'Channel ID missing',
      detail: `${missingChannels} enabled communit${missingChannels === 1 ? 'y needs' : 'ies need'} a channel ID.`,
    });
  }

  const liveWarnings: DiscordDigestWarning[] = [];
  if (liveAutoCommunities > 0) {
    liveWarnings.push({
      title: 'Live auto trading',
      detail: `${liveAutoCommunities} community ${liveAutoCommunities === 1 ? 'can' : 'can'} place live orders.`,
    });
  }

  const parserWarnings: DiscordDigestWarning[] = [];
  if (!requireTicker) {
    parserWarnings.push({ title: 'Ticker optional', detail: 'Messages without tickers can enter parsing.' });
  }
  if (!requireExpiration) {
    parserWarnings.push({ title: 'Expiration optional', detail: 'Option alerts can pass without an expiration.' });
  }
  if (!requirePrice) {
    parserWarnings.push({ title: 'Price optional', detail: 'Alerts can pass without a quoted entry price.' });
  }
  if (!hasText(patterns.ignoreKeywords)) {
    parserWarnings.push({ title: 'Ignore list empty', detail: 'Watchlist or paper-only language will not be filtered.' });
  }
  if (!hasText(patterns.buyKeywords) || !hasText(patterns.sellKeywords)) {
    parserWarnings.push({ title: 'Action keywords missing', detail: 'Buy and sell terms both need coverage.' });
  }

  let primaryStatus: DiscordDigestStatus;
  if (communities.length === 0) {
    primaryStatus = {
      title: 'No Communities',
      detail: 'Add a Discord community before alerts can be parsed.',
      tone: 'idle',
    };
  } else if (channelWarnings.length > 0) {
    primaryStatus = {
      title: 'Channel Setup',
      detail: `${missingChannels} enabled communit${missingChannels === 1 ? 'y is' : 'ies are'} missing a channel.`,
      tone: 'attention',
    };
  } else if (liveWarnings.length > 0) {
    primaryStatus = {
      title: 'Live Auto Review',
      detail: `${liveAutoCommunities} community ${liveAutoCommunities === 1 ? 'has' : 'have'} live automation enabled.`,
      tone: 'attention',
    };
  } else if (parserWarnings.length > 0) {
    primaryStatus = {
      title: 'Parser Review',
      detail: `${parserWarnings.length} parsing safeguard${parserWarnings.length === 1 ? '' : 's'} are relaxed.`,
      tone: 'attention',
    };
  } else {
    primaryStatus = {
      title: 'Parser Guarded',
      detail: `${enabledCommunities.length} enabled communit${enabledCommunities.length === 1 ? 'y is' : 'ies are'} ready for signal ingestion.`,
      tone: 'live',
    };
  }

  return {
    primaryStatus,
    warningItems: [...channelWarnings, ...liveWarnings, ...parserWarnings],
    totalCommunities: communities.length,
    enabledCommunities: enabledCommunities.length,
    autoTradeCommunities,
    missingChannels,
    requiredFields,
    priceRangeLabel: `${formatCurrency(toNumber(filters.minPrice))}-${formatCurrency(toNumber(filters.maxPrice))}`,
  };
}
