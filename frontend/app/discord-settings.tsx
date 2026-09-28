/**
 * Discord Communities Settings Page
 *
 * Configure multiple Discord communities with custom alert patterns
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import {
  DiscordDigest,
  summarizeDiscordSettings,
} from '../utils/discordDigest';
import { api } from '../utils/api';
import { BACKEND_URL } from '../constants/config';

type TabType = 'communities' | 'patterns' | 'filters' | 'behaviors';
type PresetId = 'default' | 'aggressive' | 'swing' | 'theta' | 'momentum' | 'custom';

type Community = {
  id: string;
  name: string;
  channelId: string;
  enabled: boolean;
  preset: PresetId;
  autoTrade: boolean;
  simulation: boolean;
  processFollowupUpdates: boolean;
  processActionableEdits: boolean;
  allowSinglePositionInferredSell: boolean;
  allowBroadExitMatching: boolean;
  protectTrailingArmedFromContextualExits: boolean;
  trailingContextExitOverrideEnabled: boolean;
  trailingContextExitOverridePercent: number;
  dedupeByChannelUrl: boolean;
  ignoreFollowupMessages: boolean;
  allowFreshEntryAfterClose: boolean;
};

type Patterns = {
  buyKeywords: string;
  sellKeywords: string;
  avgDownKeywords: string;
  ignoreKeywords: string;
  tickerPattern: string;
  requireTicker: boolean;
  requireExpiration: boolean;
  requirePrice: boolean;
};

type Filters = {
  listenToUsers: string;
  ignoreUsers: string;
  listenToChannels: string;
  minPrice: number;
  maxPrice: number;
};

type DiscordConnectionResult = {
  success: boolean;
  message: string;
  details?: {
    monitoring_channels?: string[];
    alerts_processed?: number;
    [key: string]: unknown;
  } | null;
};

const TABS: { id: TabType; label: string }[] = [
  { id: 'communities', label: 'Communities' },
  { id: 'patterns', label: 'Patterns' },
  { id: 'filters', label: 'Filters' },
  { id: 'behaviors', label: 'Behaviors' },
];

const PRESETS: { id: PresetId; name: string; detail: string }[] = [
  { id: 'default', name: 'Default', detail: 'Balanced parsing' },
  { id: 'aggressive', name: 'Aggressive', detail: 'Fast entries' },
  { id: 'swing', name: 'Swing', detail: 'Longer holds' },
  { id: 'theta', name: 'Theta', detail: 'Premium selling' },
  { id: 'momentum', name: 'Momentum', detail: 'Breakout signals' },
  { id: 'custom', name: 'Custom', detail: 'Manual rules' },
];

const DEFAULT_PATTERNS: Patterns = {
  buyKeywords: 'BUY,ENTRY,LONG,BTO,OPENING',
  sellKeywords: 'SELL,EXIT,CLOSE,STC,TRIM',
  avgDownKeywords: 'AVERAGE DOWN,AVG DOWN,AVERAGING,ADD TO',
  ignoreKeywords: 'WATCHLIST,WATCHING,MIGHT,PAPER',
  tickerPattern: '\\$([A-Z]{1,5})\\b',
  requireTicker: true,
  requireExpiration: true,
  requirePrice: true,
};

const DEFAULT_FILTERS: Filters = {
  listenToUsers: '',
  ignoreUsers: '',
  listenToChannels: '',
  minPrice: 0.01,
  maxPrice: 100,
};

const DEFAULT_BEHAVIORS = {
  processFollowupUpdates: true,
  processActionableEdits: true,
  allowSinglePositionInferredSell: true,
  allowBroadExitMatching: true,
  protectTrailingArmedFromContextualExits: true,
  trailingContextExitOverrideEnabled: true,
  trailingContextExitOverridePercent: 80,
  dedupeByChannelUrl: false,
  ignoreFollowupMessages: false,
  allowFreshEntryAfterClose: false,
};

const PRESET_IDS = new Set<PresetId>(['default', 'aggressive', 'swing', 'theta', 'momentum', 'custom']);
const MASKED_SECRET = '********';

function parseBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = String(value ?? '').trim().toLowerCase();
  if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
  if (['false', '0', 'no', 'off'].includes(normalized)) return false;
  return fallback;
}

function normalizePreset(value: unknown): PresetId {
  const preset = String(value || 'default').trim().toLowerCase() as PresetId;
  return PRESET_IDS.has(preset) ? preset : 'default';
}

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function uniqueList(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const clean = value.trim();
    if (clean && !seen.has(clean)) {
      seen.add(clean);
      result.push(clean);
    }
  });
  return result;
}

function patternText(value: unknown, fallback: string): string {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean).join(',');
  return fallback;
}

function patternList(value: string): string[] {
  return splitList(value).map((item) => item.toUpperCase());
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeCommunity(value: any, index: number): Community | null {
  if (!value || typeof value !== 'object') return null;
  const channelId = String(value.channelId ?? value.channel_id ?? '').trim();
  const id = String(value.id || channelId || `community-${index + 1}`);
  return {
    id,
    name: String(value.name || `Discord Channel ${channelId || index + 1}`),
    channelId,
    enabled: parseBoolean(value.enabled, true),
    preset: normalizePreset(value.preset || value.parser_format),
    autoTrade: parseBoolean(value.autoTrade ?? value.auto_trade ?? !parseBoolean(value.require_manual_confirm, false), false),
    simulation: parseBoolean(value.simulation ?? value.paper_only, true),
    processFollowupUpdates: parseBoolean(
      value.processFollowupUpdates ?? value.process_followup_updates,
      DEFAULT_BEHAVIORS.processFollowupUpdates,
    ),
    processActionableEdits: parseBoolean(
      value.processActionableEdits ?? value.process_actionable_edits,
      DEFAULT_BEHAVIORS.processActionableEdits,
    ),
    allowSinglePositionInferredSell: parseBoolean(
      value.allowSinglePositionInferredSell ?? value.allow_single_position_inferred_sell,
      DEFAULT_BEHAVIORS.allowSinglePositionInferredSell,
    ),
    allowBroadExitMatching: parseBoolean(
      value.allowBroadExitMatching ?? value.allow_broad_exit_matching,
      DEFAULT_BEHAVIORS.allowBroadExitMatching,
    ),
    protectTrailingArmedFromContextualExits: parseBoolean(
      value.protectTrailingArmedFromContextualExits ?? value.protect_trailing_armed_from_contextual_exits,
      DEFAULT_BEHAVIORS.protectTrailingArmedFromContextualExits,
    ),
    trailingContextExitOverrideEnabled: parseBoolean(
      value.trailingContextExitOverrideEnabled ?? value.trailing_context_exit_override_enabled,
      DEFAULT_BEHAVIORS.trailingContextExitOverrideEnabled,
    ),
    trailingContextExitOverridePercent: numberValue(
      value.trailingContextExitOverridePercent ?? value.trailing_context_exit_override_percent,
      DEFAULT_BEHAVIORS.trailingContextExitOverridePercent,
    ),
    dedupeByChannelUrl: parseBoolean(
      value.dedupeByChannelUrl ?? value.dedupe_by_channel_url,
      DEFAULT_BEHAVIORS.dedupeByChannelUrl,
    ),
    ignoreFollowupMessages: parseBoolean(
      value.ignoreFollowupMessages ?? value.ignore_followup_messages,
      DEFAULT_BEHAVIORS.ignoreFollowupMessages,
    ),
    allowFreshEntryAfterClose: parseBoolean(
      value.allowFreshEntryAfterClose ?? value.allow_fresh_entry_after_close,
      DEFAULT_BEHAVIORS.allowFreshEntryAfterClose,
    ),
  };
}

function communitiesFromSettings(settings: any): Community[] {
  const saved = Array.isArray(settings?.discord_communities)
    ? settings.discord_communities
        .map((community: any, index: number) => normalizeCommunity(community, index))
        .filter(Boolean) as Community[]
    : [];
  if (saved.length > 0) return saved;

  const sourceOverrides = settings?.source_overrides && typeof settings.source_overrides === 'object'
    ? settings.source_overrides
    : {};
  const channelIds = Array.isArray(settings?.discord_channel_ids)
    ? settings.discord_channel_ids.map((channelId: unknown) => String(channelId).trim()).filter(Boolean)
    : [];
  return channelIds.map((channelId: string, index: number) => {
    const source = sourceOverrides[channelId] || {};
    return {
      id: channelId || `community-${index + 1}`,
      name: String(source.name || `Discord Channel ${channelId}`),
      channelId,
      enabled: parseBoolean(source.enabled, true),
      preset: normalizePreset(source.parser_format),
      autoTrade: !parseBoolean(source.require_manual_confirm, false),
      simulation: parseBoolean(source.paper_only, false),
      processFollowupUpdates: parseBoolean(source.process_followup_updates, DEFAULT_BEHAVIORS.processFollowupUpdates),
      processActionableEdits: parseBoolean(source.process_actionable_edits, DEFAULT_BEHAVIORS.processActionableEdits),
      allowSinglePositionInferredSell: parseBoolean(source.allow_single_position_inferred_sell, DEFAULT_BEHAVIORS.allowSinglePositionInferredSell),
      allowBroadExitMatching: parseBoolean(source.allow_broad_exit_matching, DEFAULT_BEHAVIORS.allowBroadExitMatching),
      protectTrailingArmedFromContextualExits: parseBoolean(
        source.protect_trailing_armed_from_contextual_exits,
        DEFAULT_BEHAVIORS.protectTrailingArmedFromContextualExits,
      ),
      trailingContextExitOverrideEnabled: parseBoolean(
        source.trailing_context_exit_override_enabled,
        DEFAULT_BEHAVIORS.trailingContextExitOverrideEnabled,
      ),
      trailingContextExitOverridePercent: numberValue(
        source.trailing_context_exit_override_percent,
        DEFAULT_BEHAVIORS.trailingContextExitOverridePercent,
      ),
      dedupeByChannelUrl: parseBoolean(source.dedupe_by_channel_url, DEFAULT_BEHAVIORS.dedupeByChannelUrl),
      ignoreFollowupMessages: parseBoolean(source.ignore_followup_messages, DEFAULT_BEHAVIORS.ignoreFollowupMessages),
      allowFreshEntryAfterClose: parseBoolean(
        source.allow_fresh_entry_after_close,
        DEFAULT_BEHAVIORS.allowFreshEntryAfterClose,
      ),
    };
  });
}

function patternsFromResponse(patternResponse: any, requirements: any): Patterns {
  return {
    buyKeywords: patternText(patternResponse?.buy_patterns, DEFAULT_PATTERNS.buyKeywords),
    sellKeywords: patternText(patternResponse?.sell_patterns, DEFAULT_PATTERNS.sellKeywords),
    avgDownKeywords: patternText(patternResponse?.average_down_patterns, DEFAULT_PATTERNS.avgDownKeywords),
    ignoreKeywords: patternText(patternResponse?.ignore_patterns, DEFAULT_PATTERNS.ignoreKeywords),
    tickerPattern: String(patternResponse?.ticker_pattern || DEFAULT_PATTERNS.tickerPattern),
    requireTicker: parseBoolean(requirements?.requireTicker ?? requirements?.require_ticker, DEFAULT_PATTERNS.requireTicker),
    requireExpiration: parseBoolean(requirements?.requireExpiration ?? requirements?.require_expiration, DEFAULT_PATTERNS.requireExpiration),
    requirePrice: parseBoolean(requirements?.requirePrice ?? requirements?.require_price, DEFAULT_PATTERNS.requirePrice),
  };
}

function filtersFromSettings(settings: any): Filters {
  const saved = settings?.discord_filters && typeof settings.discord_filters === 'object'
    ? settings.discord_filters
    : {};
  return {
    listenToUsers: String(saved.listenToUsers ?? saved.listen_to_users ?? ''),
    ignoreUsers: String(saved.ignoreUsers ?? saved.ignore_users ?? ''),
    listenToChannels: String(saved.listenToChannels ?? saved.listen_to_channels ?? ''),
    minPrice: numberValue(saved.minPrice ?? saved.min_price, DEFAULT_FILTERS.minPrice),
    maxPrice: numberValue(saved.maxPrice ?? saved.max_price, DEFAULT_FILTERS.maxPrice),
  };
}

function buildSourceOverrides(communities: Community[], existing: any): Record<string, any> {
  const source_overrides = existing && typeof existing === 'object' ? { ...existing } : {};
  communities.forEach((community) => {
    const key = community.channelId.trim() || community.id;
    if (!key) return;
    const previous = source_overrides[key] && typeof source_overrides[key] === 'object' ? source_overrides[key] : {};
    source_overrides[key] = {
      ...previous,
      name: community.name.trim() || community.channelId.trim() || community.id,
      enabled: community.enabled,
      paper_only: community.simulation,
      require_manual_confirm: !community.autoTrade,
      parser_format: community.preset,
      process_followup_updates: community.processFollowupUpdates,
      process_actionable_edits: community.processActionableEdits,
      allow_single_position_inferred_sell: community.allowSinglePositionInferredSell,
      allow_broad_exit_matching: community.allowBroadExitMatching,
      protect_trailing_armed_from_contextual_exits: community.protectTrailingArmedFromContextualExits,
      trailing_context_exit_override_enabled: community.trailingContextExitOverrideEnabled,
      trailing_context_exit_override_percent: community.trailingContextExitOverridePercent,
      dedupe_by_channel_url: community.dedupeByChannelUrl,
      ignore_followup_messages: community.ignoreFollowupMessages,
      allow_fresh_entry_after_close: community.allowFreshEntryAfterClose,
    };
  });
  return source_overrides;
}

function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.digestStat}>
      <Text style={[styles.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.digestStatLabel}>{label}</Text>
    </View>
  );
}

function DiscordBriefing({ digest }: { digest: DiscordDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#68779b';
  const warnings = digest.warningItems.slice(0, 3);

  return (
    <View style={[styles.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={styles.digestTop}>
        <View style={styles.digestTitleBlock}>
          <Text style={styles.digestEyebrow}>SIGNAL READINESS</Text>
          <Text style={styles.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={styles.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[styles.communityBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[styles.communityBadgeValue, { color: toneColor }]}>{digest.enabledCommunities}</Text>
          <Text style={styles.communityBadgeLabel}>enabled</Text>
        </View>
      </View>

      <View style={styles.digestStats}>
        <DigestStat label="Sources" value={`${digest.enabledCommunities}/${digest.totalCommunities}`} />
        <DigestStat label="Auto" value={String(digest.autoTradeCommunities)} color={digest.autoTradeCommunities ? '#f59e0b' : undefined} />
        <DigestStat label="Required" value={`${digest.requiredFields}/3`} />
        <DigestStat label="Range" value={digest.priceRangeLabel} />
      </View>

      <View style={styles.warningList}>
        {warnings.length > 0 ? warnings.map((warning) => (
          <View key={warning.title} style={styles.warningRow}>
            <Ionicons name="warning-outline" size={14} color="#f59e0b" />
            <View style={styles.warningCopy}>
              <Text style={styles.warningTitle}>{warning.title}</Text>
              <Text style={styles.warningDetail}>{warning.detail}</Text>
            </View>
          </View>
        )) : (
          <View style={styles.warningRow}>
            <Ionicons name="checkmark-circle-outline" size={14} color="#22c55e" />
            <Text style={styles.clearText}>Communities, required fields, and ignore language are aligned.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

function ToggleRow({
  title,
  detail,
  value,
  onValueChange,
}: {
  title: string;
  detail?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.toggleRow}>
      <View style={styles.toggleCopy}>
        <Text style={styles.label}>{title}</Text>
        {detail ? <Text style={styles.hint}>{detail}</Text> : null}
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        accessibilityLabel={title}
        trackColor={{ false: '#29213a', true: '#164766' }}
        thumbColor={value ? '#f43f5e' : '#68779b'}
      />
    </View>
  );
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  multiline = false,
  keyboardType = 'default',
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
  keyboardType?: 'default' | 'numeric' | 'decimal-pad';
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, multiline && styles.multilineInput]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#68779b"
        multiline={multiline}
        keyboardType={keyboardType}
        autoCapitalize="none"
      />
    </View>
  );
}

export function DiscordSettingsPage() {
  const [activeTab, setActiveTab] = useState<TabType>('communities');
  const [communities, setCommunities] = useState<Community[]>([]);
  const [patterns, setPatterns] = useState<Patterns>(DEFAULT_PATTERNS);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [discordToken, setDiscordToken] = useState('');
  const [discordTokenConfigured, setDiscordTokenConfigured] = useState(false);
  const [discordStarting, setDiscordStarting] = useState(false);
  const [discordTesting, setDiscordTesting] = useState(false);
  const [discordResult, setDiscordResult] = useState<DiscordConnectionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [sourceOverrides, setSourceOverrides] = useState<Record<string, any>>({});
  const originalState = useRef<{
    communities: Community[];
    patterns: Patterns;
    filters: Filters;
    discordTokenConfigured: boolean;
    sourceOverrides: Record<string, any>;
  } | null>(null);
  const digest = summarizeDiscordSettings(communities, patterns, filters);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [settingsRes, patternsRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/settings`),
        api.get(`${BACKEND_URL}/api/discord/alert-patterns`),
      ]);
      const settings = settingsRes.data || {};
      const loadedCommunities = communitiesFromSettings(settings);
      const loadedPatterns = patternsFromResponse(patternsRes.data || {}, settings.discord_parser_requirements || {});
      const loadedFilters = filtersFromSettings(settings);
      const loadedSourceOverrides = settings.source_overrides && typeof settings.source_overrides === 'object'
        ? settings.source_overrides
        : {};
      const hasSavedToken = Boolean(settings.discord_token_configured || (settings.discord_token && settings.discord_token !== MASKED_SECRET));

      setCommunities(loadedCommunities);
      setPatterns(loadedPatterns);
      setFilters(loadedFilters);
      setDiscordToken('');
      setDiscordTokenConfigured(hasSavedToken);
      setSourceOverrides(loadedSourceOverrides);
      originalState.current = {
        communities: loadedCommunities.map((community) => ({ ...community })),
        patterns: { ...loadedPatterns },
        filters: { ...loadedFilters },
        discordTokenConfigured: hasSavedToken,
        sourceOverrides: loadedSourceOverrides,
      };
    } catch (error) {
      console.error('Discord settings load failed:', error);
      setLoadError('Discord settings could not load. Check the backend connection and retry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const addCommunity = () => {
    setCommunities(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        name: 'New Community',
        channelId: '',
        enabled: true,
        preset: 'default',
        autoTrade: false,
        simulation: true,
        ...DEFAULT_BEHAVIORS,
      },
    ]);
  };

  const updateCommunity = <K extends keyof Community>(id: string, field: K, value: Community[K]) => {
    setCommunities(prev => prev.map((community) => (
      community.id === id ? { ...community, [field]: value } : community
    )));
  };

  const removeCommunity = (id: string) => {
    setCommunities(prev => prev.filter((community) => community.id !== id));
  };

  const updatePattern = <K extends keyof Patterns>(field: K, value: Patterns[K]) => {
    setPatterns(prev => ({ ...prev, [field]: value }));
  };

  const updateFilter = <K extends keyof Filters>(field: K, value: Filters[K]) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const resetSettings = () => {
    if (originalState.current) {
      setCommunities(originalState.current.communities.map((community) => ({ ...community })));
      setPatterns({ ...originalState.current.patterns });
      setFilters({ ...originalState.current.filters });
      setDiscordToken('');
      setDiscordTokenConfigured(originalState.current.discordTokenConfigured);
      setSourceOverrides(originalState.current.sourceOverrides);
      return;
    }
    fetchSettings();
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const filterChannelIds = splitList(filters.listenToChannels);
      const enabledCommunityChannelIds = communities
        .filter((community) => community.enabled)
        .map((community) => community.channelId.trim())
        .filter(Boolean);
      const discord_channel_ids = uniqueList([...enabledCommunityChannelIds, ...filterChannelIds]);
      const source_overrides = buildSourceOverrides(communities, sourceOverrides);
      const settingsPayload: Record<string, any> = {
        discord_channel_ids,
        source_overrides,
        discord_communities: communities,
        discord_filters: filters,
        discord_parser_requirements: {
          requireTicker: patterns.requireTicker,
          requireExpiration: patterns.requireExpiration,
          requirePrice: patterns.requirePrice,
        },
      };
      const token = discordToken.trim();
      if (token && token !== MASKED_SECRET) {
        settingsPayload.discord_token = token;
      }

      const patternsPayload = {
        buy_patterns: patternList(patterns.buyKeywords),
        sell_patterns: patternList(patterns.sellKeywords),
        average_down_patterns: patternList(patterns.avgDownKeywords),
        ignore_patterns: patternList(patterns.ignoreKeywords),
        ticker_pattern: patterns.tickerPattern,
      };

      await Promise.all([
        api.put(`${BACKEND_URL}/api/settings`, settingsPayload),
        api.put(`${BACKEND_URL}/api/discord/alert-patterns`, patternsPayload),
      ]);

      setDiscordToken('');
      setDiscordTokenConfigured(discordTokenConfigured || Boolean(token));
      setSourceOverrides(source_overrides);
      originalState.current = {
        communities: communities.map((community) => ({ ...community })),
        patterns: { ...patterns },
        filters: { ...filters },
        discordTokenConfigured: discordTokenConfigured || Boolean(token),
        sourceOverrides: source_overrides,
      };
      Alert.alert('Saved', 'Discord settings saved successfully');
    } catch (error: any) {
      console.error('Discord settings save failed:', error);
      Alert.alert('Error', error?.response?.data?.detail || 'Failed to save Discord settings');
    } finally {
      setSaving(false);
    }
  };

  const startDiscord = async () => {
    setDiscordStarting(true);
    setDiscordResult(null);
    try {
      const response = await api.post(`${BACKEND_URL}/api/discord/start`);
      const result: DiscordConnectionResult = {
        success: response.data?.success ?? true,
        message: response.data?.message || 'Discord bot start requested.',
        details: response.data?.details || response.data || null,
      };
      setDiscordResult(result);
      Alert.alert('Discord', result.message);
    } catch (error: any) {
      setDiscordResult({
        success: false,
        message: error?.response?.data?.detail || 'Failed to start Discord bot',
        details: null,
      });
    } finally {
      setDiscordStarting(false);
    }
  };

  const testDiscord = async () => {
    setDiscordTesting(true);
    setDiscordResult(null);
    try {
      const response = await api.post(`${BACKEND_URL}/api/discord/test-connection`);
      setDiscordResult({
        success: Boolean(response.data?.success),
        message: response.data?.message || 'Discord connection checked.',
        details: response.data?.details || null,
      });
    } catch (error: any) {
      setDiscordResult({
        success: false,
        message: error?.response?.data?.detail || 'Connection failed',
        details: null,
      });
    } finally {
      setDiscordTesting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>DISCORD INGESTION</Text>
            <Text style={styles.title}>Discord Configuration</Text>
          </View>
          <TouchableOpacity style={styles.addIconButton} onPress={addCommunity} accessibilityRole="button" accessibilityLabel="Add community">
            <Ionicons name="add" size={20} color="#070812" />
          </TouchableOpacity>
        </View>

        <DiscordBriefing digest={digest} />

        <View style={styles.connectionPanel}>
          <View style={styles.connectionHeader}>
            <View style={styles.connectionCopy}>
              <Text style={styles.sectionTitle}>Bot Connection</Text>
              <Text style={styles.sectionHint}>Start the listener and test access to the saved Discord token and channels.</Text>
            </View>
          </View>
          <View style={styles.connectionActions}>
            <TouchableOpacity
              style={[styles.connectionAction, styles.connectionPrimary, (loading || discordStarting) && styles.actionDisabled]}
              onPress={startDiscord}
              disabled={loading || discordStarting}
            >
              {discordStarting ? <ActivityIndicator size="small" color="#070812" /> : <Ionicons name="play" size={17} color="#070812" />}
              <Text style={styles.connectionPrimaryText}>{discordStarting ? 'Starting...' : 'Start Bot'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.connectionAction, styles.connectionSecondary, (loading || discordTesting) && styles.actionDisabled]}
              onPress={testDiscord}
              disabled={loading || discordTesting}
            >
              {discordTesting ? <ActivityIndicator size="small" color="#fb7185" /> : <Ionicons name="pulse-outline" size={17} color="#fb7185" />}
              <Text style={styles.connectionSecondaryText}>{discordTesting ? 'Testing...' : 'Test'}</Text>
            </TouchableOpacity>
          </View>
          {discordResult ? (
            <View style={[styles.connectionResult, discordResult.success ? styles.connectionSuccess : styles.connectionError]}>
              <View style={styles.connectionResultHeader}>
                <Ionicons
                  name={discordResult.success ? 'checkmark-circle' : 'alert-circle'}
                  size={17}
                  color={discordResult.success ? '#4ade80' : '#f87171'}
                />
                <Text style={[styles.connectionResultTitle, { color: discordResult.success ? '#4ade80' : '#f87171' }]}>
                  {discordResult.success ? 'Connected' : 'Not Connected'}
                </Text>
              </View>
              <Text style={styles.connectionResultMessage}>{discordResult.message}</Text>
              {discordResult.details?.monitoring_channels?.length ? (
                <Text style={styles.connectionResultDetail}>Channels: {discordResult.details.monitoring_channels.join(', ')}</Text>
              ) : null}
              {discordResult.details?.alerts_processed !== undefined ? (
                <Text style={styles.connectionResultDetail}>Alerts processed: {discordResult.details.alerts_processed}</Text>
              ) : null}
            </View>
          ) : null}
        </View>

        {loading && (
          <View style={styles.statusPanel}>
            <ActivityIndicator size="small" color="#fb7185" />
            <Text style={styles.statusText}>Loading saved Discord settings...</Text>
          </View>
        )}
        {loadError ? (
          <View style={styles.statusPanel}>
            <Ionicons name="warning-outline" size={16} color="#f59e0b" />
            <Text style={styles.statusText}>{loadError}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={fetchSettings}>
              <Text style={styles.retryText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={styles.tabRow}>
          {TABS.map((tab) => (
            <TouchableOpacity
              key={tab.id}
              style={[styles.tab, activeTab === tab.id && styles.tabActive]}
              onPress={() => setActiveTab(tab.id)}
            >
              <Text style={[styles.tabText, activeTab === tab.id && styles.tabTextActive]}>{tab.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {activeTab === 'communities' && (
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <View>
                <Text style={styles.sectionTitle}>Communities</Text>
                <Text style={styles.sectionHint}>Manage signal sources and automation mode per server.</Text>
              </View>
              <TouchableOpacity style={styles.miniAction} onPress={addCommunity}>
                <Ionicons name="add" size={16} color="#fb7185" />
                <Text style={styles.miniActionText}>Add</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.tokenPanel}>
              <View style={styles.tokenHeader}>
                <View>
                  <Text style={styles.sectionTitle}>Bot Token</Text>
                  <Text style={styles.sectionHint}>
                    {discordTokenConfigured ? 'A Discord token is saved. Enter a new token only when rotating it.' : 'No Discord token is saved for bot login.'}
                  </Text>
                </View>
                <View style={[styles.tokenBadge, discordTokenConfigured ? styles.tokenBadgeSaved : styles.tokenBadgeMissing]}>
                  <Text style={styles.tokenBadgeText}>{discordTokenConfigured ? 'Saved' : 'Missing'}</Text>
                </View>
              </View>
              <Field
                label="New Bot Token"
                value={discordToken}
                onChangeText={setDiscordToken}
                placeholder={discordTokenConfigured ? 'Leave blank to keep saved token' : 'Paste bot token'}
              />
            </View>

            {communities.map((community) => (
              <View key={community.id} style={styles.communityCard}>
                <View style={styles.communityTop}>
                  <View style={styles.communityTitleRow}>
                    <Switch
                      value={community.enabled}
                      onValueChange={(value) => updateCommunity(community.id, 'enabled', value)}
                      accessibilityLabel={`${community.name} enabled`}
                      trackColor={{ false: '#29213a', true: '#164766' }}
                      thumbColor={community.enabled ? '#f43f5e' : '#68779b'}
                    />
                    <View style={styles.communityTitleBlock}>
                      <Text style={styles.communityName}>{community.name}</Text>
                      <Text style={styles.communityMeta}>{community.preset.toUpperCase()} parser</Text>
                    </View>
                  </View>
                  <TouchableOpacity style={styles.removeButton} onPress={() => removeCommunity(community.id)}>
                    <Ionicons name="trash-outline" size={16} color="#f87171" />
                  </TouchableOpacity>
                </View>

                <Field
                  label="Community Name"
                  value={community.name}
                  onChangeText={(value) => updateCommunity(community.id, 'name', value)}
                  placeholder="Trading server"
                />
                <Field
                  label="Channel ID"
                  value={community.channelId}
                  onChangeText={(value) => updateCommunity(community.id, 'channelId', value)}
                  placeholder="123456789"
                  keyboardType="numeric"
                />

                <Text style={styles.label}>Preset</Text>
                <View style={styles.presetGrid}>
                  {PRESETS.map((preset) => (
                    <TouchableOpacity
                      key={preset.id}
                      style={[styles.presetButton, community.preset === preset.id && styles.presetButtonActive]}
                      onPress={() => updateCommunity(community.id, 'preset', preset.id)}
                    >
                      <Text style={[styles.presetTitle, community.preset === preset.id && styles.presetTitleActive]}>
                        {preset.name}
                      </Text>
                      <Text style={styles.presetDetail}>{preset.detail}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <ToggleRow
                  title="Auto Trade"
                  detail="Allow parsed alerts from this community to route into execution."
                  value={community.autoTrade}
                  onValueChange={(value) => updateCommunity(community.id, 'autoTrade', value)}
                />
                <ToggleRow
                  title="Simulation"
                  detail="Keep this community in paper trading mode."
                  value={community.simulation}
                  onValueChange={(value) => updateCommunity(community.id, 'simulation', value)}
                />
              </View>
            ))}
            {communities.length === 0 && !loading ? (
              <View style={styles.emptyPanel}>
                <Text style={styles.emptyTitle}>No Discord channels saved</Text>
                <Text style={styles.emptyDetail}>Add a community and channel ID, then save to start monitoring it.</Text>
              </View>
            ) : null}
          </View>
        )}

        {activeTab === 'patterns' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Alert Patterns</Text>
            <Text style={styles.sectionHint}>Tune the parser vocabulary used before an alert becomes actionable.</Text>
            <Field
              label="Buy Keywords"
              value={patterns.buyKeywords}
              onChangeText={(value) => updatePattern('buyKeywords', value)}
              placeholder="BUY,ENTRY,LONG,BTO"
              multiline
            />
            <Field
              label="Sell Keywords"
              value={patterns.sellKeywords}
              onChangeText={(value) => updatePattern('sellKeywords', value)}
              placeholder="SELL,EXIT,CLOSE,STC"
              multiline
            />
            <Field
              label="Average Down Keywords"
              value={patterns.avgDownKeywords}
              onChangeText={(value) => updatePattern('avgDownKeywords', value)}
              placeholder="AVERAGE DOWN,AVG DOWN"
              multiline
            />
            <Field
              label="Ignore Keywords"
              value={patterns.ignoreKeywords}
              onChangeText={(value) => updatePattern('ignoreKeywords', value)}
              placeholder="WATCHLIST,PAPER"
              multiline
            />
            <Field
              label="Ticker Pattern"
              value={patterns.tickerPattern}
              onChangeText={(value) => updatePattern('tickerPattern', value)}
              placeholder="\\$([A-Z]{1,5})\\b"
            />

            <View style={styles.requirementPanel}>
              <Text style={styles.requirementTitle}>Required Fields</Text>
              <ToggleRow
                title="Ticker"
                value={patterns.requireTicker}
                onValueChange={(value) => updatePattern('requireTicker', value)}
              />
              <ToggleRow
                title="Expiration"
                value={patterns.requireExpiration}
                onValueChange={(value) => updatePattern('requireExpiration', value)}
              />
              <ToggleRow
                title="Price"
                value={patterns.requirePrice}
                onValueChange={(value) => updatePattern('requirePrice', value)}
              />
            </View>
          </View>
        )}

        {activeTab === 'filters' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Message Filters</Text>
            <Text style={styles.sectionHint}>Constrain who and what the parser listens to before keyword matching.</Text>
            <Field
              label="Listen To Users"
              value={filters.listenToUsers}
              onChangeText={(value) => updateFilter('listenToUsers', value)}
              placeholder="user123, user456"
              multiline
            />
            <Field
              label="Ignore Users"
              value={filters.ignoreUsers}
              onChangeText={(value) => updateFilter('ignoreUsers', value)}
              placeholder="baduser"
              multiline
            />
            <Field
              label="Listen To Channels"
              value={filters.listenToChannels}
              onChangeText={(value) => updateFilter('listenToChannels', value)}
              placeholder="123456, 789012"
              multiline
            />
            <View style={styles.twoColumn}>
              <Field
                label="Min Price"
                value={String(filters.minPrice)}
                onChangeText={(value) => updateFilter('minPrice', Number(value))}
                keyboardType="decimal-pad"
              />
              <Field
                label="Max Price"
                value={String(filters.maxPrice)}
                onChangeText={(value) => updateFilter('maxPrice', Number(value))}
                keyboardType="decimal-pad"
              />
            </View>
          </View>
        )}

        {activeTab === 'behaviors' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Behaviors</Text>
            <Text style={styles.sectionHint}>Source-specific compatibility switches for analyst conversation parsing.</Text>

            {communities.map((community) => (
              <View key={community.id} style={styles.communityCard}>
                <View style={styles.communityTop}>
                  <View style={styles.communityTitleBlock}>
                    <Text style={styles.communityName}>{community.name}</Text>
                    <Text style={styles.communityMeta}>{community.channelId || 'No channel ID saved'}</Text>
                  </View>
                </View>
                <ToggleRow
                  title="Process Follow-Up Updates"
                  detail="Treat profit updates and fill notes as state changes for active positions."
                  value={community.processFollowupUpdates}
                  onValueChange={(value) => updateCommunity(community.id, 'processFollowupUpdates', value)}
                />
                <ToggleRow
                  title="Process Actionable Edits"
                  detail="Re-parse Discord edits when a message changes into a sell, trim, close, or average-down instruction."
                  value={community.processActionableEdits}
                  onValueChange={(value) => updateCommunity(community.id, 'processActionableEdits', value)}
                />
                <ToggleRow
                  title="Infer Single-Position Sells"
                  detail="Allow a sell missing expiration to close the only matching open contract."
                  value={community.allowSinglePositionInferredSell}
                  onValueChange={(value) => updateCommunity(community.id, 'allowSinglePositionInferredSell', value)}
                />
                <ToggleRow
                  title="Broad Exit Matching"
                  detail="Allow broad SOLD, TRIM, and CLOSE messages to match open contracts when the match is unambiguous."
                  value={community.allowBroadExitMatching}
                  onValueChange={(value) => updateCommunity(community.id, 'allowBroadExitMatching', value)}
                />
                <ToggleRow
                  title="Protect Trailing Runners"
                  detail="Ignore broad or inferred sell messages after a contract reaches trailing activation. Exact contract exits still close it."
                  value={community.protectTrailingArmedFromContextualExits}
                  onValueChange={(value) => updateCommunity(community.id, 'protectTrailingArmedFromContextualExits', value)}
                />
                <ToggleRow
                  title="Obey Large Exact Exits"
                  detail="Allow a contract-specific sell at or above the threshold to override trailing protection, even when expiration is omitted."
                  value={community.trailingContextExitOverrideEnabled}
                  onValueChange={(value) => updateCommunity(community.id, 'trailingContextExitOverrideEnabled', value)}
                />
                <View style={styles.field}>
                  <Text style={styles.label}>Exact Exit Override Threshold (%)</Text>
                  <TextInput
                    style={[styles.input, !community.trailingContextExitOverrideEnabled && styles.inputDisabled]}
                    value={String(community.trailingContextExitOverridePercent)}
                    onChangeText={(value) => updateCommunity(
                      community.id,
                      'trailingContextExitOverridePercent',
                      Number(value),
                    )}
                    keyboardType="numeric"
                    editable={community.trailingContextExitOverrideEnabled}
                  />
                </View>
                <ToggleRow
                  title="Legacy Channel URL Dedupe"
                  detail="Use channel-only Discord URLs as duplicate identity for sources that need older Chrome parsing behavior."
                  value={community.dedupeByChannelUrl}
                  onValueChange={(value) => updateCommunity(community.id, 'dedupeByChannelUrl', value)}
                />
                <ToggleRow
                  title="Ignore Follow-Up Messages"
                  detail="Skip follow-up messages instead of using them to update active position marks."
                  value={community.ignoreFollowupMessages}
                  onValueChange={(value) => updateCommunity(community.id, 'ignoreFollowupMessages', value)}
                />
                <ToggleRow
                  title="Allow Fresh Same-Contract Entries"
                  detail="Permit a new alert ID to reopen a contract closed earlier in the session. Reposts of the same alert remain blocked."
                  value={community.allowFreshEntryAfterClose}
                  onValueChange={(value) => updateCommunity(community.id, 'allowFreshEntryAfterClose', value)}
                />
              </View>
            ))}
            {communities.length === 0 && !loading ? (
              <View style={styles.emptyPanel}>
                <Text style={styles.emptyTitle}>No Discord channels saved</Text>
                <Text style={styles.emptyDetail}>Add a community before tuning source behaviors.</Text>
              </View>
            ) : null}
          </View>
        )}

        <View style={styles.actionRow}>
          <TouchableOpacity style={[styles.secondaryAction, loading && styles.actionDisabled]} onPress={resetSettings} disabled={loading || saving}>
            <Ionicons name="refresh-outline" size={18} color="#fb7185" />
            <Text style={styles.secondaryActionText}>Reset</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.primaryAction, (loading || saving) && styles.actionDisabled]} onPress={saveSettings} disabled={loading || saving}>
            {saving ? <ActivityIndicator size="small" color="#070812" /> : <Ionicons name="save-outline" size={18} color="#070812" />}
            <Text style={styles.primaryActionText}>{saving ? 'Saving...' : 'Save Discord Settings'}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export default DiscordSettingsPage;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050416' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 },
  eyebrow: { color: '#f43f5e', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { color: '#edf3ff', fontSize: 26, fontWeight: '900' },
  addIconButton: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: '#f43f5e',
    alignItems: 'center',
    justifyContent: 'center',
  },
  digestCard: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginBottom: 12,
  },
  digestTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  digestTitleBlock: { flex: 1 },
  digestEyebrow: { color: '#68779b', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle: { color: '#edf3ff', fontSize: 18, fontWeight: '900' },
  digestDetail: { color: '#aec0e5', fontSize: 12, lineHeight: 17, marginTop: 3 },
  communityBadge: { minWidth: 78, height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  communityBadgeValue: { fontSize: 18, fontWeight: '900' },
  communityBadgeLabel: { color: '#68779b', fontSize: 10, fontWeight: '800', marginTop: 1 },
  digestStats: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(41, 33, 58, 0.82)',
  },
  digestStat: { flex: 1, alignItems: 'center' },
  digestStatValue: { color: '#edf3ff', fontSize: 13, fontWeight: '900' },
  digestStatLabel: { color: '#68779b', fontSize: 9, fontWeight: '800', marginTop: 3 },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#18283c',
    padding: 10,
  },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#68779b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#aec0e5', flex: 1, fontSize: 12, fontWeight: '700' },
  connectionPanel: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderColor: '#29213a',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14,
  },
  connectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  connectionCopy: { flex: 1 },
  connectionActions: { flexDirection: 'row', gap: 10, marginTop: 12 },
  connectionAction: {
    minHeight: 46,
    borderRadius: 9,
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: 12,
  },
  connectionPrimary: { backgroundColor: '#f43f5e' },
  connectionSecondary: {
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    borderColor: '#f43f5e',
    borderWidth: 1,
  },
  connectionPrimaryText: { color: '#070812', fontSize: 14, fontWeight: '900' },
  connectionSecondaryText: { color: '#fb7185', fontSize: 14, fontWeight: '900' },
  connectionResult: {
    borderRadius: 9,
    borderWidth: 1,
    marginTop: 12,
    padding: 11,
  },
  connectionSuccess: { backgroundColor: '#052e16', borderColor: '#22c55e' },
  connectionError: { backgroundColor: '#2d1515', borderColor: '#ef4444' },
  connectionResultHeader: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 5 },
  connectionResultTitle: { fontSize: 13, fontWeight: '900' },
  connectionResultMessage: { color: '#aec0e5', fontSize: 12, fontWeight: '700', lineHeight: 17 },
  connectionResultDetail: { color: '#68779b', fontSize: 11, fontWeight: '700', marginTop: 4 },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  statusPanel: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderColor: '#29213a',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 12,
    padding: 10,
  },
  statusText: { color: '#aec0e5', flex: 1, fontSize: 12, fontWeight: '700' },
  retryButton: {
    borderColor: '#164766',
    borderRadius: 6,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  retryText: { color: '#fb7185', fontSize: 11, fontWeight: '900' },
  tab: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderColor: '#29213a',
    borderRadius: 8,
    borderWidth: 1,
    paddingVertical: 10,
  },
  tabActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  tabText: { color: '#68779b', fontSize: 13, fontWeight: '800' },
  tabTextActive: { color: '#fb7185' },
  section: {
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#29213a',
    marginBottom: 12,
  },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 },
  sectionTitle: { color: '#edf3ff', fontSize: 18, fontWeight: '900', marginBottom: 4 },
  sectionHint: { color: '#68779b', fontSize: 12, lineHeight: 16, maxWidth: 260 },
  miniAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#164766',
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  miniActionText: { color: '#fb7185', fontSize: 12, fontWeight: '900' },
  tokenPanel: {
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#29213a',
    padding: 12,
    marginBottom: 12,
  },
  tokenHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, marginBottom: 10 },
  tokenBadge: {
    alignItems: 'center',
    borderRadius: 999,
    height: 26,
    justifyContent: 'center',
    minWidth: 68,
    paddingHorizontal: 10,
  },
  tokenBadgeSaved: { backgroundColor: 'rgba(34, 197, 94, 0.18)' },
  tokenBadgeMissing: { backgroundColor: 'rgba(245, 158, 11, 0.18)' },
  tokenBadgeText: { color: '#edf3ff', fontSize: 11, fontWeight: '900' },
  communityCard: {
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#29213a',
    padding: 14,
    marginBottom: 12,
  },
  communityTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  communityTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 },
  communityTitleBlock: { flex: 1 },
  communityName: { color: '#edf3ff', fontSize: 16, fontWeight: '900' },
  communityMeta: { color: '#68779b', fontSize: 10, fontWeight: '800', marginTop: 2 },
  removeButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    backgroundColor: '#2d1515',
    alignItems: 'center',
    justifyContent: 'center',
  },
  field: { flex: 1, marginBottom: 14 },
  label: { color: '#aec0e5', fontSize: 13, fontWeight: '800', marginBottom: 6 },
  hint: { color: '#68779b', fontSize: 12, lineHeight: 16 },
  input: {
    minHeight: 46,
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderColor: '#29213a',
    borderRadius: 8,
    borderWidth: 1,
    color: '#edf3ff',
    fontSize: 15,
    fontWeight: '700',
    paddingHorizontal: 12,
  },
  inputDisabled: { opacity: 0.5 },
  multilineInput: { minHeight: 72, paddingTop: 10, textAlignVertical: 'top' },
  presetGrid: { gap: 8, marginBottom: 12 },
  presetButton: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#29213a',
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    padding: 11,
  },
  presetButtonActive: { borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.18)' },
  presetTitle: { color: '#edf3ff', fontSize: 13, fontWeight: '900' },
  presetTitleActive: { color: '#fb7185' },
  presetDetail: { color: '#68779b', fontSize: 11, fontWeight: '700', marginTop: 2 },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: '#29213a',
  },
  toggleCopy: { flex: 1 },
  requirementPanel: {
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#29213a',
    padding: 12,
  },
  requirementTitle: { color: '#edf3ff', fontSize: 14, fontWeight: '900', marginBottom: 4 },
  twoColumn: { flexDirection: 'row', gap: 10 },
  emptyPanel: {
    borderColor: '#29213a',
    borderRadius: 10,
    borderStyle: 'dashed',
    borderWidth: 1,
    padding: 14,
  },
  emptyTitle: { color: '#edf3ff', fontSize: 14, fontWeight: '900' },
  emptyDetail: { color: '#68779b', fontSize: 12, lineHeight: 16, marginTop: 3 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 4, marginBottom: 32 },
  secondaryAction: {
    flex: 1,
    minHeight: 48,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#164766',
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  secondaryActionText: { color: '#fb7185', fontSize: 14, fontWeight: '900' },
  primaryAction: {
    flex: 1.6,
    minHeight: 48,
    borderRadius: 10,
    backgroundColor: '#f43f5e',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  actionDisabled: { opacity: 0.55 },
  primaryActionText: { color: '#070812', fontSize: 14, fontWeight: '900' },
});
