import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { api } from '../utils/api';
import { BACKEND_URL, DEMO_MODE } from '../constants/config';
import { BROKER_COLORS, BROKER_NAMES_FULL as BROKER_NAMES } from '../constants/brokers';
import { SettingsDigest, summarizeSettings } from '../utils/settingsDigest';
import { buildPremiumBufferSettingsParams } from '../utils/settingsPayload';

// Default demo settings
const DEMO_SETTINGS: Settings = {
  discord_token: 'DEMO_TOKEN',
  discord_channel_ids: ['123456789'],
  active_broker: 'IBKR',
  auto_trading_enabled: true,
  default_quantity: 5,
  simulation_mode: true,
  max_position_size: 1000,
  averaging_down_enabled: true,
  averaging_down_threshold: 10,
  averaging_down_percentage: 50,
  averaging_down_max_buys: 3,
  take_profit_enabled: true,
  take_profit_percentage: 50,
  stop_loss_enabled: true,
  stop_loss_percentage: 30,
  bracket_order_enabled: true,
  stop_loss_order_type: 'market',
  trailing_stop_enabled: true,
  trailing_stop_type: 'percent',
  trailing_stop_percent: 25,
  trailing_stop_cents: 0.5,
  auto_shutdown_enabled: true,
  max_consecutive_losses: 3,
  max_daily_losses: 5,
  max_daily_loss_amount: 500,
  premium_buffer_enabled: true,
  premium_buffer_amount: 2,
  max_positions_per_ticker: 3,
  sms_enabled: false,
  sms_phone_number: '',
  twilio_account_sid: '',
  twilio_auth_token: '',
  twilio_from_number: '',
};

const DEMO_PATTERNS: AlertPatterns = {
  buy_patterns: ['BTO', 'BUY', 'LONG', 'CALL'],
  sell_patterns: ['STC', 'SELL', 'CLOSE', 'EXIT'],
  partial_sell_patterns: ['STC PARTIAL', 'TRIM', 'TAKE PROFIT'],
  average_down_patterns: ['AVG DOWN', 'ADD TO', 'AVERAGING'],
  stop_loss_patterns: ['STOP', 'STOP LOSS', 'GLD'],
  take_profit_patterns: ['TAKE PROFIT', 'TP', 'TARGET'],
  ignore_patterns: ['WATCH', 'WATCHLIST', 'PAPER'],
  case_sensitive: false,
};

// ── Types ─────────────────────────────────────────────────────────────────────
interface Settings {
  discord_token: string; discord_channel_ids: string[];
  active_broker: string; auto_trading_enabled: boolean;
  default_quantity: number; simulation_mode: boolean; max_position_size: number;
  averaging_down_enabled: boolean; averaging_down_threshold: number;
  averaging_down_percentage: number; averaging_down_max_buys: number;
  take_profit_enabled: boolean; take_profit_percentage: number;
  stop_loss_enabled: boolean; stop_loss_percentage: number;
  bracket_order_enabled: boolean; stop_loss_order_type: string;
  trailing_stop_enabled: boolean; trailing_stop_type: string;
  trailing_stop_percent: number; trailing_stop_cents: number;
  auto_shutdown_enabled: boolean; max_consecutive_losses: number;
  max_daily_losses: number; max_daily_loss_amount: number;
  premium_buffer_enabled: boolean; premium_buffer_amount: number;
  max_positions_per_ticker: number;
  sms_enabled: boolean; sms_phone_number: string;
  twilio_account_sid: string; twilio_auth_token: string; twilio_from_number: string;
}

interface AlertPatterns {
  buy_patterns: string[]; sell_patterns: string[];
  partial_sell_patterns: string[]; average_down_patterns: string[];
  stop_loss_patterns: string[]; take_profit_patterns: string[];
  ignore_patterns: string[]; case_sensitive: boolean;
}

// ── Reusable components ────────────────────────────────────────────────────────
function SectionCard({ children, accent = '#0ea5e9' }: { children: React.ReactNode; accent?: string }) {
  return <View style={[s.card, { borderLeftColor: accent, borderLeftWidth: 3 }]}>{children}</View>;
}

function SectionTitle({ icon, label, color, sub }: { icon: string; label: string; color: string; sub?: string }) {
  return (
    <View style={s.sectionTitle}>
      <View style={[s.sectionIcon, { backgroundColor: color + '22' }]}>
        <Ionicons name={icon as any} size={18} color={color} />
      </View>
      <View>
        <Text style={s.sectionTitleText}>{label}</Text>
        {sub && <Text style={s.sectionTitleSub}>{sub}</Text>}
      </View>
    </View>
  );
}

function FieldLabel({ label, hint }: { label: string; hint?: string }) {
  return (
    <View style={s.fieldLabelWrap}>
      <Text style={s.fieldLabel}>{label}</Text>
      {hint && <Text style={s.fieldHint}>{hint}</Text>}
    </View>
  );
}

function Input({ value, onChange, placeholder, secure, numeric, disabled }: {
  value: string; onChange: (v: string) => void; placeholder?: string;
  secure?: boolean; numeric?: boolean; disabled?: boolean;
}) {
  return (
    <TextInput
      style={[s.input, disabled && s.inputDisabled]}
      value={value} onChangeText={onChange}
      placeholder={placeholder} placeholderTextColor="#334155"
      secureTextEntry={secure} autoCorrect={false} autoCapitalize="none"
      keyboardType={numeric ? 'decimal-pad' : 'default'}
      editable={!disabled}
    />
  );
}

function SwitchRow({ label, sub, value, onChange, accent = '#0ea5e9' }: {
  label: string; sub?: string; value: boolean; onChange: (v: boolean) => void; accent?: string;
}) {
  return (
    <View style={s.switchRow}>
      <View style={s.switchLeft}>
        <Text style={s.switchLabel}>{label}</Text>
        {sub && <Text style={s.switchSub}>{sub}</Text>}
      </View>
      <TouchableOpacity 
        style={[
          s.customSwitch, 
          { backgroundColor: value ? accent : '#1e2d3d' }
        ]} 
        onPress={() => onChange(!value)}
        activeOpacity={0.8}
      >
        <View style={[
          s.customSwitchThumb,
          { transform: [{ translateX: value ? 18 : 0 }] }
        ]} />
      </TouchableOpacity>
    </View>
  );
}

function QuickSelect({ values, current, onChange, suffix = '' }: {
  values: number[]; current: number; onChange: (v: number) => void; suffix?: string;
}) {
  return (
    <View style={s.quickRow}>
      {values.map(v => (
        <TouchableOpacity key={v} style={[s.quickBtn, current === v && s.quickBtnActive]} onPress={() => onChange(v)}>
          <Text style={[s.quickText, current === v && s.quickTextActive]}>{v}{suffix}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

function InfoBox({ text, color = '#0ea5e9' }: { text: string; color?: string }) {
  return (
    <View style={[s.infoBox, { borderLeftColor: color }]}>
      <Ionicons name="information-circle-outline" size={16} color={color} />
      <Text style={s.infoText}>{text}</Text>
    </View>
  );
}

// ── Main Screen ────────────────────────────────────────────────────────────────
function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={s.digestStat}>
      <Text style={[s.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={s.digestStatLabel}>{label}</Text>
    </View>
  );
}

function SettingsBriefing({ digest }: { digest: SettingsDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#64748b';
  const warnings = digest.warningItems.slice(0, 4);
  const hiddenWarningCount = Math.max(0, digest.warningItems.length - warnings.length);

  return (
    <View style={[s.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={s.digestTop}>
        <View style={s.digestTitleBlock}>
          <Text style={s.digestEyebrow}>CONFIG READINESS</Text>
          <Text style={s.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={s.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[s.readinessBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[s.readinessValue, { color: toneColor }]}>{digest.guardrailCoveragePercent}%</Text>
          <Text style={s.readinessLabel}>guarded</Text>
        </View>
      </View>

      <View style={s.digestStats}>
        <DigestStat label="Mode" value={digest.modeLabel} color={digest.modeLabel === 'Live auto' ? '#f59e0b' : undefined} />
        <DigestStat label="Discord" value={digest.channelLabel} />
        <DigestStat label="Parser" value={digest.parserLabel} />
        <DigestStat label="Guards" value={`${digest.guardrailCount}/6`} color={toneColor} />
      </View>

      <View style={s.digestMetaRow}>
        <Text style={s.digestMetaText}>Broker: {digest.brokerLabel}</Text>
        <Text style={s.digestMetaText}>Notify: {digest.notificationLabel}</Text>
      </View>

      <View style={s.warningList}>
        {warnings.length > 0 ? warnings.map((warning) => (
          <View key={warning.title} style={s.warningRow}>
            <Ionicons name="warning-outline" size={14} color="#f59e0b" />
            <View style={s.warningCopy}>
              <Text style={s.warningTitle}>{warning.title}</Text>
              <Text style={s.warningDetail}>{warning.detail}</Text>
            </View>
          </View>
        )) : (
          <View style={s.warningRow}>
            <Ionicons name="shield-checkmark-outline" size={14} color="#22c55e" />
            <Text style={s.clearText}>Discord, parser, and risk guardrails are aligned for simulated operation.</Text>
          </View>
        )}
        {hiddenWarningCount > 0 && (
          <Text style={s.hiddenWarningText}>+{hiddenWarningCount} more settings need review</Text>
        )}
      </View>
    </View>
  );
}

export default function SettingsScreen() {
  const router = useRouter();
  const [settings, setSettings]       = useState<Settings | null>(null);
  const [patterns, setPatterns]       = useState<AlertPatterns | null>(null);
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [dirty, setDirty]             = useState(false);
  const [channelInput, setChannelInput] = useState('');

  // Discord state
  const [discordStarting, setDiscordStarting] = useState(false);
  const [discordTesting, setDiscordTesting]   = useState(false);
  const [discordResult, setDiscordResult]     = useState<any>(null);
  const [showGuide, setShowGuide]             = useState(false);

  // Broker state
  const [brokerChecking, setBrokerChecking] = useState(false);

  // Alert patterns state
  const [showPatterns, setShowPatterns]       = useState(false);
  const [patternType, setPatternType]         = useState('buy_patterns');
  const [newPattern, setNewPattern]           = useState('');
  const [addingPattern, setAddingPattern]     = useState(false);
  const [testingSms, setTestingSms]           = useState(false);
  const [smsTestResult, setSmsTestResult]     = useState<{ok: boolean; msg: string} | null>(null);

  const originalSettings = useRef<Settings | null>(null);

  const fetchAll = useCallback(async () => {
    if (DEMO_MODE) {
      // Use demo data
      setSettings(DEMO_SETTINGS);
      setPatterns(DEMO_PATTERNS);
      setChannelInput(DEMO_SETTINGS.discord_channel_ids.join(', '));
      originalSettings.current = DEMO_SETTINGS;
      setDirty(false);
      setLoading(false);
      return;
    }
    try {
      const [sRes, pRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/settings`),
        api.get(`${BACKEND_URL}/api/discord/alert-patterns`),
      ]);
      // Merge auto-shutdown and premium-buffer into settings
      const [shutRes, bufRes, riskRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/auto-shutdown-settings`),
        api.get(`${BACKEND_URL}/api/premium-buffer-settings`),
        api.get(`${BACKEND_URL}/api/risk-management-settings`),
      ]);
      const [notifRes, corrRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/notification-settings`),
        api.get(`${BACKEND_URL}/api/correlation-settings`),
      ]);
      const merged: Settings = {
        ...sRes.data,
        auto_shutdown_enabled:  shutRes.data.auto_shutdown_enabled,
        max_consecutive_losses: shutRes.data.max_consecutive_losses,
        max_daily_losses:       shutRes.data.max_daily_losses,
        max_daily_loss_amount:  shutRes.data.max_daily_loss_amount,
        premium_buffer_enabled: bufRes.data.premium_buffer_enabled,
        premium_buffer_amount:  bufRes.data.premium_buffer_amount,
        bracket_order_enabled:  riskRes.data.bracket_order_enabled,
        stop_loss_order_type:   riskRes.data.stop_loss_order_type || 'market',
        max_positions_per_ticker: corrRes.data.max_positions_per_ticker ?? 3,
        sms_enabled:          notifRes.data.sms_enabled,
        sms_phone_number:     notifRes.data.sms_phone_number || '',
        twilio_account_sid:   notifRes.data.twilio_account_sid || '',
        twilio_auth_token:    notifRes.data.twilio_auth_token || '',
        twilio_from_number:   notifRes.data.twilio_from_number || '',
      };
      setSettings(merged);
      originalSettings.current = merged;
      setChannelInput(sRes.data.discord_channel_ids?.join(', ') || '');
      setPatterns(pRes.data);
      setDirty(false);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const update = (key: keyof Settings, value: any) => {
    setSettings(prev => prev ? { ...prev, [key]: value } : prev);
    setDirty(true);
  };

  const saveSettings = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const channelIds = channelInput.split(',').map(s => s.trim()).filter(Boolean);

      // Main settings
      await api.put(`${BACKEND_URL}/api/settings`, {
        discord_token: settings.discord_token,
        discord_channel_ids: channelIds,
        active_broker: settings.active_broker,
        auto_trading_enabled: settings.auto_trading_enabled,
        default_quantity: settings.default_quantity,
        simulation_mode: settings.simulation_mode,
        max_position_size: settings.max_position_size,
        averaging_down_enabled: settings.averaging_down_enabled,
        averaging_down_threshold: settings.averaging_down_threshold,
        averaging_down_percentage: settings.averaging_down_percentage,
        averaging_down_max_buys: settings.averaging_down_max_buys,
        take_profit_enabled: settings.take_profit_enabled,
        take_profit_percentage: settings.take_profit_percentage,
        stop_loss_enabled: settings.stop_loss_enabled,
        stop_loss_percentage: settings.stop_loss_percentage,
        trailing_stop_enabled: settings.trailing_stop_enabled,
        trailing_stop_type: settings.trailing_stop_type,
        trailing_stop_percent: settings.trailing_stop_percent,
        trailing_stop_cents: settings.trailing_stop_cents,
      });

      // Auto-shutdown settings (separate endpoint)
      await api.put(`${BACKEND_URL}/api/auto-shutdown-settings`, {
        auto_shutdown_enabled:  settings.auto_shutdown_enabled,
        max_consecutive_losses: settings.max_consecutive_losses,
        max_daily_losses:       settings.max_daily_losses,
        max_daily_loss_amount:  settings.max_daily_loss_amount,
      });

      // Premium buffer (separate endpoint)
      await api.put(`${BACKEND_URL}/api/premium-buffer-settings`, null, {
        params: buildPremiumBufferSettingsParams(settings),
      });

      // Risk management extras
      await api.put(`${BACKEND_URL}/api/risk-management-settings`, {
        bracket_order_enabled: settings.bracket_order_enabled,
        stop_loss_order_type:  settings.stop_loss_order_type,
      });

      // Notification (SMS) settings
      await api.put(
        `${BACKEND_URL}/api/notification-settings?` +
        `sms_enabled=${settings.sms_enabled}` +
        `&sms_phone_number=${encodeURIComponent(settings.sms_phone_number)}` +
        `&twilio_account_sid=${encodeURIComponent(settings.twilio_account_sid)}` +
        (settings.twilio_auth_token && !settings.twilio_auth_token.startsWith('●')
          ? `&twilio_auth_token=${encodeURIComponent(settings.twilio_auth_token)}`
          : '') +
        `&twilio_from_number=${encodeURIComponent(settings.twilio_from_number)}`
      );

      // Correlation limit
      await api.put(
        `${BACKEND_URL}/api/correlation-settings?max_positions_per_ticker=${settings.max_positions_per_ticker}`
      );

      setDirty(false);
      originalSettings.current = { ...settings, discord_channel_ids: channelIds };
      Alert.alert('Saved', 'All settings saved successfully.');
    } catch { Alert.alert('Error', 'Failed to save settings.'); }
    finally { setSaving(false); }
  };

  const discardChanges = () => {
    if (originalSettings.current) {
      setSettings({ ...originalSettings.current });
      setChannelInput(originalSettings.current.discord_channel_ids?.join(', ') || '');
      setDirty(false);
    }
  };

  const startDiscord = async () => {
    setDiscordStarting(true);
    try {
      const r = await api.post(`${BACKEND_URL}/api/discord/start`);
      Alert.alert('Discord', r.data.message);
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || 'Failed to start Discord bot'); }
    finally { setDiscordStarting(false); }
  };

  const testDiscord = async () => {
    setDiscordTesting(true); setDiscordResult(null);
    try {
      const r = await api.post(`${BACKEND_URL}/api/discord/test-connection`);
      setDiscordResult(r.data);
    } catch (e: any) {
      setDiscordResult({ success: false, message: e.response?.data?.detail || 'Connection failed', details: null });
    } finally { setDiscordTesting(false); }
  };

  const checkBroker = async () => {
    if (!settings) return;
    setBrokerChecking(true);
    try {
      const r = await api.post(`${BACKEND_URL}/api/broker/check/${settings.active_broker}`);
      Alert.alert(r.data.connected ? '✓ Connected' : 'Not Connected', r.data.message);
    } catch { Alert.alert('Error', 'Failed to check broker connection.'); }
    finally { setBrokerChecking(false); }
  };

  const addPattern = async () => {
    if (!newPattern.trim() || addingPattern) return;
    setAddingPattern(true);
    try {
      const r = await api.post(`${BACKEND_URL}/api/discord/alert-patterns/${patternType}/add?pattern=${encodeURIComponent(newPattern.trim().toUpperCase())}`);
      setPatterns(prev => prev ? { ...prev, [patternType]: r.data[patternType] } : null);
      setNewPattern('');
    } catch { Alert.alert('Error', 'Failed to add pattern.'); }
    finally { setAddingPattern(false); }
  };

  const removePattern = async (type: string, pattern: string) => {
    try {
      const r = await api.post(`${BACKEND_URL}/api/discord/alert-patterns/${type}/remove?pattern=${encodeURIComponent(pattern)}`);
      setPatterns(prev => prev ? { ...prev, [type]: r.data[type] } : null);
    } catch { Alert.alert('Error', 'Failed to remove pattern.'); }
  };

  const resetPatterns = () => Alert.alert('Reset Patterns', 'Reset all alert patterns to defaults?', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Reset', style: 'destructive', onPress: async () => {
      try { const r = await api.post(`${BACKEND_URL}/api/discord/alert-patterns/reset`); setPatterns(r.data); }
      catch { Alert.alert('Error', 'Failed to reset.'); }
    }}
  ]);

  const testSms = async () => {
    setTestingSms(true);
    setSmsTestResult(null);
    try {
      await api.post(`${BACKEND_URL}/api/notification-settings/test`);
      setSmsTestResult({ ok: true, msg: 'Test SMS sent! Check your phone.' });
    } catch (e: any) {
      setSmsTestResult({ ok: false, msg: e.response?.data?.detail || 'Send failed — check credentials.' });
    } finally {
      setTestingSms(false);
    }
  };

  const PATTERN_TYPES = [
    { key: 'buy_patterns',          label: 'Buy',          color: '#22c55e', icon: 'arrow-up'      },
    { key: 'sell_patterns',         label: 'Sell',         color: '#ef4444', icon: 'arrow-down'    },
    { key: 'partial_sell_patterns', label: 'Partial',      color: '#f59e0b', icon: 'remove'        },
    { key: 'average_down_patterns', label: 'Avg Down',     color: '#a78bfa', icon: 'trending-down' },
    { key: 'ignore_patterns',       label: 'Ignore',       color: '#64748b', icon: 'close-circle'  },
  ] as const;

  if (loading) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.centered}><ActivityIndicator size="large" color="#0ea5e9" /></View>
      </SafeAreaView>
    );
  }

  const bColor = BROKER_COLORS[settings?.active_broker || ''] || '#0ea5e9';
  const bName  = BROKER_NAMES[settings?.active_broker || ''] || 'None';
  const channelIdsForDigest = channelInput.split(',').map(channel => channel.trim()).filter(Boolean);
  const settingsDigest = settings
    ? summarizeSettings({ ...settings, discord_channel_ids: channelIdsForDigest }, patterns)
    : null;

  return (
    <SafeAreaView style={s.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>

        {/* ── Header ── */}
        <View style={s.header}>
          <View>
            <Text style={s.headerEyebrow}>CONFIGURATION</Text>
            <Text style={s.headerTitle}>Settings</Text>
          </View>
          <View style={s.headerBtns}>
            {dirty && (
              <TouchableOpacity style={s.discardBtn} onPress={discardChanges}>
                <Text style={s.discardText}>Discard</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={[s.saveBtn, !dirty && s.saveBtnDim]}
              onPress={saveSettings} disabled={saving || !dirty}
            >
              {saving
                ? <ActivityIndicator size="small" color="#fff" />
                : <Text style={s.saveBtnText}>{dirty ? '● Save' : 'Saved'}</Text>
              }
            </TouchableOpacity>
          </View>
        </View>

        {/* ── Sim mode banner ── */}
        {settings?.simulation_mode && (
          <View style={s.simBanner}>
            <Ionicons name="flask" size={16} color="#a78bfa" />
            <Text style={s.simBannerText}>SIMULATION MODE ACTIVE — No real trades will execute</Text>
          </View>
        )}

        {/* ── Unsaved changes bar ── */}
        {dirty && (
          <View style={s.dirtyBar}>
            <Ionicons name="ellipse" size={8} color="#f59e0b" />
            <Text style={s.dirtyText}>You have unsaved changes</Text>
          </View>
        )}

        <ScrollView style={s.scroll} showsVerticalScrollIndicator={false}>
          {settingsDigest && <SettingsBriefing digest={settingsDigest} />}

          {/* ═══ DISCORD ═══ */}
          <SectionCard accent="#5865F2">
            <SectionTitle icon="logo-discord" label="Discord" color="#5865F2" sub="Bot token & channels" />

            <FieldLabel label="Bot Token" hint="Never share this — it controls your bot" />
            <Input
              value={settings?.discord_token || ''}
              onChange={v => update('discord_token', v)}
              placeholder={settings?.discord_token ? '••••••••• (saved)' : 'Paste your bot token'}
              secure
            />

            <FieldLabel
              label="Channel IDs"
              hint="Comma-separated — right-click channel in Discord → Copy ID (requires Developer Mode)"
            />
            <Input
              value={channelInput}
              onChange={v => { setChannelInput(v); setDirty(true); }}
              placeholder="123456789012345678, 987654321..."
            />
            {channelInput.split(',').filter(s => s.trim()).some(id => !/^\d{17,19}$/.test(id.trim())) && channelInput.trim() !== '' && (
              <Text style={s.validationWarn}>⚠ Channel IDs should be 17–19 digit numbers</Text>
            )}

            <View style={s.btnRow}>
              <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#5865F2', flex: 1 }]} onPress={startDiscord} disabled={discordStarting}>
                {discordStarting ? <ActivityIndicator size="small" color="#fff" /> : (
                  <><Ionicons name="play" size={16} color="#fff" /><Text style={s.actionBtnText}>Start Bot</Text></>
                )}
              </TouchableOpacity>
              <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#1e2d3d', flex: 1, borderWidth: 1, borderColor: '#5865F2' }]} onPress={testDiscord} disabled={discordTesting}>
                {discordTesting ? <ActivityIndicator size="small" color="#5865F2" /> : (
                  <><Ionicons name="pulse" size={16} color="#5865F2" /><Text style={[s.actionBtnText, { color: '#5865F2' }]}>Test</Text></>
                )}
              </TouchableOpacity>
            </View>

            {discordResult && (
              <View style={[s.resultBox, discordResult.success ? s.resultSuccess : s.resultError]}>
                <View style={s.resultHeader}>
                  <Ionicons name={discordResult.success ? 'checkmark-circle' : 'alert-circle'} size={20} color={discordResult.success ? '#4ade80' : '#f87171'} />
                  <Text style={[s.resultTitle, { color: discordResult.success ? '#4ade80' : '#f87171' }]}>
                    {discordResult.success ? 'Connected' : 'Not Connected'}
                  </Text>
                </View>
                <Text style={s.resultMsg}>{discordResult.message}</Text>
                {discordResult.details?.monitoring_channels && (
                  <Text style={s.resultDetail}>Channels: {discordResult.details.monitoring_channels.join(', ')}</Text>
                )}
                {discordResult.details?.alerts_processed !== undefined && (
                  <Text style={s.resultDetail}>Alerts processed: {discordResult.details.alerts_processed}</Text>
                )}
              </View>
            )}

            <TouchableOpacity style={s.guideToggle} onPress={() => setShowGuide(!showGuide)}>
              <View style={s.guideToggleLeft}>
                <Ionicons name="help-circle-outline" size={16} color="#5865F2" />
                <Text style={s.guideToggleText}>How to create your Discord bot</Text>
              </View>
              <Ionicons name={showGuide ? 'chevron-up' : 'chevron-down'} size={16} color="#475569" />
            </TouchableOpacity>

            {showGuide && (
              <View style={s.guide}>
                {[
                  { n: 1, title: 'Create application', steps: ['Go to discord.com/developers/applications', 'Click "New Application" → name it → Create'] },
                  { n: 2, title: 'Create the bot', steps: ['Click "Bot" in sidebar → Add Bot', 'Enable MESSAGE CONTENT INTENT and SERVER MEMBERS INTENT', 'Click Save Changes'] },
                  { n: 3, title: 'Copy your token', steps: ['On the Bot page, click Reset Token', 'Copy the token — paste it above', '⚠ Never share this token with anyone'] },
                  { n: 4, title: 'Invite bot to server', steps: ['OAuth2 → URL Generator → check "bot"', 'Permissions: Read Messages, Read Message History', 'Open generated URL → select server → Authorize'] },
                  { n: 5, title: 'Get channel IDs', steps: ['Discord → User Settings → Advanced → Developer Mode ON', 'Right-click any channel → Copy Channel ID', 'Paste the IDs above (comma-separated)'] },
                ].map(({ n, title, steps }) => (
                  <View key={n} style={s.guideStep}>
                    <View style={s.guideStepHeader}>
                      <View style={s.guideNum}><Text style={s.guideNumText}>{n}</Text></View>
                      <Text style={s.guideStepTitle}>{title}</Text>
                    </View>
                    {steps.map((step, i) => (
                      <Text key={i} style={s.guideStepText}>• {step}</Text>
                    ))}
                  </View>
                ))}
              </View>
            )}
          </SectionCard>

          {/* ═══ BROKER ═══ */}
          <SectionCard accent={bColor}>
            <SectionTitle icon="trending-up" label="Broker" color={bColor} sub={`Active: ${bName}`} />
            <View style={s.brokerRow}>
              <View style={[s.brokerDot, { backgroundColor: bColor }]} />
              <Text style={[s.brokerName, { color: bColor }]}>{bName}</Text>
              <TouchableOpacity style={s.brokerConfigBtn} onPress={() => router.push('/broker-config')}>
                <Text style={s.brokerConfigText}>Configure Keys →</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity style={[s.actionBtn, { backgroundColor: bColor + '22', borderWidth: 1, borderColor: bColor }]} onPress={checkBroker} disabled={brokerChecking}>
              {brokerChecking ? <ActivityIndicator size="small" color={bColor} /> : (
                <><Ionicons name="refresh" size={16} color={bColor} /><Text style={[s.actionBtnText, { color: bColor }]}>Check Connection</Text></>
              )}
            </TouchableOpacity>
          </SectionCard>

          {/* ═══ TRADING ═══ */}
          <SectionCard accent="#22c55e">
            <SectionTitle icon="settings-outline" label="Trading" color="#22c55e" sub="Core execution settings" />

            <SwitchRow label="Auto Trading" sub="Execute trades when Discord alerts arrive" value={settings?.auto_trading_enabled || false} onChange={v => update('auto_trading_enabled', v)} accent="#22c55e" />
            <SwitchRow label="Simulation Mode" sub="Paper trade — no real money executes" value={settings?.simulation_mode || false} onChange={v => update('simulation_mode', v)} accent="#a78bfa" />

            {settings?.simulation_mode && (
              <View style={s.simWarning}>
                <Ionicons name="flask" size={14} color="#a78bfa" />
                <Text style={s.simWarningText}>Simulation mode is ON. All trades will be paper trades only.</Text>
              </View>
            )}

            <View style={s.twoCol}>
              <View style={s.twoColItem}>
                <FieldLabel label="Default Quantity" hint="Contracts per trade" />
                <Input value={String(settings?.default_quantity || 1)} onChange={v => update('default_quantity', parseInt(v) || 1)} numeric />
              </View>
              <View style={s.twoColItem}>
                <FieldLabel label="Max Position Size ($)" hint="Dollar limit per trade" />
                <Input value={String(settings?.max_position_size || 1000)} onChange={v => update('max_position_size', parseFloat(v) || 1000)} numeric />
              </View>
            </View>

            {/* Premium Buffer */}
            <View style={s.divider} />
            <Text style={s.subSectionLabel}>PREMIUM BUFFER</Text>
            <SwitchRow label="Premium Buffer" sub="Skip trade if live price too far above alert price" value={settings?.premium_buffer_enabled || false} onChange={v => update('premium_buffer_enabled', v)} accent="#0ea5e9" />
            {settings?.premium_buffer_enabled && (
              <>
                <FieldLabel label="Max Difference (cents)" hint="Skip if live premium exceeds alert price by this many ¢" />
                <QuickSelect values={[5, 10, 15, 25, 50]} current={settings.premium_buffer_amount} onChange={v => update('premium_buffer_amount', v)} suffix="¢" />
                <Input value={String(settings.premium_buffer_amount)} onChange={v => update('premium_buffer_amount', parseFloat(v) || 10)} placeholder="Custom ¢" numeric />
              </>
            )}
          </SectionCard>

          {/* ═══ AVERAGING DOWN ═══ */}
          <SectionCard accent="#f59e0b">
            <SectionTitle icon="trending-down" label="Averaging Down" color="#f59e0b" sub="Buy more on price drops" />
            <SwitchRow label="Enable Averaging Down" sub="Add to losing positions to lower average cost" value={settings?.averaging_down_enabled || false} onChange={v => update('averaging_down_enabled', v)} accent="#f59e0b" />

            {settings?.averaging_down_enabled && (
              <>
                <FieldLabel label="Price Drop Threshold (%)" hint="Buy when price drops this % below entry" />
                <QuickSelect values={[5, 10, 15, 20, 25]} current={settings.averaging_down_threshold} onChange={v => update('averaging_down_threshold', v)} suffix="%" />
                <Input value={String(settings.averaging_down_threshold || 10)} onChange={v => update('averaging_down_threshold', parseFloat(v) || 10)} numeric />

                <FieldLabel label="Buy Size (% of original)" hint="How much to buy relative to original position" />
                <QuickSelect values={[10, 25, 50, 75, 100]} current={settings.averaging_down_percentage} onChange={v => update('averaging_down_percentage', v)} suffix="%" />
                <Input value={String(settings.averaging_down_percentage || 25)} onChange={v => update('averaging_down_percentage', parseFloat(v) || 25)} numeric />

                <FieldLabel label="Max Avg-Down Buys" hint="Maximum number of times to average down per position" />
                <QuickSelect values={[1, 2, 3, 4, 5]} current={settings.averaging_down_max_buys} onChange={v => update('averaging_down_max_buys', v)} />
                <Input value={String(settings.averaging_down_max_buys || 3)} onChange={v => update('averaging_down_max_buys', parseInt(v) || 3)} numeric />
              </>
            )}
            <InfoBox text='Discord alerts like "AVERAGE DOWN $SPY" or "AVG DOWN $QQQ" trigger this.' color="#f59e0b" />
          </SectionCard>

          {/* ═══ RISK MANAGEMENT ═══ */}
          <SectionCard accent="#3b82f6">
            <SectionTitle icon="shield-checkmark" label="Risk Management" color="#3b82f6" sub="Take profit, stop loss, bracket orders" />

            {/* Take Profit */}
            <Text style={s.subSectionLabel}>TAKE PROFIT</Text>
            <SwitchRow label="Take Profit" sub="Auto-sell when profit target is reached" value={settings?.take_profit_enabled || false} onChange={v => update('take_profit_enabled', v)} accent="#22c55e" />
            {settings?.take_profit_enabled && (
              <>
                <FieldLabel label="Take Profit %" hint="Sell when position gains this %" />
                <QuickSelect values={[25, 50, 75, 100, 150]} current={settings.take_profit_percentage} onChange={v => update('take_profit_percentage', v)} suffix="%" />
                <Input value={String(settings.take_profit_percentage || 50)} onChange={v => update('take_profit_percentage', parseFloat(v) || 50)} numeric />

                <SwitchRow label="Bracket Order" sub="Submit TP + SL as a single bracket order" value={settings?.bracket_order_enabled || false} onChange={v => update('bracket_order_enabled', v)} accent="#3b82f6" />
              </>
            )}

            <View style={s.divider} />

            {/* Stop Loss */}
            <Text style={s.subSectionLabel}>STOP LOSS</Text>
            <SwitchRow label="Stop Loss" sub="Auto-sell to limit losses" value={settings?.stop_loss_enabled || false} onChange={v => update('stop_loss_enabled', v)} accent="#ef4444" />
            {settings?.stop_loss_enabled && (
              <>
                <FieldLabel label="Stop Loss %" hint="Sell when position loses this %" />
                <QuickSelect values={[10, 25, 50, 75, 90]} current={settings.stop_loss_percentage} onChange={v => update('stop_loss_percentage', v)} suffix="%" />
                <Input value={String(settings.stop_loss_percentage || 25)} onChange={v => update('stop_loss_percentage', parseFloat(v) || 25)} numeric />

                <FieldLabel label="Stop Loss Order Type" />
                <View style={s.segmentRow}>
                  {['market', 'limit', 'stop'].map(type => (
                    <TouchableOpacity
                      key={type}
                      style={[s.segBtn, settings.stop_loss_order_type === type && s.segBtnActive]}
                      onPress={() => update('stop_loss_order_type', type)}
                    >
                      <Text style={[s.segText, settings.stop_loss_order_type === type && s.segTextActive]}>
                        {type.charAt(0).toUpperCase() + type.slice(1)}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </>
            )}

            <InfoBox text="These settings override Discord sell commands — the position closes automatically when thresholds are hit." color="#3b82f6" />
          </SectionCard>

          {/* ═══ TRAILING STOP ═══ */}
          <SectionCard accent="#a78bfa">
            <SectionTitle icon="git-branch" label="Trailing Stop" color="#a78bfa" sub="Follow price up, sell on pullback" />
            <SwitchRow label="Enable Trailing Stop" sub="Sell when price pulls back from its highest point" value={settings?.trailing_stop_enabled || false} onChange={v => update('trailing_stop_enabled', v)} accent="#a78bfa" />

            {settings?.trailing_stop_enabled && (
              <>
                <FieldLabel label="Trail By" />
                <View style={s.segmentRow}>
                  {[{ v: 'percent', label: '% Percent' }, { v: 'premium', label: '¢ Premium' }].map(({ v, label }) => (
                    <TouchableOpacity key={v} style={[s.segBtn, settings.trailing_stop_type === v && s.segBtnActive]} onPress={() => update('trailing_stop_type', v)}>
                      <Text style={[s.segText, settings.trailing_stop_type === v && s.segTextActive]}>{label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {settings.trailing_stop_type === 'percent' ? (
                  <>
                    <FieldLabel label="Trail Percent (%)" hint="Sell when price drops this % below its highest" />
                    <QuickSelect values={[5, 10, 15, 20, 25]} current={settings.trailing_stop_percent} onChange={v => update('trailing_stop_percent', v)} suffix="%" />
                    <Input value={String(settings.trailing_stop_percent || 10)} onChange={v => update('trailing_stop_percent', parseFloat(v) || 10)} numeric />
                  </>
                ) : (
                  <>
                    <FieldLabel label="Trail Cents (¢)" hint="Sell when price drops this many cents below its highest" />
                    <QuickSelect values={[10, 25, 50, 75, 100]} current={settings.trailing_stop_cents} onChange={v => update('trailing_stop_cents', v)} suffix="¢" />
                    <Input value={String(settings.trailing_stop_cents || 50)} onChange={v => update('trailing_stop_cents', parseFloat(v) || 50)} numeric />
                  </>
                )}
              </>
            )}
            <InfoBox text="Trailing stop locks in profits by following the price up, then triggering a sell when it falls back." color="#a78bfa" />
          </SectionCard>

          {/* ═══ AUTO SHUTDOWN ═══ */}
          <SectionCard accent="#f87171">
            <SectionTitle icon="power" label="Auto Shutdown" color="#f87171" sub="Stop trading on loss limits" />
            <SwitchRow label="Enable Auto Shutdown" sub="Automatically pause trading when loss limits are hit" value={settings?.auto_shutdown_enabled || false} onChange={v => update('auto_shutdown_enabled', v)} accent="#f87171" />

            {settings?.auto_shutdown_enabled && (
              <>
                {/* Consecutive Losses */}
                <View style={s.thresholdBlock}>
                  <View style={s.thresholdHeader}>
                    <View>
                      <Text style={s.thresholdLabel}>Max Consecutive Losses</Text>
                      <Text style={s.thresholdHint}>Stop after this many losses in a row</Text>
                    </View>
                    <View style={s.stepperWrap}>
                      <TouchableOpacity
                        style={s.stepperBtn}
                        onPress={() => update('max_consecutive_losses', Math.max(1, (settings.max_consecutive_losses || 3) - 1))}
                      >
                        <Ionicons name="remove" size={16} color="#f87171" />
                      </TouchableOpacity>
                      <TextInput
                        style={s.stepperInput}
                        value={String(settings.max_consecutive_losses || 3)}
                        onChangeText={v => { const n = parseInt(v); if (!isNaN(n) && n >= 1) update('max_consecutive_losses', n); else if (v === '') update('max_consecutive_losses', 1); }}
                        keyboardType="number-pad"
                        selectTextOnFocus
                      />
                      <TouchableOpacity
                        style={s.stepperBtn}
                        onPress={() => update('max_consecutive_losses', (settings.max_consecutive_losses || 3) + 1)}
                      >
                        <Ionicons name="add" size={16} color="#f87171" />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={s.thresholdPresets}>
                    {[2, 3, 4, 5, 6, 8, 10].map(v => (
                      <TouchableOpacity key={v} style={[s.preset, settings.max_consecutive_losses === v && s.presetActive]} onPress={() => update('max_consecutive_losses', v)}>
                        <Text style={[s.presetText, settings.max_consecutive_losses === v && s.presetTextActive]}>{v}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>

                {/* Daily Losses */}
                <View style={s.thresholdBlock}>
                  <View style={s.thresholdHeader}>
                    <View>
                      <Text style={s.thresholdLabel}>Max Daily Losses</Text>
                      <Text style={s.thresholdHint}>Stop after this many losses today</Text>
                    </View>
                    <View style={s.stepperWrap}>
                      <TouchableOpacity
                        style={s.stepperBtn}
                        onPress={() => update('max_daily_losses', Math.max(1, (settings.max_daily_losses || 5) - 1))}
                      >
                        <Ionicons name="remove" size={16} color="#f87171" />
                      </TouchableOpacity>
                      <TextInput
                        style={s.stepperInput}
                        value={String(settings.max_daily_losses || 5)}
                        onChangeText={v => { const n = parseInt(v); if (!isNaN(n) && n >= 1) update('max_daily_losses', n); else if (v === '') update('max_daily_losses', 1); }}
                        keyboardType="number-pad"
                        selectTextOnFocus
                      />
                      <TouchableOpacity
                        style={s.stepperBtn}
                        onPress={() => update('max_daily_losses', (settings.max_daily_losses || 5) + 1)}
                      >
                        <Ionicons name="add" size={16} color="#f87171" />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={s.thresholdPresets}>
                    {[3, 5, 7, 10, 15, 20].map(v => (
                      <TouchableOpacity key={v} style={[s.preset, settings.max_daily_losses === v && s.presetActive]} onPress={() => update('max_daily_losses', v)}>
                        <Text style={[s.presetText, settings.max_daily_losses === v && s.presetTextActive]}>{v}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>

                {/* Daily Loss Amount */}
                <View style={s.thresholdBlock}>
                  <View style={s.thresholdHeader}>
                    <View>
                      <Text style={s.thresholdLabel}>Max Daily Loss Amount</Text>
                      <Text style={s.thresholdHint}>Stop if total losses today exceed this $</Text>
                    </View>
                    <View style={s.stepperWrap}>
                      <TouchableOpacity
                        style={s.stepperBtn}
                        onPress={() => update('max_daily_loss_amount', Math.max(10, (settings.max_daily_loss_amount || 500) - 50))}
                      >
                        <Ionicons name="remove" size={16} color="#f87171" />
                      </TouchableOpacity>
                      <View style={s.stepperInputWrap}>
                        <Text style={s.stepperDollar}>$</Text>
                        <TextInput
                          style={[s.stepperInput, { paddingLeft: 2 }]}
                          value={String(settings.max_daily_loss_amount || 500)}
                          onChangeText={v => { const n = parseFloat(v); if (!isNaN(n) && n >= 1) update('max_daily_loss_amount', n); else if (v === '') update('max_daily_loss_amount', 0); }}
                          keyboardType="decimal-pad"
                          selectTextOnFocus
                        />
                      </View>
                      <TouchableOpacity
                        style={s.stepperBtn}
                        onPress={() => update('max_daily_loss_amount', (settings.max_daily_loss_amount || 500) + 50)}
                      >
                        <Ionicons name="add" size={16} color="#f87171" />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={s.thresholdPresets}>
                    {[100, 250, 500, 1000, 2000, 5000].map(v => (
                      <TouchableOpacity key={v} style={[s.preset, settings.max_daily_loss_amount === v && s.presetActive]} onPress={() => update('max_daily_loss_amount', v)}>
                        <Text style={[s.presetText, settings.max_daily_loss_amount === v && s.presetTextActive]}>${v >= 1000 ? `${v/1000}k` : v}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </>
            )}
            <InfoBox text="Auto-shutdown pauses all trading when triggered. Use the Reset button on the dashboard to re-enable after reviewing." color="#f87171" />
          </SectionCard>

          {/* ═══ ALERT PATTERNS ═══ */}
          <SectionCard accent="#0ea5e9">
            <TouchableOpacity style={s.patternsHeader} onPress={() => setShowPatterns(!showPatterns)}>
              <SectionTitle icon="code-working" label="Alert Patterns" color="#0ea5e9" sub="Customize Discord keywords" />
              <Ionicons name={showPatterns ? 'chevron-up' : 'chevron-down'} size={18} color="#475569" />
            </TouchableOpacity>

            {showPatterns && patterns && (
              <View style={s.patternsBody}>
                {/* Type selector */}
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
                  <View style={s.patternTypesRow}>
                    {PATTERN_TYPES.map(pt => (
                      <TouchableOpacity
                        key={pt.key}
                        style={[s.patternTypeBtn, patternType === pt.key && { backgroundColor: pt.color }]}
                        onPress={() => setPatternType(pt.key)}
                      >
                        <Ionicons name={pt.icon as any} size={13} color={patternType === pt.key ? '#fff' : pt.color} />
                        <Text style={[s.patternTypeBtnText, patternType === pt.key && { color: '#fff' }]}>{pt.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </ScrollView>

                {/* Current patterns */}
                <View style={s.patternChips}>
                  {(patterns[patternType as keyof AlertPatterns] as string[] || []).map((p, i) => {
                    const pt = PATTERN_TYPES.find(t => t.key === patternType);
                    return (
                      <View key={i} style={[s.chip, { borderColor: pt?.color || '#334155' }]}>
                        <Text style={s.chipText}>{p}</Text>
                        <TouchableOpacity onPress={() => removePattern(patternType, p)}>
                          <Ionicons name="close" size={13} color="#64748b" />
                        </TouchableOpacity>
                      </View>
                    );
                  })}
                  {(patterns[patternType as keyof AlertPatterns] as string[])?.length === 0 && (
                    <Text style={s.noPatterns}>No patterns — add one below</Text>
                  )}
                </View>

                {/* Add new */}
                <View style={s.addPatternRow}>
                  <TextInput
                    style={[s.input, { flex: 1 }]}
                    value={newPattern} onChangeText={setNewPattern}
                    placeholder="New keyword..." placeholderTextColor="#334155"
                    autoCapitalize="characters"
                  />
                  <TouchableOpacity style={s.addPatternBtn} onPress={addPattern} disabled={addingPattern}>
                    {addingPattern ? <ActivityIndicator size="small" color="#0ea5e9" /> : <Ionicons name="add" size={20} color="#0ea5e9" />}
                  </TouchableOpacity>
                </View>

                <TouchableOpacity style={s.resetPatternsBtn} onPress={resetPatterns}>
                  <Ionicons name="refresh" size={15} color="#f87171" />
                  <Text style={s.resetPatternsBtnText}>Reset All to Defaults</Text>
                </TouchableOpacity>
              </View>
            )}
          </SectionCard>

          {/* ═══ NOTIFICATIONS (SMS) ═══ */}
          <SectionCard accent="#10b981">
            <SectionTitle icon="notifications" label="Notifications" color="#10b981" sub="SMS alerts via Twilio" />

            <SwitchRow
              label="SMS Alerts"
              sub="Receive texts for fills, failures, shutdowns & disconnects"
              value={settings?.sms_enabled || false}
              onChange={v => update('sms_enabled', v)}
              accent="#10b981"
            />

            {settings?.sms_enabled && (
              <>
                <FieldLabel label="Your Phone Number" hint="Format: +15551234567 (include country code)" />
                <Input
                  value={settings.sms_phone_number}
                  onChange={v => update('sms_phone_number', v)}
                  placeholder="+15551234567"
                />

                <View style={s.divider} />
                <Text style={s.subSectionLabel}>TWILIO CREDENTIALS</Text>
                <InfoBox
                  text="Sign up free at twilio.com → get Account SID, Auth Token, and a phone number. Free trial includes ~$15 credit."
                  color="#10b981"
                />

                <FieldLabel label="Account SID" hint="From your Twilio console dashboard" />
                <Input
                  value={settings.twilio_account_sid}
                  onChange={v => update('twilio_account_sid', v)}
                  placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                />

                <FieldLabel label="Auth Token" hint="Keep this secret — never share it" />
                <Input
                  value={settings.twilio_auth_token}
                  onChange={v => update('twilio_auth_token', v)}
                  placeholder={settings.twilio_auth_token?.startsWith('●') ? '●●●●●●●● (saved)' : 'Paste auth token'}
                  secure
                />

                <FieldLabel label="Twilio From Number" hint="The number Twilio assigned to you" />
                <Input
                  value={settings.twilio_from_number}
                  onChange={v => update('twilio_from_number', v)}
                  placeholder="+15550000000"
                />

                <View style={s.divider} />
                <Text style={s.subSectionLabel}>SMS EVENTS</Text>
                <View style={s.smsEventGrid}>
                  {[
                    { icon: 'checkmark-circle', color: '#22c55e', label: 'Trade filled' },
                    { icon: 'close-circle',     color: '#f87171', label: 'Trade failed / rejected' },
                    { icon: 'power',            color: '#f87171', label: 'Auto-shutdown triggered' },
                    { icon: 'logo-discord',     color: '#5865F2', label: 'Discord disconnected' },
                    { icon: 'layers',           color: '#f59e0b', label: 'Correlation limit blocked' },
                  ].map(({ icon, color, label }) => (
                    <View key={label} style={s.smsEventRow}>
                      <Ionicons name={icon as any} size={14} color={color} />
                      <Text style={s.smsEventLabel}>{label}</Text>
                    </View>
                  ))}
                </View>

                <TouchableOpacity
                  style={[s.actionBtn, { backgroundColor: '#064e3b', borderWidth: 1, borderColor: '#10b981', marginTop: 12 }]}
                  onPress={testSms}
                  disabled={testingSms}
                >
                  {testingSms
                    ? <ActivityIndicator size="small" color="#10b981" />
                    : <><Ionicons name="send" size={15} color="#10b981" /><Text style={[s.actionBtnText, { color: '#10b981' }]}>Send Test SMS</Text></>
                  }
                </TouchableOpacity>

                {smsTestResult && (
                  <View style={[s.resultBox, smsTestResult.ok ? s.resultSuccess : s.resultError, { flexDirection: 'row', alignItems: 'center', gap: 8 }]}>
                    <Ionicons name={smsTestResult.ok ? 'checkmark-circle' : 'alert-circle'} size={18} color={smsTestResult.ok ? '#4ade80' : '#f87171'} />
                    <Text style={[s.resultMsg, { flex: 1, marginBottom: 0 }]}>{smsTestResult.msg}</Text>
                  </View>
                )}
              </>
            )}
          </SectionCard>

          {/* ═══ CORRELATION / CONCENTRATION ═══ */}
          <SectionCard accent="#f59e0b">
            <SectionTitle icon="layers" label="Position Concentration" color="#f59e0b" sub="Limit exposure per underlying" />

            <View style={s.thresholdBlock}>
              <View style={s.thresholdHeader}>
                <View style={{ flex: 1, paddingRight: 12 }}>
                  <Text style={s.thresholdLabel}>Max Positions Per Ticker</Text>
                  <Text style={s.thresholdHint}>
                    Block new entries when this many open positions exist in the same underlying (e.g. SPY). Set to 0 to disable.
                  </Text>
                </View>
                <View style={s.stepperWrap}>
                  <TouchableOpacity
                    style={s.stepperBtn}
                    onPress={() => update('max_positions_per_ticker', Math.max(0, (settings?.max_positions_per_ticker ?? 3) - 1))}
                  >
                    <Ionicons name="remove" size={16} color="#f59e0b" />
                  </TouchableOpacity>
                  <TextInput
                    style={s.stepperInput}
                    value={String(settings?.max_positions_per_ticker ?? 3)}
                    onChangeText={v => { const n = parseInt(v); update('max_positions_per_ticker', isNaN(n) ? 0 : Math.max(0, n)); }}
                    keyboardType="number-pad"
                    selectTextOnFocus
                  />
                  <TouchableOpacity
                    style={s.stepperBtn}
                    onPress={() => update('max_positions_per_ticker', (settings?.max_positions_per_ticker ?? 3) + 1)}
                  >
                    <Ionicons name="add" size={16} color="#f59e0b" />
                  </TouchableOpacity>
                </View>
              </View>
              <View style={s.thresholdPresets}>
                {[0, 1, 2, 3, 5, 10].map(v => (
                  <TouchableOpacity
                    key={v}
                    style={[s.preset, (settings?.max_positions_per_ticker ?? 3) === v && { backgroundColor: '#1c1200', borderWidth: 1, borderColor: '#f59e0b' }]}
                    onPress={() => update('max_positions_per_ticker', v)}
                  >
                    <Text style={[s.presetText, (settings?.max_positions_per_ticker ?? 3) === v && { color: '#f59e0b' }]}>
                      {v === 0 ? 'Off' : v}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <InfoBox
              text="Prevents accidentally stacking 5 SPY calls from 5 separate alerts. When blocked, you'll receive an SMS (if enabled) explaining which ticker hit the limit."
              color="#f59e0b"
            />
          </SectionCard>

          {/* ═══ Risk Warning ═══ */}
          <View style={s.riskWarning}>
            <Ionicons name="warning-outline" size={20} color="#f59e0b" />
            <Text style={s.riskWarningText}>
              Auto-trading carries significant financial risk. Always start with simulation mode and small position sizes. Never risk money you cannot afford to lose.
            </Text>
          </View>

          <View style={{ height: 32 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#080f1a' },
  centered:     { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll:       { flex: 1 },

  header:       { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 },
  headerEyebrow:{ fontSize: 10, color: '#0ea5e9', fontWeight: '700', letterSpacing: 2, marginBottom: 2 },
  headerTitle:  { fontSize: 26, fontWeight: '800', color: '#e2e8f0' },
  headerBtns:   { flexDirection: 'row', gap: 8, alignItems: 'center' },
  discardBtn:   { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: '#1e2d3d' },
  discardText:  { fontSize: 13, color: '#64748b', fontWeight: '600' },
  saveBtn:      { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: '#0ea5e9' },
  saveBtnDim:   { backgroundColor: '#1e2d3d' },
  saveBtnText:  { fontSize: 13, color: '#fff', fontWeight: '700' },

  simBanner:    { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#2d1f5e', marginHorizontal: 16, marginBottom: 8, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: '#7c3aed' },
  simBannerText:{ fontSize: 12, color: '#a78bfa', fontWeight: '700', flex: 1 },
  dirtyBar:     { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#1c1500', paddingHorizontal: 20, paddingVertical: 6 },
  dirtyText:    { fontSize: 11, color: '#92400e' },

  card:         { backgroundColor: '#0d1826', borderRadius: 14, marginHorizontal: 16, marginBottom: 12, padding: 16, borderWidth: 1, borderColor: '#1e2d3d' },
  digestCard:   { backgroundColor: '#0d1826', borderRadius: 14, marginHorizontal: 16, marginBottom: 12, padding: 16, borderWidth: 1 },
  digestTop:    { flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  digestTitleBlock: { flex: 1 },
  digestEyebrow:{ fontSize: 10, color: '#64748b', fontWeight: '800', letterSpacing: 1.8, marginBottom: 4 },
  digestTitle:  { fontSize: 20, fontWeight: '900', color: '#f8fafc' },
  digestDetail: { fontSize: 12, color: '#94a3b8', lineHeight: 18, marginTop: 4 },
  readinessBadge: { minWidth: 78, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10 },
  readinessValue: { fontSize: 20, fontWeight: '900' },
  readinessLabel: { fontSize: 10, color: '#64748b', fontWeight: '700', textTransform: 'uppercase' },
  digestStats:  { flexDirection: 'row', gap: 8, marginTop: 14 },
  digestStat:   { flex: 1, minHeight: 58, borderRadius: 10, backgroundColor: '#08111d', borderWidth: 1, borderColor: '#1e2d3d', padding: 9, justifyContent: 'center' },
  digestStatValue: { fontSize: 14, fontWeight: '900', color: '#e2e8f0' },
  digestStatLabel: { fontSize: 10, color: '#475569', fontWeight: '700', marginTop: 3, textTransform: 'uppercase' },
  digestMetaRow: { flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' },
  digestMetaText: { fontSize: 11, color: '#64748b', fontWeight: '700', backgroundColor: '#08111d', borderRadius: 7, paddingHorizontal: 9, paddingVertical: 5 },
  warningList:  { marginTop: 12, gap: 8 },
  warningRow:   { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  warningCopy:  { flex: 1 },
  warningTitle: { fontSize: 12, color: '#e2e8f0', fontWeight: '800' },
  warningDetail:{ fontSize: 11, color: '#64748b', lineHeight: 16, marginTop: 1 },
  clearText:    { flex: 1, fontSize: 12, color: '#94a3b8', lineHeight: 17 },
  hiddenWarningText: { fontSize: 11, color: '#f59e0b', fontWeight: '700', marginLeft: 22 },
  sectionTitle: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 },
  sectionIcon:  { width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  sectionTitleText: { fontSize: 16, fontWeight: '800', color: '#e2e8f0' },
  sectionTitleSub:  { fontSize: 11, color: '#475569', marginTop: 1 },

  subSectionLabel: { fontSize: 10, color: '#334155', fontWeight: '700', letterSpacing: 1.5, marginBottom: 10, marginTop: 6 },
  divider:      { height: 1, backgroundColor: '#111c2a', marginVertical: 14 },

  fieldLabelWrap: { marginBottom: 6, marginTop: 12 },
  fieldLabel:   { fontSize: 13, fontWeight: '600', color: '#94a3b8' },
  fieldHint:    { fontSize: 11, color: '#334155', marginTop: 2 },

  input:        { backgroundColor: '#111c2a', borderRadius: 9, padding: 12, color: '#e2e8f0', fontSize: 15, borderWidth: 1, borderColor: '#1e2d3d', marginBottom: 4 },
  inputDisabled:{ opacity: 0.4 },

  switchRow:    { flexDirection: 'row', alignItems: 'center', paddingVertical: 10 },
  switchLeft:   { flex: 1 },
  switchLabel:  { fontSize: 14, fontWeight: '600', color: '#e2e8f0' },
  switchSub:    { fontSize: 12, color: '#475569', marginTop: 1 },
  
  customSwitch: { 
    width: 44, 
    height: 26, 
    borderRadius: 13, 
    padding: 3,
    justifyContent: 'center',
  },
  customSwitchThumb: { 
    width: 20, 
    height: 20, 
    borderRadius: 10, 
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 2,
  },

  quickRow:     { flexDirection: 'row', gap: 6, marginBottom: 6, flexWrap: 'wrap' },
  quickBtn:     { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, backgroundColor: '#1e2d3d' },
  quickBtnActive:{ backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9' },
  quickText:    { fontSize: 12, color: '#64748b', fontWeight: '600' },
  quickTextActive: { color: '#0ea5e9' },

  twoCol:       { flexDirection: 'row', gap: 10 },
  twoColItem:   { flex: 1 },

  btnRow:       { flexDirection: 'row', gap: 8, marginTop: 10 },
  actionBtn:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, padding: 12, borderRadius: 9 },
  actionBtnText:{ fontSize: 14, fontWeight: '700', color: '#fff' },

  validationWarn: { fontSize: 11, color: '#f59e0b', marginBottom: 6 },

  resultBox:    { borderRadius: 9, padding: 12, marginTop: 10, borderWidth: 1 },
  resultSuccess:{ backgroundColor: '#052e16', borderColor: '#22c55e' },
  resultError:  { backgroundColor: '#2d1515', borderColor: '#ef4444' },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  resultTitle:  { fontSize: 15, fontWeight: '700' },
  resultMsg:    { fontSize: 13, color: '#94a3b8', marginBottom: 4 },
  resultDetail: { fontSize: 12, color: '#64748b' },

  guideToggle:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#1e2d3d' },
  guideToggleLeft: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  guideToggleText: { fontSize: 13, color: '#94a3b8', fontWeight: '500' },
  guide:        { backgroundColor: '#080f1a', borderRadius: 9, padding: 14, marginTop: 10, borderWidth: 1, borderColor: '#1e2d3d' },
  guideStep:    { marginBottom: 16 },
  guideStepHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 },
  guideNum:     { width: 22, height: 22, borderRadius: 11, backgroundColor: '#5865F2', alignItems: 'center', justifyContent: 'center' },
  guideNumText: { fontSize: 11, fontWeight: '700', color: '#fff' },
  guideStepTitle: { fontSize: 13, fontWeight: '700', color: '#e2e8f0' },
  guideStepText: { fontSize: 12, color: '#64748b', lineHeight: 20, paddingLeft: 32 },

  brokerRow:    { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  brokerDot:    { width: 10, height: 10, borderRadius: 5 },
  brokerName:   { fontSize: 16, fontWeight: '700', flex: 1 },
  brokerConfigBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 7, backgroundColor: '#0c2740' },
  brokerConfigText: { fontSize: 12, color: '#0ea5e9', fontWeight: '600' },

  segmentRow:   { flexDirection: 'row', gap: 6, marginBottom: 8 },
  segBtn:       { flex: 1, padding: 10, borderRadius: 8, backgroundColor: '#1e2d3d', alignItems: 'center' },
  segBtnActive: { backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9' },
  segText:      { fontSize: 13, color: '#64748b', fontWeight: '600' },
  segTextActive:{ color: '#0ea5e9' },

  simWarning:   { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#1a0f3d', borderRadius: 7, padding: 10, marginTop: 6, borderWidth: 1, borderColor: '#7c3aed' },
  simWarningText: { flex: 1, fontSize: 12, color: '#a78bfa' },

  infoBox:      { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#080f1a', borderRadius: 7, padding: 10, marginTop: 12, borderLeftWidth: 2 },
  infoText:     { flex: 1, fontSize: 12, color: '#475569', lineHeight: 18 },

  patternsHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  patternsBody:   { marginTop: 14 },
  patternTypesRow:{ flexDirection: 'row', gap: 7 },
  patternTypeBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#111c2a' },
  patternTypeBtnText: { fontSize: 12, fontWeight: '600', color: '#64748b' },
  patternChips:   { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginBottom: 12 },
  chip:           { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: '#111c2a', borderWidth: 1 },
  chipText:       { fontSize: 12, color: '#e2e8f0' },
  noPatterns:     { fontSize: 12, color: '#334155', fontStyle: 'italic' },
  addPatternRow:  { flexDirection: 'row', gap: 8, marginBottom: 10 },
  addPatternBtn:  { width: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0c2740', borderRadius: 9, borderWidth: 1, borderColor: '#0ea5e9' },
  resetPatternsBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, padding: 11, borderRadius: 8, backgroundColor: '#2d1515' },
  resetPatternsBtnText: { fontSize: 13, color: '#f87171', fontWeight: '600' },

  thresholdBlock:  { backgroundColor: '#080f1a', borderRadius: 10, padding: 12, marginTop: 10, borderWidth: 1, borderColor: '#1e2d3d' },
  thresholdHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  thresholdLabel:  { fontSize: 13, fontWeight: '700', color: '#e2e8f0' },
  thresholdHint:   { fontSize: 11, color: '#334155', marginTop: 2 },
  stepperWrap:     { flexDirection: 'row', alignItems: 'center', gap: 0, backgroundColor: '#111c2a', borderRadius: 9, borderWidth: 1, borderColor: '#1e2d3d', overflow: 'hidden' },
  stepperBtn:      { width: 36, height: 38, alignItems: 'center', justifyContent: 'center', backgroundColor: '#1e2d3d' },
  stepperInputWrap:{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 4 },
  stepperDollar:   { fontSize: 13, color: '#475569', fontWeight: '700' },
  stepperInput:    { minWidth: 44, maxWidth: 72, height: 38, textAlign: 'center', color: '#e2e8f0', fontSize: 15, fontWeight: '800', paddingHorizontal: 6 },
  thresholdPresets:{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  preset:          { paddingHorizontal: 11, paddingVertical: 5, borderRadius: 6, backgroundColor: '#1e2d3d' },
  presetActive:    { backgroundColor: '#2d1515', borderWidth: 1, borderColor: '#f87171' },
  presetText:      { fontSize: 12, color: '#475569', fontWeight: '600' },
  presetTextActive:{ color: '#f87171' },

  riskWarning:  { flexDirection: 'row', alignItems: 'flex-start', gap: 10, backgroundColor: '#1c1400', marginHorizontal: 16, marginTop: 4, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: '#92400e' },
  riskWarningText: { flex: 1, fontSize: 13, color: '#92400e', lineHeight: 19 },

  smsEventGrid:  { gap: 8, marginTop: 6 },
  smsEventRow:   { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 3 },
  smsEventLabel: { fontSize: 13, color: '#64748b' },

});
