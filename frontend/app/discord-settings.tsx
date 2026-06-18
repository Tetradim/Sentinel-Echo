/**
 * Discord Communities Settings Page
 *
 * Configure multiple Discord communities with custom alert patterns
 */
import React, { useState } from 'react';
import {
  Alert,
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

type TabType = 'communities' | 'patterns' | 'filters';
type PresetId = 'default' | 'aggressive' | 'swing' | 'theta' | 'momentum' | 'custom';

type Community = {
  id: string;
  name: string;
  channelId: string;
  enabled: boolean;
  preset: PresetId;
  autoTrade: boolean;
  simulation: boolean;
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

const TABS: { id: TabType; label: string }[] = [
  { id: 'communities', label: 'Communities' },
  { id: 'patterns', label: 'Patterns' },
  { id: 'filters', label: 'Filters' },
];

const PRESETS: { id: PresetId; name: string; detail: string }[] = [
  { id: 'default', name: 'Default', detail: 'Balanced parsing' },
  { id: 'aggressive', name: 'Aggressive', detail: 'Fast entries' },
  { id: 'swing', name: 'Swing', detail: 'Longer holds' },
  { id: 'theta', name: 'Theta', detail: 'Premium selling' },
  { id: 'momentum', name: 'Momentum', detail: 'Breakout signals' },
  { id: 'custom', name: 'Custom', detail: 'Manual rules' },
];

const DEFAULT_COMMUNITIES: Community[] = [
  {
    id: '1',
    name: 'Main Trading Server',
    channelId: '123456789',
    enabled: true,
    preset: 'default',
    autoTrade: false,
    simulation: true,
  },
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

function cloneCommunities(): Community[] {
  return DEFAULT_COMMUNITIES.map((community) => ({ ...community }));
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
    '#64748b';
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
        trackColor={{ false: '#1e2d3d', true: '#164766' }}
        thumbColor={value ? '#38bdf8' : '#64748b'}
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
        placeholderTextColor="#475569"
        multiline={multiline}
        keyboardType={keyboardType}
        autoCapitalize="none"
      />
    </View>
  );
}

export function DiscordSettingsPage() {
  const [activeTab, setActiveTab] = useState<TabType>('communities');
  const [communities, setCommunities] = useState<Community[]>(cloneCommunities);
  const [patterns, setPatterns] = useState<Patterns>(DEFAULT_PATTERNS);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const digest = summarizeDiscordSettings(communities, patterns, filters);

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
    setCommunities(cloneCommunities());
    setPatterns(DEFAULT_PATTERNS);
    setFilters(DEFAULT_FILTERS);
  };

  const saveSettings = () => {
    Alert.alert('Saved', 'Discord settings saved successfully');
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>DISCORD INGESTION</Text>
            <Text style={styles.title}>Discord Configuration</Text>
          </View>
          <TouchableOpacity style={styles.addIconButton} onPress={addCommunity} accessibilityRole="button">
            <Ionicons name="add" size={20} color="#08111f" />
          </TouchableOpacity>
        </View>

        <DiscordBriefing digest={digest} />

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
                <Ionicons name="add" size={16} color="#7dd3fc" />
                <Text style={styles.miniActionText}>Add</Text>
              </TouchableOpacity>
            </View>

            {communities.map((community) => (
              <View key={community.id} style={styles.communityCard}>
                <View style={styles.communityTop}>
                  <View style={styles.communityTitleRow}>
                    <Switch
                      value={community.enabled}
                      onValueChange={(value) => updateCommunity(community.id, 'enabled', value)}
                      trackColor={{ false: '#1e2d3d', true: '#164766' }}
                      thumbColor={community.enabled ? '#38bdf8' : '#64748b'}
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

        <View style={styles.actionRow}>
          <TouchableOpacity style={styles.secondaryAction} onPress={resetSettings}>
            <Ionicons name="refresh-outline" size={18} color="#7dd3fc" />
            <Text style={styles.secondaryActionText}>Reset</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.primaryAction} onPress={saveSettings}>
            <Ionicons name="save-outline" size={18} color="#08111f" />
            <Text style={styles.primaryActionText}>Save Discord Settings</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export default DiscordSettingsPage;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#08111f' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 },
  eyebrow: { color: '#38bdf8', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { color: '#e2e8f0', fontSize: 26, fontWeight: '900' },
  addIconButton: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: '#38bdf8',
    alignItems: 'center',
    justifyContent: 'center',
  },
  digestCard: {
    backgroundColor: '#0b1420',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginBottom: 12,
  },
  digestTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  digestTitleBlock: { flex: 1 },
  digestEyebrow: { color: '#64748b', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle: { color: '#e2e8f0', fontSize: 18, fontWeight: '900' },
  digestDetail: { color: '#94a3b8', fontSize: 12, lineHeight: 17, marginTop: 3 },
  communityBadge: { minWidth: 78, height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  communityBadgeValue: { fontSize: 18, fontWeight: '900' },
  communityBadgeLabel: { color: '#64748b', fontSize: 10, fontWeight: '800', marginTop: 1 },
  digestStats: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#132235',
  },
  digestStat: { flex: 1, alignItems: 'center' },
  digestStatValue: { color: '#e2e8f0', fontSize: 13, fontWeight: '900' },
  digestStatLabel: { color: '#64748b', fontSize: 9, fontWeight: '800', marginTop: 3 },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#0d1826',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#18283c',
    padding: 10,
  },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#64748b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#94a3b8', flex: 1, fontSize: 12, fontWeight: '700' },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tab: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#0d1826',
    borderColor: '#1e2d3d',
    borderRadius: 8,
    borderWidth: 1,
    paddingVertical: 10,
  },
  tabActive: { backgroundColor: '#0b2136', borderColor: '#38bdf8' },
  tabText: { color: '#64748b', fontSize: 13, fontWeight: '800' },
  tabTextActive: { color: '#7dd3fc' },
  section: {
    backgroundColor: '#0d1826',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1e2d3d',
    marginBottom: 12,
  },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 },
  sectionTitle: { color: '#e2e8f0', fontSize: 18, fontWeight: '900', marginBottom: 4 },
  sectionHint: { color: '#64748b', fontSize: 12, lineHeight: 16, maxWidth: 260 },
  miniAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#164766',
    backgroundColor: '#0b2136',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  miniActionText: { color: '#7dd3fc', fontSize: 12, fontWeight: '900' },
  communityCard: {
    backgroundColor: '#111c2a',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#1e2d3d',
    padding: 14,
    marginBottom: 12,
  },
  communityTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  communityTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 },
  communityTitleBlock: { flex: 1 },
  communityName: { color: '#e2e8f0', fontSize: 16, fontWeight: '900' },
  communityMeta: { color: '#64748b', fontSize: 10, fontWeight: '800', marginTop: 2 },
  removeButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    backgroundColor: '#2d1515',
    alignItems: 'center',
    justifyContent: 'center',
  },
  field: { flex: 1, marginBottom: 14 },
  label: { color: '#94a3b8', fontSize: 13, fontWeight: '800', marginBottom: 6 },
  hint: { color: '#64748b', fontSize: 12, lineHeight: 16 },
  input: {
    minHeight: 46,
    backgroundColor: '#0d1826',
    borderColor: '#1e2d3d',
    borderRadius: 8,
    borderWidth: 1,
    color: '#e2e8f0',
    fontSize: 15,
    fontWeight: '700',
    paddingHorizontal: 12,
  },
  multilineInput: { minHeight: 72, paddingTop: 10, textAlignVertical: 'top' },
  presetGrid: { gap: 8, marginBottom: 12 },
  presetButton: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1e2d3d',
    backgroundColor: '#0d1826',
    padding: 11,
  },
  presetButtonActive: { borderColor: '#38bdf8', backgroundColor: '#0b2136' },
  presetTitle: { color: '#e2e8f0', fontSize: 13, fontWeight: '900' },
  presetTitleActive: { color: '#7dd3fc' },
  presetDetail: { color: '#64748b', fontSize: 11, fontWeight: '700', marginTop: 2 },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: '#1e2d3d',
  },
  toggleCopy: { flex: 1 },
  requirementPanel: {
    backgroundColor: '#111c2a',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1e2d3d',
    padding: 12,
  },
  requirementTitle: { color: '#e2e8f0', fontSize: 14, fontWeight: '900', marginBottom: 4 },
  twoColumn: { flexDirection: 'row', gap: 10 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 4, marginBottom: 32 },
  secondaryAction: {
    flex: 1,
    minHeight: 48,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#164766',
    backgroundColor: '#0b2136',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  secondaryActionText: { color: '#7dd3fc', fontSize: 14, fontWeight: '900' },
  primaryAction: {
    flex: 1.6,
    minHeight: 48,
    borderRadius: 10,
    backgroundColor: '#38bdf8',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  primaryActionText: { color: '#08111f', fontSize: 14, fontWeight: '900' },
});
