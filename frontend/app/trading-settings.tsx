/**
 * Trading Settings Page
 *
 * Dedicated page for trading configuration
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
  summarizeTradingSettings,
  TradingSettingsDigest,
} from '../utils/tradingSettingsDigest';

type BrokerId = 'IBKR' | 'ALPACA' | 'TRADIER' | 'TD';
type OrderType = 'LIMIT' | 'MARKET';

type TradingSettings = {
  simulationMode: boolean;
  autoTradingEnabled: boolean;
  priceBufferEnabled: boolean;
  priceBufferPercentage: number;
  orderTimeout: number;
  retryFilledCheck: boolean;
  retryInterval: number;
  activeBroker: BrokerId;
  brokerGatewayUrl: string;
  brokerAccountId: string;
  orderType: OrderType;
};

const DEFAULT_TRADING_SETTINGS: TradingSettings = {
  simulationMode: true,
  autoTradingEnabled: true,
  priceBufferEnabled: true,
  priceBufferPercentage: 3,
  orderTimeout: 30,
  retryFilledCheck: true,
  retryInterval: 2,
  activeBroker: 'IBKR',
  brokerGatewayUrl: 'https://localhost:5000',
  brokerAccountId: '',
  orderType: 'LIMIT',
};

const BROKERS: { id: BrokerId; label: string; detail: string; color: string }[] = [
  { id: 'IBKR', label: 'IBKR', detail: 'Interactive Brokers', color: '#f43f5e' },
  { id: 'ALPACA', label: 'Alpaca', detail: 'Equities and options', color: '#22c55e' },
  { id: 'TRADIER', label: 'Tradier', detail: 'Options API', color: '#f59e0b' },
  { id: 'TD', label: 'TD', detail: 'Legacy profile', color: '#a78bfa' },
];

const BUFFER_PRESETS = [1, 3, 5];

function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.digestStat}>
      <Text style={[styles.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.digestStatLabel}>{label}</Text>
    </View>
  );
}

function TradingBriefing({ digest }: { digest: TradingSettingsDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#68779b';
  const warnings = digest.warningItems.slice(0, 3);

  return (
    <View style={[styles.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={styles.digestTop}>
        <View style={styles.digestTitleBlock}>
          <Text style={styles.digestEyebrow}>EXECUTION READINESS</Text>
          <Text style={styles.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={styles.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[styles.scoreBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[styles.scoreValue, { color: toneColor }]}>{digest.safeguardCoveragePercent}%</Text>
          <Text style={styles.scoreLabel}>safe</Text>
        </View>
      </View>

      <View style={styles.digestStats}>
        <DigestStat label="Mode" value={digest.modeLabel} color={digest.modeLabel === 'Live' ? '#f59e0b' : undefined} />
        <DigestStat label="Broker" value={digest.brokerLabel} />
        <DigestStat label="Buffer" value={digest.bufferLabel} color={digest.bufferLabel === 'Off' ? '#ef4444' : undefined} />
        <DigestStat label="Timeout" value={digest.timeoutLabel} />
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
            <Text style={styles.clearText}>Broker identity, limit pricing, buffer, and retries are aligned.</Text>
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
  detail: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.toggleRow}>
      <View style={styles.toggleCopy}>
        <Text style={styles.label}>{title}</Text>
        <Text style={styles.hint}>{detail}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
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
  keyboardType = 'default',
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  keyboardType?: 'default' | 'numeric' | 'decimal-pad';
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#68779b"
        keyboardType={keyboardType}
        autoCapitalize="none"
      />
    </View>
  );
}

export function TradingSettingsPage() {
  const [settings, setSettings] = useState<TradingSettings>(DEFAULT_TRADING_SETTINGS);
  const digest = summarizeTradingSettings(settings);

  const updateSetting = <K extends keyof TradingSettings>(key: K, value: TradingSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const saveSettings = () => {
    Alert.alert('Saved', 'Trading settings saved successfully');
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>AUTOMATION</Text>
            <Text style={styles.title}>Trading Settings</Text>
          </View>
          <View style={[styles.modeBadge, settings.simulationMode ? styles.modeBadgeSim : styles.modeBadgeLive]}>
            <Ionicons
              name={settings.simulationMode ? 'flask-outline' : 'flash-outline'}
              size={14}
              color={settings.simulationMode ? '#fb7185' : '#fbbf24'}
            />
            <Text style={[styles.modeBadgeText, !settings.simulationMode && styles.modeBadgeTextLive]}>
              {settings.simulationMode ? 'SIM' : 'LIVE'}
            </Text>
          </View>
        </View>

        <TradingBriefing digest={digest} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Trading Mode</Text>
          <ToggleRow
            title="Simulation Mode"
            detail="Route alerts to paper execution instead of live broker orders."
            value={settings.simulationMode}
            onValueChange={(value) => updateSetting('simulationMode', value)}
          />
          <ToggleRow
            title="Auto Trading"
            detail="Allow parsed alerts to create orders without manual confirmation."
            value={settings.autoTradingEnabled}
            onValueChange={(value) => updateSetting('autoTradingEnabled', value)}
          />
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Price Buffer</Text>
          <ToggleRow
            title="Enable Buffer"
            detail="Place limit orders below alert price to reduce poor fills."
            value={settings.priceBufferEnabled}
            onValueChange={(value) => updateSetting('priceBufferEnabled', value)}
          />
          <View style={[styles.field, !settings.priceBufferEnabled && styles.disabledBlock]}>
            <Text style={styles.label}>Buffer Percentage</Text>
            <View style={styles.inlineInputRow}>
              <TextInput
                style={[styles.input, styles.inlineInput]}
                value={String(settings.priceBufferPercentage)}
                onChangeText={(value) => updateSetting('priceBufferPercentage', Number(value))}
                keyboardType="decimal-pad"
                editable={settings.priceBufferEnabled}
              />
              <Text style={styles.inputSuffix}>%</Text>
            </View>
            <View style={styles.presetRow}>
              {BUFFER_PRESETS.map((preset) => (
                <TouchableOpacity
                  key={preset}
                  style={[
                    styles.presetButton,
                    settings.priceBufferPercentage === preset && styles.presetButtonActive,
                    !settings.priceBufferEnabled && styles.presetButtonDisabled,
                  ]}
                  disabled={!settings.priceBufferEnabled}
                  onPress={() => updateSetting('priceBufferPercentage', preset)}
                >
                  <Text style={[
                    styles.presetText,
                    settings.priceBufferPercentage === preset && styles.presetTextActive,
                  ]}>
                    {preset}%
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.hint}>
              Orders target {Math.max(0, 100 - settings.priceBufferPercentage)}% of the alert price.
            </Text>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Broker And Order Routing</Text>
          <View style={styles.brokerGrid}>
            {BROKERS.map((broker) => (
              <TouchableOpacity
                key={broker.id}
                style={[
                  styles.brokerButton,
                  settings.activeBroker === broker.id && { borderColor: broker.color, backgroundColor: broker.color + '16' },
                ]}
                onPress={() => updateSetting('activeBroker', broker.id)}
              >
                <View style={[styles.brokerDot, { backgroundColor: broker.color }]} />
                <Text style={styles.brokerLabel}>{broker.label}</Text>
                <Text style={styles.brokerDetail}>{broker.detail}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Field
            label="Gateway URL"
            value={settings.brokerGatewayUrl}
            onChangeText={(value) => updateSetting('brokerGatewayUrl', value)}
            placeholder="https://localhost:5000"
          />
          <Field
            label="Account ID"
            value={settings.brokerAccountId}
            onChangeText={(value) => updateSetting('brokerAccountId', value)}
            placeholder="DU12345"
          />

          <Text style={styles.label}>Order Type</Text>
          <View style={styles.segmentRow}>
            {(['LIMIT', 'MARKET'] as OrderType[]).map((orderType) => (
              <TouchableOpacity
                key={orderType}
                style={[styles.segmentButton, settings.orderType === orderType && styles.segmentButtonActive]}
                onPress={() => updateSetting('orderType', orderType)}
              >
                <Text style={[styles.segmentText, settings.orderType === orderType && styles.segmentTextActive]}>
                  {orderType}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Order Timing</Text>
          <View style={styles.twoColumn}>
            <Field
              label="Timeout"
              value={String(settings.orderTimeout)}
              onChangeText={(value) => updateSetting('orderTimeout', Number(value))}
              keyboardType="numeric"
            />
            <Field
              label="Retry Interval"
              value={String(settings.retryInterval)}
              onChangeText={(value) => updateSetting('retryInterval', Number(value))}
              keyboardType="numeric"
            />
          </View>
          <ToggleRow
            title="Check For Fill"
            detail="Retry broker status checks after order submission."
            value={settings.retryFilledCheck}
            onValueChange={(value) => updateSetting('retryFilledCheck', value)}
          />
        </View>

        <View style={styles.actionRow}>
          <TouchableOpacity style={styles.secondaryAction} onPress={() => setSettings(DEFAULT_TRADING_SETTINGS)}>
            <Ionicons name="refresh-outline" size={18} color="#fb7185" />
            <Text style={styles.secondaryActionText}>Reset</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.primaryAction} onPress={saveSettings}>
            <Ionicons name="save-outline" size={18} color="transparent" />
            <Text style={styles.primaryActionText}>Save Settings</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export default TradingSettingsPage;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050416' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 },
  eyebrow: { color: '#f43f5e', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { color: '#edf3ff', fontSize: 26, fontWeight: '900' },
  modeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  modeBadgeSim: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#164766' },
  modeBadgeLive: { backgroundColor: '#2a2109', borderColor: '#7c4a03' },
  modeBadgeText: { color: '#fb7185', fontSize: 11, fontWeight: '900' },
  modeBadgeTextLive: { color: '#fbbf24' },
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
  scoreBadge: { minWidth: 78, height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  scoreValue: { fontSize: 18, fontWeight: '900' },
  scoreLabel: { color: '#68779b', fontSize: 10, fontWeight: '800', marginTop: 1 },
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
  section: {
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#29213a',
    marginBottom: 12,
  },
  sectionTitle: { color: '#edf3ff', fontSize: 18, fontWeight: '900', marginBottom: 14 },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: 'rgba(41, 33, 58, 0.82)',
  },
  toggleCopy: { flex: 1 },
  field: { flex: 1, marginBottom: 14 },
  label: { color: '#aec0e5', fontSize: 13, fontWeight: '800', marginBottom: 6 },
  hint: { color: '#68779b', fontSize: 12, lineHeight: 16 },
  input: {
    minHeight: 46,
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    borderColor: '#29213a',
    borderRadius: 8,
    borderWidth: 1,
    color: '#edf3ff',
    fontSize: 15,
    fontWeight: '700',
    paddingHorizontal: 12,
  },
  disabledBlock: { opacity: 0.5 },
  inlineInputRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  inlineInput: { flex: 1 },
  inputSuffix: { color: '#68779b', fontSize: 14, fontWeight: '900' },
  presetRow: { flexDirection: 'row', gap: 8, marginTop: 10, marginBottom: 8 },
  presetButton: {
    flex: 1,
    alignItems: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#29213a',
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    paddingVertical: 9,
  },
  presetButtonActive: { borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.18)' },
  presetButtonDisabled: { opacity: 0.5 },
  presetText: { color: '#68779b', fontSize: 13, fontWeight: '800' },
  presetTextActive: { color: '#fb7185' },
  brokerGrid: { gap: 8, marginBottom: 14 },
  brokerButton: {
    minHeight: 58,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#29213a',
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    padding: 12,
  },
  brokerDot: { width: 8, height: 8, borderRadius: 999, marginBottom: 6 },
  brokerLabel: { color: '#edf3ff', fontSize: 14, fontWeight: '900' },
  brokerDetail: { color: '#68779b', fontSize: 11, fontWeight: '700', marginTop: 2 },
  segmentRow: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  segmentButton: {
    flex: 1,
    alignItems: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#29213a',
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    paddingVertical: 11,
  },
  segmentButtonActive: { borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.18)' },
  segmentText: { color: '#68779b', fontSize: 13, fontWeight: '900' },
  segmentTextActive: { color: '#fb7185' },
  twoColumn: { flexDirection: 'row', gap: 10 },
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
    flex: 1.4,
    minHeight: 48,
    borderRadius: 10,
    backgroundColor: '#f43f5e',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  primaryActionText: { color: 'transparent', fontSize: 14, fontWeight: '900' },
});
