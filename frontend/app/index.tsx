import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  AppState,
  AppStateStatus,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { api } from '../utils/api';
import { BACKEND_URL, DEMO_MODE } from '../constants/config';
import { BROKER_COLORS, BROKER_NAMES } from '../constants/brokers';
import { formatDate, formatPnL, getPnLColor } from '../utils/format';
import {
  buildDashboardReadiness,
  DashboardReadiness,
  ReadinessActionTarget,
  ReadinessTone,
} from '../utils/dashboardReadiness';
import { buildOperatorActionQueue, OperatorActionTarget } from '../utils/operatorActionQueue';
import { summarizeAlerts } from '../utils/alertDigest';
import { summarizePositions } from '../utils/positionDigest';
import { summarizeSettings } from '../utils/settingsDigest';
import { summarizeTrades } from '../utils/tradeDigest';
import {
  normalizeDashboardRuntimeState,
  normalizeDashboardStatusFlags,
  readDashboardToggleValue,
} from '../utils/dashboardRuntimeState';

type AccentKey = 'indigo' | 'mint' | 'amber' | 'rose' | 'sky' | 'violet' | 'gold' | 'coral';
type PatternKey = 'triangle' | 'hex' | 'circuit';
type ThemeKey = 'midnight' | 'space' | 'forest';
type DensityKey = 'compact' | 'standard' | 'spacious';

interface UiPrefs {
  accentKey: AccentKey;
  pattern: PatternKey;
  glassOpacity: number;
  blur: number;
  theme: ThemeKey;
  density: DensityKey;
  cardGlow: boolean;
  pipelineTrack: boolean;
  animatedDots: boolean;
}

interface ThemeTokens {
  name: string;
  bg: string;
  bg2: string;
  card: string;
  cardAlt: string;
  text: string;
  muted: string;
  faint: string;
  border: string;
}

interface BotStatus {
  discord_connected: boolean;
  broker_connected: boolean;
  active_broker: string;
  auto_trading_enabled: boolean;
  simulation_mode?: boolean;
  last_alert_time: string | null;
  alerts_processed?: number;
}

interface AlertItem {
  id: string;
  ticker: string;
  strike: number;
  option_type: string;
  expiration: string;
  entry_price: number;
  received_at: string;
  processed: boolean;
  trade_executed: boolean;
  channel_name?: string | null;
}

interface Trade {
  id: string;
  ticker: string;
  strike: number;
  option_type: string;
  expiration: string;
  entry_price: number;
  exit_price: number | null;
  current_price: number | null;
  quantity: number;
  status: string;
  executed_at: string | null;
  broker: string;
  simulated: boolean;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
}

interface PositionItem {
  id: string;
  ticker: string;
  strike?: number | null;
  option_type?: string | null;
  expiration?: string | null;
  entry_price?: number | null;
  current_price?: number | null;
  remaining_quantity?: number | null;
  total_cost?: number | null;
  status: string;
  simulated?: boolean | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
}

interface PortfolioSummary {
  total_trades: number;
  open_positions: number;
  closed_positions: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_pnl: number;
  win_rate: number;
  winning_trades: number;
  losing_trades: number;
  best_trade: number;
  worst_trade: number;
  average_pnl: number;
}

interface ShutdownSettings {
  max_consecutive_losses: number;
  max_daily_losses: number;
  max_daily_loss_amount: number;
  consecutive_losses: number;
  daily_losses: number;
  shutdown_triggered: boolean;
  shutdown_reason: string;
}

interface AppSettings {
  discord_token?: string | null;
  discord_channel_ids?: string[] | null;
  active_broker?: string | null;
  auto_trading_enabled?: boolean | null;
  default_quantity?: number | null;
  simulation_mode?: boolean | null;
  max_position_size?: number | null;
  take_profit_enabled?: boolean | null;
  stop_loss_enabled?: boolean | null;
  trailing_stop_enabled?: boolean | null;
  auto_shutdown_enabled?: boolean | null;
  premium_buffer_enabled?: boolean | null;
  sms_enabled?: boolean | null;
  sms_phone_number?: string | null;
}

interface AlertPatterns {
  buy_patterns?: string[] | null;
  sell_patterns?: string[] | null;
  partial_sell_patterns?: string[] | null;
  average_down_patterns?: string[] | null;
  stop_loss_patterns?: string[] | null;
  take_profit_patterns?: string[] | null;
  ignore_patterns?: string[] | null;
}

type ParsePreviewWarning = { title?: string; detail?: string; message?: string } | string;

interface ParsePreview {
  parsed?: Record<string, any> | null;
  skip_reason?: string | null;
  confidence?: string | null;
  warnings?: ParsePreviewWarning[];
  execution_preview?: Record<string, any> | null;
  source_config?: Record<string, any> | null;
  parser_metadata?: Record<string, any> | null;
}

interface ReplayPreview {
  execution_mode?: string;
  event_count?: number;
  parsed_count?: number;
  would_request_trade_count?: number;
  drift_alert_count?: number;
  replay_url?: string;
  results?: Record<string, any>[];
}

const ACCENTS: Record<AccentKey, { name: string; color: string }> = {
  indigo: { name: 'Indigo', color: '#6366f1' },
  mint: { name: 'Mint', color: '#25d0a4' },
  amber: { name: 'Amber', color: '#f59e0b' },
  rose: { name: 'Rose', color: '#f43f5e' },
  sky: { name: 'Sky', color: '#38bdf8' },
  violet: { name: 'Violet', color: '#a78bfa' },
  gold: { name: 'Gold', color: '#d8ad1f' },
  coral: { name: 'Coral', color: '#fb7185' },
};

const THEMES: Record<ThemeKey, ThemeTokens> = {
  midnight: {
    name: 'Midnight',
    bg: '#020617',
    bg2: '#07111f',
    card: '#0b1220',
    cardAlt: '#101827',
    text: '#e5edf8',
    muted: '#9db0cc',
    faint: '#62718e',
    border: '#1e2d44',
  },
  space: {
    name: 'Space',
    bg: '#050416',
    bg2: '#0d0820',
    card: '#10091c',
    cardAlt: '#151021',
    text: '#edf3ff',
    muted: '#aec0e5',
    faint: '#68779b',
    border: '#29213a',
  },
  forest: {
    name: 'Forest',
    bg: '#02120b',
    bg2: '#062018',
    card: '#081a12',
    cardAlt: '#0c251a',
    text: '#e8fff3',
    muted: '#a7cdb6',
    faint: '#5f826d',
    border: '#183927',
  },
};

const DEFAULT_UI_PREFS: UiPrefs = {
  accentKey: 'rose',
  pattern: 'circuit',
  glassOpacity: 88,
  blur: 15,
  theme: 'space',
  density: 'compact',
  cardGlow: false,
  pipelineTrack: true,
  animatedDots: false,
};

const DENSITY_PADDING: Record<DensityKey, number> = {
  compact: 12,
  standard: 16,
  spacious: 22,
};

const DEMO_STATUS: BotStatus = {
  discord_connected: true,
  broker_connected: true,
  active_broker: 'ibkr',
  auto_trading_enabled: true,
  simulation_mode: true,
  last_alert_time: new Date().toISOString(),
  alerts_processed: 24,
};

const DEMO_ALERTS: AlertItem[] = [
  {
    id: '1',
    ticker: 'SPY',
    strike: 738,
    option_type: 'PUT',
    expiration: '2026-06-18',
    entry_price: 0.6,
    received_at: '2026-06-18T15:10:00Z',
    processed: true,
    trade_executed: true,
    channel_name: 'alerts',
  },
  {
    id: '2',
    ticker: 'QQQ',
    strike: 520,
    option_type: 'CALL',
    expiration: '2026-06-18',
    entry_price: 1.35,
    received_at: '2026-06-18T14:45:00Z',
    processed: true,
    trade_executed: false,
    channel_name: 'alerts',
  },
  {
    id: '3',
    ticker: 'NVDA',
    strike: 152,
    option_type: 'CALL',
    expiration: '2026-06-18',
    entry_price: 2.1,
    received_at: '2026-06-17T18:20:00Z',
    processed: false,
    trade_executed: false,
    channel_name: 'watch',
  },
];

const DEMO_TRADES: Trade[] = [
  {
    id: '1',
    ticker: 'SPY',
    strike: 738,
    option_type: 'PUT',
    expiration: '2026-06-18',
    entry_price: 0.6,
    exit_price: 0.83,
    current_price: null,
    quantity: 1,
    status: 'closed',
    executed_at: '2026-06-18T15:11:00Z',
    broker: 'ibkr',
    simulated: true,
    realized_pnl: 23,
    unrealized_pnl: null,
  },
  {
    id: '2',
    ticker: 'QQQ',
    strike: 520,
    option_type: 'CALL',
    expiration: '2026-06-18',
    entry_price: 1.35,
    exit_price: null,
    current_price: 1.12,
    quantity: 1,
    status: 'open',
    executed_at: '2026-06-18T14:47:00Z',
    broker: 'ibkr',
    simulated: true,
    realized_pnl: null,
    unrealized_pnl: -23,
  },
];

const DEMO_POSITIONS: PositionItem[] = [
  {
    id: 'p1',
    ticker: 'QQQ',
    strike: 520,
    option_type: 'CALL',
    expiration: '2026-06-18',
    entry_price: 1.35,
    current_price: 1.12,
    remaining_quantity: 1,
    status: 'open',
    simulated: true,
    unrealized_pnl: -23,
    realized_pnl: null,
  },
];

const DEMO_PORTFOLIO: PortfolioSummary = {
  total_trades: 34,
  open_positions: 1,
  closed_positions: 33,
  total_realized_pnl: 1240,
  total_unrealized_pnl: -23,
  total_pnl: 1217,
  win_rate: 64,
  winning_trades: 21,
  losing_trades: 12,
  best_trade: 410,
  worst_trade: -165,
  average_pnl: 35.79,
};

const DEMO_SETTINGS: AppSettings = {
  discord_token: 'configured',
  discord_channel_ids: ['872226993557606440', '1224357494365622376'],
  active_broker: 'ibkr',
  auto_trading_enabled: true,
  default_quantity: 1,
  simulation_mode: true,
  max_position_size: 100,
  take_profit_enabled: false,
  stop_loss_enabled: false,
  trailing_stop_enabled: true,
  auto_shutdown_enabled: true,
  premium_buffer_enabled: false,
  sms_enabled: false,
};

const DEMO_PATTERNS: AlertPatterns = {
  buy_patterns: ['BTO', 'BUY', 'ENTRY'],
  sell_patterns: ['STC', 'SELL', 'EXIT'],
  partial_sell_patterns: ['TRIM'],
  average_down_patterns: ['AVG DOWN', 'AVG'],
  stop_loss_patterns: ['STOP'],
  take_profit_patterns: ['TARGET'],
  ignore_patterns: ['WATCHLIST', 'PAPER'],
};

const DEMO_SHUTDOWN: ShutdownSettings = {
  max_consecutive_losses: 3,
  max_daily_losses: 5,
  max_daily_loss_amount: 500,
  consecutive_losses: 1,
  daily_losses: 2,
  shutdown_triggered: false,
  shutdown_reason: '',
};

const DEFAULT_SAMPLE_ALERT = `$SPY
$738 PUTS
 EXPIRATION 6/18/2026
$.6 Entry. $.55 AVG`;

const READINESS_TONE: Record<ReadinessTone, { accent: string; icon: string }> = {
  live: { accent: '#22c55e', icon: 'checkmark-circle' },
  attention: { accent: '#f59e0b', icon: 'alert-circle' },
  blocked: { accent: '#ef4444', icon: 'warning' },
};

const ROUTE_GROUPS = [
  { label: 'Dashboard', route: '/', icon: 'pulse-outline' },
  { label: 'Alerts', route: '/alerts', icon: 'notifications-outline' },
  { label: 'Trades', route: '/trades', icon: 'receipt-outline' },
  { label: 'Positions', route: '/positions', icon: 'briefcase-outline' },
  { label: 'Operator Lab', route: '/operator-lab', icon: 'flask-outline' },
  { label: 'Strike Selection', route: '/strike-selection', icon: 'trending-up-outline' },
  { label: 'Trading', route: '/trading-settings', icon: 'options-outline' },
  { label: 'Risk', route: '/risk-settings', icon: 'shield-outline' },
  { label: 'Discord', route: '/settings', icon: 'chatbubbles-outline' },
  { label: 'Broker', route: '/broker-config', icon: 'key-outline' },
  { label: 'Profiles', route: '/profiles', icon: 'people-outline' },
  { label: 'Settings', route: '/settings', icon: 'settings-outline' },
];

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const bigint = parseInt(clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean, 16);
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `rgba(${r}, ${g}, ${b}, ${Math.min(1, Math.max(0, alpha))})`;
}

function compactNumber(value: number | undefined | null): string {
  const next = Number(value ?? 0);
  if (!Number.isFinite(next)) return '0';
  if (Math.abs(next) >= 1000) return `${(next / 1000).toFixed(1)}k`;
  return String(Math.round(next));
}

function safeUpper(value: string | null | undefined, fallback = 'None'): string {
  const normalized = String(value || '').trim();
  return normalized ? normalized.toUpperCase() : fallback;
}

function firstConfiguredChannel(settings: AppSettings | null): string | undefined {
  return settings?.discord_channel_ids?.find((channel) => String(channel || '').trim().length > 0);
}

function toneToColor(tone: string): string {
  if (tone === 'live') return '#22c55e';
  if (tone === 'attention') return '#f59e0b';
  if (tone === 'blocked') return '#ef4444';
  return '#94a3b8';
}

function warningText(warning: NonNullable<ParsePreview['warnings']>[number]): string {
  if (typeof warning === 'string') return warning;
  return warning.title || warning.detail || warning.message || 'Parser warning';
}

function useThemedCard(theme: ThemeTokens, prefs: UiPrefs) {
  const accent = ACCENTS[prefs.accentKey].color;
  return useMemo(
    () => ({
      backgroundColor: hexToRgba(theme.card, prefs.glassOpacity / 100),
      borderColor: prefs.cardGlow ? hexToRgba(accent, 0.74) : hexToRgba(theme.border, 0.95),
      shadowColor: prefs.cardGlow ? accent : '#000',
      padding: DENSITY_PADDING[prefs.density],
      ...(Platform.OS === 'web'
        ? {
            backdropFilter: `blur(${prefs.blur}px)`,
            WebkitBackdropFilter: `blur(${prefs.blur}px)`,
          }
        : null),
    }),
    [accent, prefs.blur, prefs.cardGlow, prefs.density, prefs.glassOpacity, theme.border, theme.card]
  );
}

function SectionTitle({ eyebrow, title, detail, theme }: { eyebrow: string; title: string; detail?: string; theme: ThemeTokens }) {
  return (
    <View style={styles.sectionTitleBlock}>
      <Text style={[styles.eyebrow, { color: theme.faint }]}>{eyebrow}</Text>
      <Text style={[styles.sectionTitle, { color: theme.text }]}>{title}</Text>
      {detail ? <Text style={[styles.sectionDetail, { color: theme.muted }]}>{detail}</Text> : null}
    </View>
  );
}

function IconAction({
  icon,
  label,
  onPress,
  accent,
  disabled = false,
  solid = false,
}: {
  icon: string;
  label: string;
  onPress: () => void;
  accent: string;
  disabled?: boolean;
  solid?: boolean;
}) {
  return (
    <TouchableOpacity
      style={[
        styles.iconAction,
        solid && { backgroundColor: accent, borderColor: accent },
        disabled && styles.disabled,
      ]}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      activeOpacity={0.78}
    >
      <Ionicons name={icon as any} size={16} color={solid ? '#070812' : accent} />
      <Text style={[styles.iconActionText, { color: solid ? '#070812' : accent }]}>{label}</Text>
    </TouchableOpacity>
  );
}

function StatusDot({ active, color, animated }: { active: boolean; color: string; animated: boolean }) {
  return (
    <View
      style={[
        styles.statusDot,
        { backgroundColor: active ? color : '#64748b' },
        animated && active && { borderColor: hexToRgba(color, 0.35), borderWidth: 4 },
      ]}
    />
  );
}

function MetricTile({
  label,
  value,
  detail,
  color,
  theme,
}: {
  label: string;
  value: string;
  detail?: string;
  color?: string;
  theme: ThemeTokens;
}) {
  return (
    <View style={[styles.metricTile, { borderColor: hexToRgba(theme.border, 0.8), backgroundColor: hexToRgba(theme.cardAlt, 0.62) }]}>
      <Text style={[styles.metricLabel, { color: theme.faint }]}>{label}</Text>
      <Text style={[styles.metricValue, color ? { color } : { color: theme.text }]}>{value}</Text>
      {detail ? <Text style={[styles.metricDetail, { color: theme.muted }]}>{detail}</Text> : null}
    </View>
  );
}

function MiniButton({
  label,
  selected,
  onPress,
  accent,
  theme,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  accent: string;
  theme: ThemeTokens;
}) {
  return (
    <TouchableOpacity
      style={[
        styles.miniButton,
        { borderColor: selected ? accent : theme.border, backgroundColor: selected ? hexToRgba(accent, 0.18) : hexToRgba(theme.cardAlt, 0.66) },
      ]}
      onPress={onPress}
      accessibilityRole="button"
    >
      <Text style={[styles.miniButtonText, { color: selected ? accent : theme.muted }]}>{label}</Text>
    </TouchableOpacity>
  );
}

function RangeInput({
  value,
  min,
  max,
  step,
  onChange,
  accent,
  theme,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  accent: string;
  theme: ThemeTokens;
}) {
  if (Platform.OS !== 'web') return null;

  return React.createElement('input' as any, {
    type: 'range',
    min,
    max,
    step,
    value,
    onChange: (event: any) => onChange(Number(event.target.value)),
    style: {
      width: '100%',
      height: 18,
      accentColor: accent,
      cursor: 'pointer',
      background: 'transparent',
      color: accent,
      outline: 'none',
      border: 0,
      margin: 0,
      padding: 0,
      ['--range-track' as any]: hexToRgba(theme.text, 0.16),
    },
    'aria-label': 'range slider',
  });
}

function PrefSlider({
  label,
  value,
  suffix,
  min,
  max,
  step,
  onChange,
  accent,
  theme,
}: {
  label: string;
  value: number;
  suffix: string;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  accent: string;
  theme: ThemeTokens;
}) {
  const percentage = ((value - min) / Math.max(max - min, 1)) * 100;
  const update = (direction: -1 | 1) => {
    const next = Math.min(max, Math.max(min, value + step * direction));
    onChange(next);
  };

  return (
    <View style={styles.prefSlider}>
      <View style={styles.prefSliderHeader}>
        <Text style={[styles.prefLabel, { color: theme.muted }]}>{label}</Text>
        <Text style={[styles.prefValue, { color: theme.muted }]}>{value}{suffix}</Text>
      </View>
      <View style={styles.prefSliderRow}>
        <TouchableOpacity style={[styles.stepper, { borderColor: theme.border }]} onPress={() => update(-1)} accessibilityRole="button">
          <Ionicons name="remove" size={16} color={theme.muted} />
        </TouchableOpacity>
        {Platform.OS === 'web' ? (
          <View style={styles.rangeInputWrap}>
            <RangeInput value={value} min={min} max={max} step={step} onChange={onChange} accent={accent} theme={theme} />
          </View>
        ) : (
          <View style={[styles.prefTrack, { backgroundColor: hexToRgba(theme.text, 0.16) }]}>
            <View style={[styles.prefTrackFill, { backgroundColor: accent, width: `${percentage}%` }]} />
          </View>
        )}
        <TouchableOpacity style={[styles.stepper, { borderColor: theme.border }]} onPress={() => update(1)} accessibilityRole="button">
          <Ionicons name="add" size={16} color={theme.muted} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

function ToggleLine({
  label,
  detail,
  enabled,
  onToggle,
  accent,
  theme,
  loading = false,
}: {
  label: string;
  detail?: string;
  enabled: boolean;
  onToggle: () => void;
  accent: string;
  theme: ThemeTokens;
  loading?: boolean;
}) {
  return (
    <View style={[styles.toggleLine, { borderColor: hexToRgba(theme.border, 0.7) }]}>
      <View style={styles.toggleLineCopy}>
        <Text style={[styles.toggleLineLabel, { color: theme.text }]}>{label}</Text>
        {detail ? <Text style={[styles.toggleLineDetail, { color: theme.faint }]}>{detail}</Text> : null}
      </View>
      {loading ? (
        <ActivityIndicator size="small" color={accent} />
      ) : (
        <Switch
          value={enabled}
          onValueChange={onToggle}
          accessibilityLabel={label}
          trackColor={{ false: '#20283b', true: hexToRgba(accent, 0.65) }}
          thumbColor={enabled ? '#ffffff' : '#d8deea'}
        />
      )}
    </View>
  );
}

function PipelineStage({
  label,
  detail,
  icon,
  active,
  accent,
  theme,
  animated,
  compact = false,
}: {
  label: string;
  detail: string;
  icon: string;
  active: boolean;
  accent: string;
  theme: ThemeTokens;
  animated: boolean;
  compact?: boolean;
}) {
  const color = active ? accent : theme.faint;
  return (
    <View style={[styles.pipelineStage, compact && styles.pipelineStageCompact, { borderColor: active ? hexToRgba(accent, 0.55) : hexToRgba(theme.border, 0.8) }]}>
      <View style={[styles.pipelineIcon, compact && styles.pipelineIconCompact, { backgroundColor: hexToRgba(color, active ? 0.18 : 0.1) }]}>
        <Ionicons name={icon as any} size={compact ? 13 : 16} color={color} />
      </View>
      <View style={[styles.pipelineCopy, compact && styles.pipelineCopyCompact]}>
        <Text numberOfLines={1} style={[styles.pipelineLabel, compact && styles.pipelineLabelCompact, { color: active ? theme.text : theme.muted }]}>{label}</Text>
        {!compact ? <Text style={[styles.pipelineDetail, { color: theme.faint }]}>{detail}</Text> : null}
      </View>
      {!compact ? <StatusDot active={active} color={accent} animated={animated} /> : null}
    </View>
  );
}

function ShellHeader({
  status,
  autoTrading,
  trailingStop,
  stopLoss,
  theme,
  prefs,
  onToggleAutoTrading,
  autoTradingLoading,
  onOpenNotifications,
  onOpenCustomizer,
}: {
  status: BotStatus | null;
  autoTrading: boolean;
  trailingStop: boolean;
  stopLoss: boolean;
  theme: ThemeTokens;
  prefs: UiPrefs;
  onToggleAutoTrading: () => void;
  autoTradingLoading: boolean;
  onOpenNotifications: () => void;
  onOpenCustomizer: () => void;
}) {
  const accent = ACCENTS[prefs.accentKey].color;
  const statusFlags = normalizeDashboardStatusFlags(status);

  return (
    <View style={[styles.pipelineShellHeader, { borderBottomColor: hexToRgba(theme.border, 0.84), backgroundColor: hexToRgba(theme.bg, 0.86) }]}>
      <View style={[styles.pipelineBrandSlot, { borderRightColor: hexToRgba(theme.border, 0.84) }]}>
        <View style={[styles.pipelineLogo, { backgroundColor: hexToRgba(accent, 0.18), borderColor: hexToRgba(accent, 0.46) }]}>
          <Ionicons name="pulse" size={16} color={accent} />
        </View>
      </View>

      {prefs.pipelineTrack ? (
        <View style={styles.pipelineTrackBar}>
          <PipelineStage label="Discord" detail={statusFlags.discordConnected ? 'Live' : 'Offline'} icon="logo-discord" active={statusFlags.discordConnected} accent={accent} theme={theme} animated={prefs.animatedDots} compact />
          <Ionicons name="chevron-forward" size={13} color={theme.faint} />
          <PipelineStage label="Parse" detail="Rules" icon="filter-outline" active={statusFlags.discordConnected} accent={accent} theme={theme} animated={prefs.animatedDots} compact />
          <Ionicons name="chevron-forward" size={13} color={theme.faint} />
          <PipelineStage label="Risk" detail={trailingStop || stopLoss ? 'Guarded' : 'Review'} icon="shield-checkmark-outline" active={trailingStop || stopLoss} accent={accent} theme={theme} animated={prefs.animatedDots} compact />
          <Ionicons name="chevron-forward" size={13} color={theme.faint} />
          <PipelineStage label="Execute" detail={autoTrading ? 'Armed' : 'Manual'} icon="flash-outline" active={statusFlags.brokerConnected && autoTrading} accent={accent} theme={theme} animated={prefs.animatedDots} compact />
        </View>
      ) : (
        <View style={styles.pipelineTrackBar} />
      )}

      <View style={styles.pipelineHeaderActions}>
        <View style={[styles.discordPill, { borderColor: hexToRgba(accent, 0.36), backgroundColor: hexToRgba(accent, 0.15) }]}>
          <StatusDot active={statusFlags.discordConnected} color={accent} animated={prefs.animatedDots} />
          <Text style={[styles.discordPillText, { color: accent }]}>Discord</Text>
        </View>

        <TouchableOpacity
          style={[
            styles.autoTradePill,
            {
              borderColor: autoTrading ? hexToRgba('#22d3a0', 0.42) : hexToRgba(theme.border, 0.9),
              backgroundColor: autoTrading ? hexToRgba('#22d3a0', 0.15) : hexToRgba(theme.cardAlt, 0.52),
            },
          ]}
          onPress={onToggleAutoTrading}
          disabled={autoTradingLoading}
          accessibilityRole="switch"
          accessibilityState={{ checked: autoTrading, disabled: autoTradingLoading }}
          activeOpacity={0.78}
        >
          <Text style={[styles.autoTradeText, { color: autoTrading ? '#22d3a0' : theme.muted }]}>Auto trading</Text>
          <View style={[styles.miniSwitchTrack, { backgroundColor: autoTrading ? '#22d3a0' : hexToRgba(theme.text, 0.14) }]}>
            <View style={[styles.miniSwitchThumb, autoTrading && styles.miniSwitchThumbOn]} />
          </View>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.headerIconButton, { borderColor: theme.border, backgroundColor: hexToRgba(theme.cardAlt, 0.52) }]} onPress={onOpenNotifications} accessibilityRole="button" accessibilityLabel="Notifications">
          <Ionicons name="notifications-outline" size={16} color={theme.muted} />
        </TouchableOpacity>
        <TouchableOpacity style={[styles.headerIconButton, { borderColor: theme.border, backgroundColor: hexToRgba(theme.cardAlt, 0.52) }]} onPress={onOpenCustomizer} accessibilityRole="button" accessibilityLabel="Customize dashboard">
          <Ionicons name="color-palette-outline" size={17} color={accent} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

function BackgroundPattern({ theme, prefs }: { theme: ThemeTokens; prefs: UiPrefs }) {
  const accent = ACCENTS[prefs.accentKey].color;
  const patternColor = hexToRgba(accent, prefs.pattern === 'circuit' ? 0.18 : 0.11);
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: theme.bg }]}>
      {prefs.pattern === 'triangle' && (
        <View style={styles.patternLayer}>
          {[0, 1, 2, 3, 4].map((item) => (
            <View key={item} style={[styles.triangleMark, { borderBottomColor: patternColor, left: `${item * 24 + 5}%`, top: `${item * 13 + 6}%` }]} />
          ))}
        </View>
      )}
      {prefs.pattern === 'hex' && (
        <View style={styles.patternLayer}>
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <View key={item} style={[styles.hexMark, { borderColor: patternColor, left: `${item * 16 + 4}%`, top: `${(item % 3) * 24 + 12}%` }]} />
          ))}
        </View>
      )}
      {prefs.pattern === 'circuit' && (
        <View style={styles.patternLayer}>
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <View key={`h-${item}`} style={[styles.circuitLineH, { backgroundColor: patternColor, top: `${item * 16 + 7}%`, left: `${item % 2 === 0 ? 4 : 22}%` }]} />
          ))}
          {[0, 1, 2, 3, 4].map((item) => (
            <View key={`v-${item}`} style={[styles.circuitLineV, { backgroundColor: patternColor, left: `${item * 18 + 10}%`, top: `${item % 2 === 0 ? 10 : 32}%` }]} />
          ))}
          {[0, 1, 2, 3, 4, 5, 6].map((item) => (
            <View key={`n-${item}`} style={[styles.circuitNode, { borderColor: patternColor, left: `${item * 13 + 8}%`, top: `${(item % 4) * 19 + 10}%` }]} />
          ))}
        </View>
      )}
    </View>
  );
}

function CustomizerModal({
  visible,
  prefs,
  onChange,
  onClose,
}: {
  visible: boolean;
  prefs: UiPrefs;
  onChange: (prefs: UiPrefs) => void;
  onClose: () => void;
}) {
  const theme = THEMES[prefs.theme];
  const accent = ACCENTS[prefs.accentKey].color;
  const update = <K extends keyof UiPrefs>(key: K, value: UiPrefs[K]) => onChange({ ...prefs, [key]: value });

  if (!visible) return null;

  return (
    <View
      style={[
        styles.modalScrim,
        Platform.OS === 'web' ? ({ position: 'fixed' } as any) : null,
        { backgroundColor: hexToRgba(theme.bg, 0.98) },
      ]}
    >
      <View style={[styles.customizer, { backgroundColor: theme.bg, borderColor: theme.border }]}>
        <View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: theme.bg }]} />
        <View style={styles.customizerHeader}>
          <View>
            <Text style={[styles.customizerTitle, { color: theme.text }]}>Make it yours</Text>
            <Text style={[styles.customizerSub, { color: theme.muted }]}>All changes are instant and session-scoped.</Text>
            <Text style={[styles.customizerSub, { color: theme.muted }]}>Mix and match to find your setup.</Text>
          </View>
          <TouchableOpacity style={[styles.closeButton, { borderColor: theme.border }]} onPress={onClose} accessibilityRole="button">
            <Ionicons name="close" size={20} color={theme.muted} />
          </TouchableOpacity>
        </View>

        <ScrollView showsVerticalScrollIndicator={false}>
          <Text style={[styles.prefEyebrow, { color: theme.faint }]}>ACCENT COLOR</Text>
          <View style={styles.swatchGrid}>
            {(Object.keys(ACCENTS) as AccentKey[]).map((key) => (
              <TouchableOpacity
                key={key}
                style={[
                  styles.swatch,
                  { backgroundColor: ACCENTS[key].color },
                  prefs.accentKey === key && { borderColor: '#ffffff', borderWidth: 3 },
                ]}
                onPress={() => update('accentKey', key)}
                accessibilityRole="button"
                accessibilityLabel={ACCENTS[key].name}
              />
            ))}
          </View>

          <Text style={[styles.prefEyebrow, { color: theme.faint }]}>BACKGROUND PATTERN</Text>
          <View style={styles.segmentWrap}>
            {([
              ['triangle', 'Triangle', 'triangle-outline'],
              ['hex', 'Hex', 'hardware-chip-outline'],
              ['circuit', 'Circuit', 'git-network-outline'],
            ] as [PatternKey, string, string][]).map(([key, label, icon]) => (
              <TouchableOpacity
                key={key}
                style={[
                  styles.segmentChoice,
                  { borderColor: prefs.pattern === key ? accent : theme.border, backgroundColor: prefs.pattern === key ? hexToRgba(accent, 0.18) : hexToRgba(theme.cardAlt, 0.52) },
                ]}
                onPress={() => update('pattern', key)}
                accessibilityRole="button"
              >
                <Ionicons name={icon as any} size={14} color={prefs.pattern === key ? accent : theme.muted} />
                <Text style={[styles.segmentChoiceText, { color: prefs.pattern === key ? accent : theme.muted }]}>{label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <PrefSlider label="Opacity" value={prefs.glassOpacity} suffix="%" min={45} max={95} step={1} onChange={(value) => update('glassOpacity', value)} accent={accent} theme={theme} />
          <PrefSlider label="Blur" value={prefs.blur} suffix="px" min={0} max={30} step={1} onChange={(value) => update('blur', value)} accent={accent} theme={theme} />

          <Text style={[styles.prefEyebrow, { color: theme.faint }]}>BASE THEME</Text>
          <View style={styles.segmentWrap}>
            {(Object.keys(THEMES) as ThemeKey[]).map((key) => (
              <MiniButton
                key={key}
                label={THEMES[key].name}
                selected={prefs.theme === key}
                onPress={() => update('theme', key)}
                accent={accent}
                theme={theme}
              />
            ))}
          </View>

          <Text style={[styles.prefEyebrow, { color: theme.faint }]}>DENSITY</Text>
          <View style={styles.segmentWrap}>
            {(['compact', 'standard', 'spacious'] as DensityKey[]).map((key) => (
              <MiniButton
                key={key}
                label={key[0].toUpperCase() + key.slice(1)}
                selected={prefs.density === key}
                onPress={() => update('density', key)}
                accent={accent}
                theme={theme}
              />
            ))}
          </View>

          <Text style={[styles.prefEyebrow, { color: theme.faint }]}>OPTIONS</Text>
          <ToggleLine label="Card border glow" enabled={prefs.cardGlow} onToggle={() => update('cardGlow', !prefs.cardGlow)} accent={accent} theme={theme} />
          <ToggleLine label="Pipeline header track" enabled={prefs.pipelineTrack} onToggle={() => update('pipelineTrack', !prefs.pipelineTrack)} accent={accent} theme={theme} />
          <ToggleLine label="Animated status dots" enabled={prefs.animatedDots} onToggle={() => update('animatedDots', !prefs.animatedDots)} accent={accent} theme={theme} />
        </ScrollView>
      </View>
    </View>
  );
}

function ReadinessCard({
  readiness,
  theme,
  prefs,
  onAction,
}: {
  readiness: DashboardReadiness;
  theme: ThemeTokens;
  prefs: UiPrefs;
  onAction: (target: ReadinessActionTarget) => void;
}) {
  const tone = READINESS_TONE[readiness.tone];
  const cardStyle = useThemedCard(theme, prefs);

  return (
    <View style={[styles.glassCard, cardStyle]}>
      <View style={styles.cardHeaderRow}>
        <SectionTitle eyebrow="OPERATOR READINESS" title={readiness.title} detail={readiness.summary} theme={theme} />
        <View style={[styles.scoreDial, { backgroundColor: hexToRgba(tone.accent, 0.16), borderColor: hexToRgba(tone.accent, 0.42) }]}>
          <Text style={[styles.scoreDialValue, { color: tone.accent }]}>{readiness.score}</Text>
          <Text style={[styles.scoreDialLabel, { color: theme.faint }]}>%</Text>
        </View>
      </View>

      <View style={styles.readinessGrid}>
        {readiness.items.map((item) => {
          const itemTone = READINESS_TONE[item.state === 'ready' ? 'live' : item.state];
          const canAct = Boolean(item.actionTarget && item.state !== 'ready');
          return (
            <TouchableOpacity
              key={item.id}
              style={[styles.readinessItem, { borderColor: hexToRgba(itemTone.accent, item.state === 'ready' ? 0.16 : 0.38) }]}
              onPress={() => item.actionTarget && onAction(item.actionTarget)}
              disabled={!canAct}
              accessibilityRole="button"
              activeOpacity={canAct ? 0.74 : 1}
            >
              <View style={[styles.readinessIcon, { backgroundColor: hexToRgba(itemTone.accent, 0.16) }]}>
                <Ionicons name={item.icon as any} size={16} color={itemTone.accent} />
              </View>
              <View style={styles.readinessCopy}>
                <Text style={[styles.readinessLabel, { color: theme.text }]}>{item.label}</Text>
                <Text style={[styles.readinessDetail, { color: theme.faint }]} numberOfLines={2}>{item.detail}</Text>
              </View>
              {canAct ? (
                <Ionicons name="arrow-forward" size={15} color={itemTone.accent} />
              ) : (
                <Ionicons name="checkmark" size={15} color="#22c55e" />
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      <IconAction icon="navigate-outline" label={readiness.primaryAction.label} onPress={() => onAction(readiness.primaryAction.target)} accent={tone.accent} />
    </View>
  );
}

function OperatorActionPanel({
  readiness,
  theme,
  prefs,
  onAction,
}: {
  readiness: DashboardReadiness;
  theme: ThemeTokens;
  prefs: UiPrefs;
  onAction: (target: OperatorActionTarget) => void;
}) {
  const cardStyle = useThemedCard(theme, prefs);
  const operatorActions = buildOperatorActionQueue(readiness);

  return (
    <View style={[styles.glassCard, cardStyle]}>
      <View style={styles.compactHeader}>
        <SectionTitle eyebrow="RUNBOOK" title="Next Actions" theme={theme} />
        <Text style={[styles.countBadge, { color: theme.text, borderColor: theme.border }]}>{operatorActions.length}</Text>
      </View>
      <View style={styles.actionList}>
        {operatorActions.map((action) => {
          const color = toneToColor(action.tone);
          return (
            <TouchableOpacity
              key={`${action.label}-${action.target}`}
              style={[styles.actionRow, { borderColor: hexToRgba(color, 0.32), backgroundColor: hexToRgba(theme.cardAlt, 0.55) }]}
              onPress={() => onAction(action.target)}
              accessibilityRole="button"
              activeOpacity={0.74}
            >
              <View style={[styles.actionIcon, { backgroundColor: hexToRgba(color, 0.14) }]}>
                <Ionicons name={action.icon as any} size={16} color={color} />
              </View>
              <View style={styles.actionCopy}>
                <Text style={[styles.actionLabel, { color: theme.text }]}>{action.label}</Text>
                <Text style={[styles.actionDetail, { color: theme.faint }]} numberOfLines={2}>{action.detail}</Text>
              </View>
              <Ionicons name="arrow-forward" size={16} color={color} />
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

function Sidebar({
  theme,
  prefs,
  onNavigate,
  settingsDigest,
}: {
  theme: ThemeTokens;
  prefs: UiPrefs;
  onNavigate: (route: string) => void;
  settingsDigest: ReturnType<typeof summarizeSettings> | null;
}) {
  const accent = ACCENTS[prefs.accentKey].color;
  const guardColor = settingsDigest ? toneToColor(settingsDigest.primaryStatus.tone) : theme.faint;
  const [expanded, setExpanded] = useState(false);

  return (
    <View
      style={[
        styles.sidebarRail,
        expanded && styles.sidebarRailOpen,
        { borderRightColor: hexToRgba(theme.border, 0.84), backgroundColor: hexToRgba(theme.bg, 0.72) },
      ]}
      {...(Platform.OS === 'web'
        ? ({
            onMouseEnter: () => setExpanded(true),
            onMouseLeave: () => setExpanded(false),
          } as any)
        : {})}
    >
      <ScrollView style={styles.sidebarTopRail} showsVerticalScrollIndicator={false}>
        {ROUTE_GROUPS.map((route) => (
          <TouchableOpacity
            key={route.route + route.label}
            style={[styles.navRailItem, route.route === '/' && { backgroundColor: hexToRgba(accent, 0.16) }]}
            onPress={() => onNavigate(route.route)}
            accessibilityRole="button"
            activeOpacity={0.74}
          >
            {route.route === '/' ? <View style={[styles.navRailActiveBar, { backgroundColor: accent }]} /> : null}
            <Ionicons name={route.icon as any} size={17} color={route.route === '/' ? accent : theme.muted} style={styles.navRailIcon} />
            <Text
              numberOfLines={1}
              style={[
                styles.navRailLabel,
                { color: route.route === '/' ? accent : theme.muted, opacity: expanded ? 1 : 0 },
              ]}
            >
              {route.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <View style={[styles.sidebarFootRail, { borderTopColor: hexToRgba(theme.border, 0.84) }]}>
        <View style={styles.brokerRailStatus}>
          <StatusDot active={guardColor !== '#ef4444'} color={guardColor} animated={prefs.animatedDots} />
          <Text numberOfLines={1} style={[styles.brokerRailLabel, { color: theme.muted, opacity: expanded ? 1 : 0 }]}>
            {settingsDigest?.primaryStatus.title || 'Operator status'}
          </Text>
        </View>
      </View>
    </View>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isWide = width >= 1080;
  const [prefs, setPrefs] = useState<UiPrefs>(DEFAULT_UI_PREFS);
  const theme = THEMES[prefs.theme];
  const accent = ACCENTS[prefs.accentKey].color;
  const cardStyle = useThemedCard(theme, prefs);

  const [status, setStatus] = useState<BotStatus | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [brokers, setBrokers] = useState<any[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [patterns, setPatterns] = useState<AlertPatterns | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showBrokerPicker, setShowBrokerPicker] = useState(false);
  const [showCustomizer, setShowCustomizer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discordResult, setDiscordResult] = useState<string | null>(null);

  const [autoTrading, setAutoTrading] = useState(false);
  const [togglingAT, setTogglingAT] = useState(false);
  const [avgDown, setAvgDown] = useState(false);
  const [takeProfit, setTakeProfit] = useState(false);
  const [stopLoss, setStopLoss] = useState(false);
  const [trailingStop, setTrailingStop] = useState(false);
  const [autoShutdown, setAutoShutdown] = useState(false);
  const [shutdownSettings, setShutdownSettings] = useState<ShutdownSettings>({
    max_consecutive_losses: 3,
    max_daily_losses: 5,
    max_daily_loss_amount: 500,
    consecutive_losses: 0,
    daily_losses: 0,
    shutdown_triggered: false,
    shutdown_reason: '',
  });
  const [riskSettings, setRiskSettings] = useState({ take_profit_percentage: 50, stop_loss_percentage: 25 });
  const [trailingSettings, setTrailingSettings] = useState({ trailing_stop_percent: 10 });
  const [simMode, setSimMode] = useState(false);
  const [premiumBuffer, setPremiumBuffer] = useState(false);
  const [premiumBufferAmt, setPremiumBufferAmt] = useState(10);

  const [sampleAlert, setSampleAlert] = useState(DEFAULT_SAMPLE_ALERT);
  const [parsePreview, setParsePreview] = useState<ParsePreview | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [runningParse, setRunningParse] = useState(false);
  const [enginePreview, setEnginePreview] = useState<ReplayPreview | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [runningEnginePreview, setRunningEnginePreview] = useState(false);
  const testAlertInFlight = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    if (DEMO_MODE) {
      setStatus(DEMO_STATUS);
      setAlerts(DEMO_ALERTS);
      setTrades(DEMO_TRADES);
      setPositions(DEMO_POSITIONS);
      setPortfolio(DEMO_PORTFOLIO);
      setBrokers([
        { id: 'ibkr', name: 'IBKR', status: 'connected', account_id: 'DU123456' },
        { id: 'alpaca', name: 'Alpaca', status: 'connected', account_id: 'PAPER-123' },
        { id: 'tradier', name: 'Tradier', status: 'disconnected', account_id: '' },
      ]);
      setSettings(DEMO_SETTINGS);
      setPatterns(DEMO_PATTERNS);
      setAutoTrading(true);
      setSimMode(true);
      setAvgDown(true);
      setTakeProfit(false);
      setStopLoss(false);
      setRiskSettings({ take_profit_percentage: 50, stop_loss_percentage: 30 });
      setTrailingStop(true);
      setTrailingSettings({ trailing_stop_percent: 10 });
      setAutoShutdown(true);
      setShutdownSettings(DEMO_SHUTDOWN);
      setPremiumBuffer(false);
      setPremiumBufferAmt(10);
      setError(null);
      setLoading(false);
      setRefreshing(false);
      return;
    }

    try {
      setError(null);
      const [
        statusRes,
        alertsRes,
        tradesRes,
        positionsRes,
        brokersRes,
        portfolioRes,
        settingsRes,
        patternsRes,
        avgRes,
        riskRes,
        trailRes,
        shutRes,
        bufRes,
      ] = await Promise.all([
        api.get(`${BACKEND_URL}/api/status`),
        api.get(`${BACKEND_URL}/api/alerts?limit=6`),
        api.get(`${BACKEND_URL}/api/trades?limit=6`),
        api.get(`${BACKEND_URL}/api/positions`),
        api.get(`${BACKEND_URL}/api/brokers`),
        api.get(`${BACKEND_URL}/api/portfolio`),
        api.get(`${BACKEND_URL}/api/settings`),
        api.get(`${BACKEND_URL}/api/discord/alert-patterns`),
        api.get(`${BACKEND_URL}/api/averaging-down-settings`),
        api.get(`${BACKEND_URL}/api/risk-management-settings`),
        api.get(`${BACKEND_URL}/api/trailing-stop-settings`),
        api.get(`${BACKEND_URL}/api/auto-shutdown-settings`),
        api.get(`${BACKEND_URL}/api/premium-buffer-settings`),
      ]);
      const liveStatus = statusRes.data;
      const liveSettings = settingsRes.data || {};

      setStatus(liveStatus);
      setAlerts(alertsRes.data || []);
      setTrades(tradesRes.data || []);
      setPositions(positionsRes.data || []);
      setBrokers(brokersRes.data || []);
      setPortfolio(portfolioRes.data);
      setSettings(liveSettings);
      setPatterns(patternsRes.data || null);
      const runtimeState = normalizeDashboardRuntimeState({
        status: liveStatus,
        settings: liveSettings,
        averagingDown: avgRes.data,
        risk: riskRes.data,
        trailing: trailRes.data,
        shutdown: shutRes.data,
        premium: bufRes.data,
      });
      setAutoTrading(runtimeState.autoTrading);
      setSimMode(runtimeState.simMode);
      setAvgDown(runtimeState.avgDown);
      setTakeProfit(runtimeState.takeProfit);
      setStopLoss(runtimeState.stopLoss);
      setRiskSettings(runtimeState.riskSettings);
      setTrailingStop(runtimeState.trailingStop);
      setTrailingSettings(runtimeState.trailingSettings);
      setAutoShutdown(runtimeState.autoShutdown);
      setShutdownSettings(runtimeState.shutdownSettings);
      setPremiumBuffer(runtimeState.premiumBuffer);
      setPremiumBufferAmt(runtimeState.premiumBufferAmt);
    } catch (e: any) {
      console.error('dashboard fetch error', e);
      setError(e?.response?.data?.detail || e?.message || 'Failed to connect to backend');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const start = () => {
      if (!intervalRef.current) intervalRef.current = setInterval(fetchData, 5000);
    };
    const stop = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    start();
    const sub = AppState.addEventListener('change', (state: AppStateStatus) => {
      if (state === 'active') {
        fetchData();
        start();
      } else {
        stop();
      }
    });

    return () => {
      stop();
      sub.remove();
    };
  }, [fetchData]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const body = (globalThis as any).document?.body;
    if (!body) return;
    const notifyCustomizerChange = () => {
      globalThis.dispatchEvent?.(new Event('consolidation-customizer-change'));
    };

    if (showCustomizer) {
      body.setAttribute('data-consolidation-customizer', 'open');
    } else {
      body.removeAttribute('data-consolidation-customizer');
    }
    notifyCustomizerChange();

    return () => {
      body.removeAttribute('data-consolidation-customizer');
      notifyCustomizerChange();
    };
  }, [showCustomizer]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchData();
  }, [fetchData]);

  const toggle = (endpoint: string, setter: (value: boolean) => void, loadSetter?: (value: boolean) => void) => async () => {
    loadSetter?.(true);
    try {
      const res = await api.post(`${BACKEND_URL}/api/${endpoint}`);
      const toggledValue = readDashboardToggleValue(res.data);
      if (toggledValue !== null) setter(toggledValue);
      await fetchData();
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to toggle setting.');
    } finally {
      loadSetter?.(false);
    }
  };

  const sendTestAlert = useCallback(async () => {
    if (testAlertInFlight.current) return;
    testAlertInFlight.current = true;
    try {
      await api.post(`${BACKEND_URL}/api/test-alert`);
      await fetchData();
      Alert.alert('Test alert sent', 'A backend test alert was created.');
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to send test alert.');
    } finally {
      setTimeout(() => {
        testAlertInFlight.current = false;
      }, 3000);
    }
  }, [fetchData]);

  const resetLossCounters = useCallback(() => {
    Alert.alert('Reset Loss Counters', 'Clear consecutive and daily loss counts and re-enable auto-trading?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Reset',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.post(`${BACKEND_URL}/api/reset-loss-counters`);
            await fetchData();
          } catch (e: any) {
            Alert.alert('Error', e?.response?.data?.detail || 'Failed to reset loss counters.');
          }
        },
      },
    ]);
  }, [fetchData]);

  const runDiscordCommand = useCallback(async (command: 'start' | 'stop' | 'test-connection') => {
    setDiscordResult(null);
    try {
      const response = await api.post(`${BACKEND_URL}/api/discord/${command}`);
      setDiscordResult(response.data?.message || response.data?.status || 'Discord command completed.');
      await fetchData();
    } catch (e: any) {
      setDiscordResult(e?.response?.data?.detail || 'Discord command failed.');
    }
  }, [fetchData]);

  const runParsePreview = useCallback(async () => {
    setRunningParse(true);
    setParseError(null);
    try {
      if (DEMO_MODE) {
        setParsePreview({
          parsed: { ticker: 'SPY', strike: 738, option_type: 'PUT', expiration: '2026-06-18', entry_price: 0.6 },
          skip_reason: null,
          confidence: 'high',
          warnings: [],
          execution_preview: { would_insert_alert: true, would_request_trade: true },
        });
        return;
      }

      const response = await api.post(`${BACKEND_URL}/api/discord/parse-preview`, {
        raw_text: sampleAlert,
        source_key: firstConfiguredChannel(settings) || 'preview',
        source_name: 'dashboard-preview',
      });
      setParsePreview(response.data);
    } catch (e: any) {
      setParseError(e?.response?.data?.detail || 'Parser preview failed.');
    } finally {
      setRunningParse(false);
    }
  }, [sampleAlert, settings]);

  const runEnginePreview = useCallback(async () => {
    setRunningEnginePreview(true);
    setEngineError(null);
    try {
      if (DEMO_MODE) {
        setEnginePreview({
          execution_mode: 'preview_only_no_trades',
          event_count: 42,
          parsed_count: 31,
          would_request_trade_count: 18,
          drift_alert_count: 5,
          replay_url: 'http://127.0.0.1:9200/api/consolidation/replay/events',
          results: [],
        });
        return;
      }

      const response = await api.post(`${BACKEND_URL}/api/simulation-engine/replay-preview`, {
        channel_id: firstConfiguredChannel(settings),
        limit: 500,
      });
      setEnginePreview(response.data);
    } catch (e: any) {
      setEngineError(e?.response?.data?.detail || 'Simulation Engine replay preview failed.');
    } finally {
      setRunningEnginePreview(false);
    }
  }, [settings]);

  const switchBroker = useCallback(async (brokerId: string) => {
    try {
      await api.post(`${BACKEND_URL}/api/broker/switch/${brokerId}`);
      setShowBrokerPicker(false);
      await fetchData();
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to switch broker.');
    }
  }, [fetchData]);

  const alertDigest = useMemo(() => summarizeAlerts(alerts), [alerts]);
  const tradeDigest = useMemo(() => summarizeTrades(trades), [trades]);
  const positionDigest = useMemo(() => summarizePositions(positions), [positions]);
  const settingsDigest = useMemo(() => (settings ? summarizeSettings(settings, patterns) : null), [patterns, settings]);

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: theme.bg }]}>
        <BackgroundPattern theme={theme} prefs={prefs} />
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={accent} />
          <Text style={[styles.loadingText, { color: theme.muted }]}>Loading Consolidation...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error && !status) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: theme.bg }]}>
        <BackgroundPattern theme={theme} prefs={prefs} />
        <View style={[styles.centered, styles.errorState]}>
          <Ionicons name="cloud-offline-outline" size={50} color="#f87171" />
          <Text style={[styles.errorTitle, { color: '#f87171' }]}>Connection Error</Text>
          <Text style={[styles.errorText, { color: theme.muted }]}>{error}</Text>
          <Text style={[styles.errorHint, { color: theme.faint }]}>Backend URL: {BACKEND_URL}</Text>
          <IconAction icon="refresh" label="Retry" onPress={() => { setLoading(true); fetchData(); }} accent={accent} solid />
        </View>
      </SafeAreaView>
    );
  }

  const brokerId = String(status?.active_broker || settings?.active_broker || '').toLowerCase();
  const brokerColor = BROKER_COLORS[brokerId] || accent;
  const brokerName = BROKER_NAMES[brokerId] || safeUpper(status?.active_broker || settings?.active_broker);
  const channelCount = settings?.discord_channel_ids?.filter(Boolean).length || 0;
  const statusFlags = normalizeDashboardStatusFlags(status);
  const readiness = buildDashboardReadiness({
    status,
    simMode,
    autoShutdownEnabled: autoShutdown,
    shutdownTriggered: shutdownSettings.shutdown_triggered,
    takeProfitEnabled: takeProfit,
    stopLossEnabled: stopLoss,
    trailingStopEnabled: trailingStop,
    premiumBufferEnabled: premiumBuffer,
  });

  return (
    <SafeAreaView style={[styles.shellRoot, { backgroundColor: theme.bg }]}>
      <BackgroundPattern theme={theme} prefs={prefs} />
      <CustomizerModal visible={showCustomizer} prefs={prefs} onChange={setPrefs} onClose={() => setShowCustomizer(false)} />

      <ShellHeader
        status={status}
        autoTrading={autoTrading}
        trailingStop={trailingStop}
        stopLoss={stopLoss}
        theme={theme}
        prefs={prefs}
        onToggleAutoTrading={toggle('toggle-trading', setAutoTrading, setTogglingAT)}
        autoTradingLoading={togglingAT}
        onOpenNotifications={() => Alert.alert('Notifications', discordResult || alertDigest.primaryStatus.detail || 'No new notifications.')}
        onOpenCustomizer={() => setShowCustomizer(true)}
      />

      <View style={styles.bodyRow}>
        <Sidebar
          theme={theme}
          prefs={prefs}
          settingsDigest={settingsDigest}
          onNavigate={(route) => router.push(route as any)}
        />

      <ScrollView
        style={styles.canvas}
        contentContainerStyle={[styles.canvasContent, isWide && styles.canvasContentWide]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={accent} />}
        showsVerticalScrollIndicator={false}
      >
        {simMode && (
          <View style={[styles.noticeBanner, { borderColor: hexToRgba('#a78bfa', 0.42), backgroundColor: hexToRgba('#a78bfa', 0.12) }]}>
            <Ionicons name="flask" size={16} color="#a78bfa" />
            <Text style={[styles.noticeText, { color: '#c4b5fd' }]}>Simulation mode is active. No real broker orders should execute from alerts.</Text>
          </View>
        )}

        {shutdownSettings.shutdown_triggered && (
          <TouchableOpacity
            style={[styles.noticeBanner, { borderColor: hexToRgba('#f59e0b', 0.5), backgroundColor: hexToRgba('#f59e0b', 0.14) }]}
            onPress={resetLossCounters}
            accessibilityRole="button"
          >
            <Ionicons name="warning" size={16} color="#fbbf24" />
            <Text style={[styles.noticeText, { color: '#fde68a' }]}>Auto-shutdown triggered: {shutdownSettings.shutdown_reason || 'loss limit reached'}</Text>
            <Text style={[styles.noticeAction, { color: '#fbbf24' }]}>Reset</Text>
          </TouchableOpacity>
        )}

        <View style={styles.canvasGrid}>
          <View style={styles.mainColumn}>
            <View style={[styles.heroCard, styles.glassCard, cardStyle]}>
              <View style={styles.heroTop}>
                <SectionTitle eyebrow="SESSION P&L" title={portfolio ? formatPnL(portfolio.total_pnl) : '$0.00'} detail={portfolio ? `${portfolio.total_trades} trades loaded` : 'Portfolio summary unavailable'} theme={theme} />
                <View style={[styles.modeBadge, { borderColor: simMode ? '#a78bfa' : '#f59e0b', backgroundColor: hexToRgba(simMode ? '#a78bfa' : '#f59e0b', 0.12) }]}>
                  <Ionicons name={simMode ? 'flask-outline' : 'flash-outline'} size={15} color={simMode ? '#a78bfa' : '#f59e0b'} />
                  <Text style={[styles.modeBadgeText, { color: simMode ? '#c4b5fd' : '#fde68a' }]}>{simMode ? 'SIM' : 'LIVE'}</Text>
                </View>
              </View>
              <View style={styles.metricGrid}>
                <MetricTile label="Realized" value={portfolio ? formatPnL(portfolio.total_realized_pnl) : '$0.00'} color={getPnLColor(portfolio?.total_realized_pnl)} theme={theme} />
                <MetricTile label="Unrealized" value={portfolio ? formatPnL(portfolio.total_unrealized_pnl) : '$0.00'} color={getPnLColor(portfolio?.total_unrealized_pnl)} theme={theme} />
                <MetricTile label="Win Rate" value={`${portfolio?.win_rate?.toFixed(0) || 0}%`} detail={`${portfolio?.winning_trades || 0}W / ${portfolio?.losing_trades || 0}L`} theme={theme} />
                <MetricTile label="Open Positions" value={String(portfolio?.open_positions ?? positionDigest.open)} detail={positionDigest.topExposureTicker ? `Top: ${positionDigest.topExposureTicker}` : 'No top exposure'} theme={theme} />
              </View>
            </View>

            <View style={[styles.contentGrid, isWide && styles.contentGridWide]}>
              <View style={styles.contentPrimary}>
                <ReadinessCard readiness={readiness} theme={theme} prefs={prefs} onAction={(target) => router.push(target as any)} />
                <View style={[styles.glassCard, cardStyle]}>
                  <View style={styles.cardHeaderRow}>
                    <SectionTitle eyebrow="INGESTION" title="Discord Listener" detail={`${channelCount} configured channel${channelCount === 1 ? '' : 's'}`} theme={theme} />
                    <StatusDot active={statusFlags.discordConnected} color={statusFlags.discordConnected ? '#22c55e' : '#ef4444'} animated={prefs.animatedDots} />
                  </View>
                  <View style={styles.connectionGrid}>
                    <MetricTile label="Discord" value={statusFlags.discordConnected ? 'Live' : 'Offline'} detail={discordResult || 'Start, stop, or test the listener.'} color={statusFlags.discordConnected ? '#22c55e' : '#ef4444'} theme={theme} />
                    <MetricTile label="Channels" value={String(channelCount)} detail={firstConfiguredChannel(settings) || 'No channel configured'} theme={theme} />
                    <MetricTile label="Alerts" value={compactNumber(status?.alerts_processed || alertDigest.total)} detail={`${alertDigest.executionRate}% executed`} color={toneToColor(alertDigest.primaryStatus.tone)} theme={theme} />
                  </View>
                  <View style={styles.buttonRow}>
                    <IconAction icon="play" label="Start" onPress={() => runDiscordCommand('start')} accent="#22c55e" />
                    <IconAction icon="pulse-outline" label="Test" onPress={() => runDiscordCommand('test-connection')} accent={accent} />
                    <IconAction icon="flask-outline" label="Test Alert" onPress={sendTestAlert} accent={accent} />
                    <IconAction icon="stop" label="Stop" onPress={() => runDiscordCommand('stop')} accent="#fb7185" />
                    <IconAction icon="settings-outline" label="Config" onPress={() => router.push('/settings' as any)} accent={theme.muted} />
                  </View>
                </View>

                <View style={[styles.glassCard, cardStyle]}>
                  <View style={styles.cardHeaderRow}>
                    <SectionTitle eyebrow="PARSER LAB" title="Alert Preview" detail="Validate copied Discord alerts without placing trades." theme={theme} />
                    <IconAction icon="scan-outline" label={runningParse ? 'Parsing' : 'Preview'} onPress={runParsePreview} accent={accent} disabled={runningParse} solid />
                  </View>
                  <TextInput
                    value={sampleAlert}
                    onChangeText={setSampleAlert}
                    multiline
                    placeholder="Paste a Discord alert"
                    placeholderTextColor={theme.faint}
                    style={[
                      styles.alertInput,
                      { color: theme.text, borderColor: theme.border, backgroundColor: hexToRgba(theme.cardAlt, 0.62) },
                    ]}
                  />
                  {parseError ? <Text style={[styles.errorInline, { color: '#fb7185' }]}>{parseError}</Text> : null}
                  {parsePreview ? (
                    <View style={styles.previewGrid}>
                      <MetricTile label="Confidence" value={safeUpper(parsePreview.confidence, 'NONE')} theme={theme} />
                      <MetricTile label="Skip Reason" value={parsePreview.skip_reason || 'None'} color={parsePreview.skip_reason ? '#f59e0b' : '#22c55e'} theme={theme} />
                      <MetricTile label="Ticker" value={safeUpper(parsePreview.parsed?.ticker)} detail={parsePreview.parsed ? `${parsePreview.parsed.strike || '?'} ${parsePreview.parsed.option_type || ''}` : 'Unparsed'} theme={theme} />
                      <MetricTile label="Entry" value={parsePreview.parsed?.entry_price ? `$${Number(parsePreview.parsed.entry_price).toFixed(2)}` : '--'} detail={parsePreview.parsed?.expiration || 'No expiration'} theme={theme} />
                    </View>
                  ) : null}
                  {parsePreview?.warnings?.length ? (
                    <View style={styles.warningList}>
                      {parsePreview.warnings.slice(0, 3).map((warning, index) => (
                        <Text key={`${warningText(warning)}-${index}`} style={[styles.warningText, { color: '#fbbf24' }]}>{warningText(warning)}</Text>
                      ))}
                    </View>
                  ) : null}
                </View>

                <View style={[styles.glassCard, cardStyle]}>
                  <View style={styles.cardHeaderRow}>
                    <SectionTitle eyebrow="SIMULATION ENGINE" title="Replay Bridge" detail="Preview historical engine events. This does not execute trades." theme={theme} />
                    <IconAction icon="git-branch-outline" label={runningEnginePreview ? 'Checking' : 'Replay'} onPress={runEnginePreview} accent={accent} disabled={runningEnginePreview} solid />
                  </View>
                  {engineError ? <Text style={[styles.errorInline, { color: '#fb7185' }]}>{engineError}</Text> : null}
                  <View style={styles.previewGrid}>
                    <MetricTile label="Events" value={String(enginePreview?.event_count ?? 0)} theme={theme} />
                    <MetricTile label="Parsed" value={String(enginePreview?.parsed_count ?? 0)} theme={theme} />
                    <MetricTile label="Would Trade" value={String(enginePreview?.would_request_trade_count ?? 0)} color="#22c55e" theme={theme} />
                    <MetricTile label="Price Drift" value={String(enginePreview?.drift_alert_count ?? 0)} color={enginePreview?.drift_alert_count ? '#f59e0b' : theme.text} theme={theme} />
                  </View>
                  <Text style={[styles.smallMono, { color: theme.faint }]} numberOfLines={2}>
                    {enginePreview?.replay_url || 'Default: http://127.0.0.1:9200/api/consolidation/replay/events'}
                  </Text>
                </View>
              </View>

              <View style={styles.contentSecondary}>
                <OperatorActionPanel readiness={readiness} theme={theme} prefs={prefs} onAction={(target) => router.push(target as any)} />

                <View style={[styles.glassCard, cardStyle]}>
                  <View style={styles.cardHeaderRow}>
                    <SectionTitle eyebrow="EXECUTION PATH" title={brokerName} detail={statusFlags.brokerConnected ? 'Broker connected' : 'Broker offline'} theme={theme} />
                    <TouchableOpacity style={[styles.brokerChip, { borderColor: brokerColor }]} onPress={() => setShowBrokerPicker(!showBrokerPicker)} accessibilityRole="button">
                      <StatusDot active={statusFlags.brokerConnected} color={brokerColor} animated={prefs.animatedDots} />
                      <Ionicons name={showBrokerPicker ? 'chevron-up' : 'chevron-down'} size={14} color={brokerColor} />
                    </TouchableOpacity>
                  </View>
                  {showBrokerPicker ? (
                    <View style={styles.brokerPicker}>
                      {brokers.map((broker) => {
                        const id = String(broker.id || broker.name || '').toLowerCase();
                        const selected = brokerId === id;
                        return (
                          <TouchableOpacity
                            key={`${id}-${broker.name}`}
                            style={[
                              styles.brokerOption,
                              { borderColor: selected ? (BROKER_COLORS[id] || accent) : theme.border, backgroundColor: selected ? hexToRgba(BROKER_COLORS[id] || accent, 0.12) : 'transparent' },
                            ]}
                            onPress={() => switchBroker(id)}
                            accessibilityRole="button"
                          >
                            <Text style={[styles.brokerOptionText, { color: selected ? (BROKER_COLORS[id] || accent) : theme.muted }]}>{broker.name || safeUpper(id)}</Text>
                            {selected ? <Ionicons name="checkmark-circle" size={16} color="#22c55e" /> : null}
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  ) : null}
                  <ToggleLine label="Auto Trading" detail={autoTrading ? 'Parsed alerts can request execution.' : 'Alerts are monitor-only.'} enabled={autoTrading} onToggle={toggle('toggle-trading', setAutoTrading, setTogglingAT)} accent={accent} theme={theme} loading={togglingAT} />
                  <ToggleLine label="Premium Buffer" detail={premiumBuffer ? `${premiumBufferAmt} cent buffer enabled.` : 'Alert price buffer disabled.'} enabled={premiumBuffer} onToggle={async () => {
                    const next = !premiumBuffer;
                    setPremiumBuffer(next);
                    try {
                      await api.post(`${BACKEND_URL}/api/toggle-premium-buffer`);
                      await fetchData();
                    } catch {
                      setPremiumBuffer(!next);
                    }
                  }} accent={accent} theme={theme} />
                  {status?.last_alert_time ? <Text style={[styles.smallMono, { color: theme.faint }]}>Last alert: {formatDate(status.last_alert_time)}</Text> : null}
                </View>

                <View style={[styles.glassCard, cardStyle]}>
                  <SectionTitle eyebrow="RISK CONTROLS" title="Guardrails" detail={`${settingsDigest?.guardrailCoveragePercent ?? 0}% coverage in persisted settings`} theme={theme} />
                  <ToggleLine label="Averaging Down" detail="Add to losing positions." enabled={avgDown} onToggle={toggle('toggle-averaging-down', setAvgDown)} accent="#f59e0b" theme={theme} />
                  <ToggleLine label="Take Profit" detail={`Auto-close at +${riskSettings.take_profit_percentage}%`} enabled={takeProfit} onToggle={toggle('toggle-take-profit', setTakeProfit)} accent="#22c55e" theme={theme} />
                  <ToggleLine label="Stop Loss" detail={`Auto-close at -${riskSettings.stop_loss_percentage}%`} enabled={stopLoss} onToggle={toggle('toggle-stop-loss', setStopLoss)} accent="#ef4444" theme={theme} />
                  <ToggleLine label="Trailing Stop" detail={`Trails at ${trailingSettings.trailing_stop_percent}%`} enabled={trailingStop} onToggle={toggle('toggle-trailing-stop', setTrailingStop)} accent="#a78bfa" theme={theme} />
                  <ToggleLine label="Auto Shutdown" detail={`${shutdownSettings.consecutive_losses}/${shutdownSettings.max_consecutive_losses} consecutive, ${shutdownSettings.daily_losses}/${shutdownSettings.max_daily_losses} daily`} enabled={autoShutdown} onToggle={toggle('toggle-auto-shutdown', setAutoShutdown)} accent="#fb7185" theme={theme} />
                  <IconAction icon="refresh-circle-outline" label="Reset Loss Counters" onPress={resetLossCounters} accent="#fbbf24" />
                </View>

                <View style={[styles.glassCard, cardStyle]}>
                  <SectionTitle eyebrow="RECENT FLOW" title={alertDigest.primaryStatus.title} detail={alertDigest.primaryStatus.detail} theme={theme} />
                  <View style={styles.previewGrid}>
                    <MetricTile label="Alerts" value={String(alertDigest.total)} detail={`${alertDigest.executed} executed`} color={toneToColor(alertDigest.primaryStatus.tone)} theme={theme} />
                    <MetricTile label="Trades" value={String(tradeDigest.total)} detail={tradeDigest.primaryStatus.title} color={toneToColor(tradeDigest.primaryStatus.tone)} theme={theme} />
                    <MetricTile label="Positions" value={String(positionDigest.total)} detail={positionDigest.primaryStatus.title} color={toneToColor(positionDigest.primaryStatus.tone)} theme={theme} />
                  </View>
                  <View style={styles.feedList}>
                    {alerts.slice(0, 3).map((alert) => (
                      <View key={alert.id} style={[styles.feedRow, { borderColor: theme.border }]}>
                        <View>
                          <Text style={[styles.feedTitle, { color: theme.text }]}>${alert.ticker} {alert.strike} {alert.option_type}</Text>
                          <Text style={[styles.feedMeta, { color: theme.faint }]}>{alert.expiration} - {formatDate(alert.received_at)}</Text>
                        </View>
                        <Text style={[styles.feedPrice, { color: alert.trade_executed ? '#22c55e' : '#f59e0b' }]}>${Number(alert.entry_price || 0).toFixed(2)}</Text>
                      </View>
                    ))}
                    {alerts.length === 0 ? <Text style={[styles.emptyText, { color: theme.faint }]}>No alerts loaded yet.</Text> : null}
                  </View>
                </View>
              </View>
            </View>
          </View>
        </View>
      </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  shellRoot: {
    flex: 1,
    overflow: 'hidden',
  },
  bodyRow: {
    flex: 1,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  canvas: {
    flex: 1,
  },
  canvasContent: {
    padding: 14,
    paddingBottom: 34,
    gap: 10,
  },
  canvasContentWide: {
    padding: 14,
    paddingBottom: 34,
  },
  canvasGrid: {
    gap: 10,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 12,
    paddingBottom: 96,
    gap: 10,
  },
  scrollContentWide: {
    padding: 18,
    paddingBottom: 112,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    fontWeight: '700',
  },
  patternLayer: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.8,
  },
  triangleMark: {
    position: 'absolute',
    width: 0,
    height: 0,
    borderLeftWidth: 9,
    borderRightWidth: 9,
    borderBottomWidth: 16,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    transform: [{ rotate: '20deg' }],
  },
  hexMark: {
    position: 'absolute',
    width: 52,
    height: 52,
    borderWidth: 1,
    borderRadius: 14,
    transform: [{ rotate: '45deg' }],
  },
  circuitLineH: {
    position: 'absolute',
    width: '56%',
    height: 1,
  },
  circuitLineV: {
    position: 'absolute',
    width: 1,
    height: '32%',
  },
  circuitNode: {
    position: 'absolute',
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 1,
  },
  glassCard: {
    borderWidth: 1,
    borderRadius: 8,
    gap: 12,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: Platform.OS === 'web' ? 0.18 : 0.22,
    shadowRadius: 22,
    elevation: 2,
  },
  topbar: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 14,
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
  },
  topbarCopy: {
    flex: 1,
    minWidth: 280,
    gap: 3,
  },
  topbarActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'flex-end',
  },
  eyebrow: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2,
  },
  pageTitle: {
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: 0,
  },
  pageSub: {
    maxWidth: 780,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  sectionTitleBlock: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  sectionTitle: {
    fontSize: 19,
    fontWeight: '900',
    letterSpacing: 0,
  },
  sectionDetail: {
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
  },
  iconAction: {
    minHeight: 34,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    paddingHorizontal: 10,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  iconActionText: {
    fontSize: 12,
    fontWeight: '900',
  },
  disabled: {
    opacity: 0.56,
  },
  pipelineShellHeader: {
    height: 52,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    zIndex: 20,
    overflow: 'visible',
  },
  pipelineBrandSlot: {
    width: 58,
    height: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRightWidth: 1,
  },
  pipelineLogo: {
    width: 28,
    height: 28,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pipelineTrackBar: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 20,
    overflow: 'hidden',
  },
  pipelineHeaderActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingRight: 16,
  },
  discordPill: {
    minHeight: 28,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 11,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  discordPillText: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  autoTradePill: {
    minHeight: 30,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  autoTradeText: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  miniSwitchTrack: {
    width: 32,
    height: 18,
    borderRadius: 999,
    padding: 3,
  },
  miniSwitchThumb: {
    width: 12,
    height: 12,
    borderRadius: 999,
    backgroundColor: '#fff',
  },
  miniSwitchThumbOn: {
    transform: [{ translateX: 14 }],
  },
  headerIconButton: {
    width: 32,
    height: 32,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pipeline: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  pipelineStage: {
    minWidth: 170,
    flex: 1,
    borderWidth: 1,
    borderRadius: 8,
    padding: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  pipelineStageCompact: {
    minWidth: 104,
    flex: 0,
    flexShrink: 0,
    borderWidth: 0,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    gap: 6,
  },
  pipelineIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pipelineIconCompact: {
    width: 18,
    height: 18,
    borderRadius: 999,
  },
  pipelineCopy: {
    flex: 1,
    minWidth: 0,
  },
  pipelineCopyCompact: {
    flex: 0,
    width: 58,
    minWidth: 58,
  },
  pipelineLabel: {
    fontSize: 12,
    fontWeight: '900',
  },
  pipelineLabelCompact: {
    fontSize: 11,
    letterSpacing: 0.4,
  },
  pipelineDetail: {
    fontSize: 10,
    fontWeight: '700',
    marginTop: 2,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  noticeBanner: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  noticeText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '800',
  },
  noticeAction: {
    fontSize: 12,
    fontWeight: '900',
  },
  workspace: {
    gap: 10,
  },
  workspaceWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  sidebarRail: {
    width: 58,
    flexShrink: 0,
    borderRightWidth: 1,
    overflow: 'hidden',
    zIndex: 10,
  },
  sidebarRailOpen: {
    width: 210,
  },
  sidebarTopRail: {
    flex: 1,
    paddingTop: 10,
  },
  navRailItem: {
    minHeight: 40,
    paddingLeft: 17,
    paddingRight: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
    position: 'relative',
  },
  navRailActiveBar: {
    position: 'absolute',
    left: 0,
    top: 5,
    bottom: 5,
    width: 3,
    borderTopRightRadius: 3,
    borderBottomRightRadius: 3,
  },
  navRailIcon: {
    width: 20,
    textAlign: 'center',
  },
  navRailLabel: {
    minWidth: 0,
    fontSize: 13,
    fontWeight: '700',
  },
  sidebarFootRail: {
    borderTopWidth: 1,
    paddingVertical: 10,
  },
  brokerRailStatus: {
    minHeight: 34,
    paddingHorizontal: 17,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  brokerRailLabel: {
    flex: 1,
    minWidth: 0,
    fontSize: 12,
    fontWeight: '700',
  },
  sidebar: {
    gap: 12,
  },
  brandLockup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  brandMark: {
    width: 42,
    height: 42,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandName: {
    fontSize: 18,
    fontWeight: '900',
  },
  brandSub: {
    fontSize: 11,
    fontWeight: '700',
  },
  auditCard: {
    gap: 8,
  },
  auditEyebrow: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.8,
  },
  auditTitle: {
    fontSize: 16,
    fontWeight: '900',
  },
  auditDetail: {
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
  },
  auditStats: {
    flexDirection: 'row',
    gap: 8,
  },
  routeList: {
    maxHeight: 520,
  },
  routeButton: {
    minHeight: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'transparent',
    paddingHorizontal: 10,
    marginBottom: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  routeText: {
    fontSize: 12,
    fontWeight: '900',
  },
  mainColumn: {
    flex: 1,
    gap: 10,
    minWidth: 0,
  },
  heroCard: {
    gap: 14,
  },
  heroTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
    flexWrap: 'wrap',
  },
  modeBadge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  modeBadgeText: {
    fontSize: 11,
    fontWeight: '900',
  },
  metricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metricTile: {
    flex: 1,
    minWidth: 128,
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    gap: 4,
  },
  metricLabel: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
  },
  metricValue: {
    fontSize: 20,
    fontWeight: '900',
  },
  metricDetail: {
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  contentGrid: {
    gap: 10,
  },
  contentGridWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  contentPrimary: {
    flex: 1.55,
    gap: 10,
    minWidth: 0,
  },
  contentSecondary: {
    flex: 1,
    gap: 10,
    minWidth: 320,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
  },
  compactHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  scoreDial: {
    width: 66,
    height: 52,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'center',
    paddingTop: 10,
  },
  scoreDialValue: {
    fontSize: 24,
    fontWeight: '900',
  },
  scoreDialLabel: {
    fontSize: 11,
    fontWeight: '900',
  },
  readinessGrid: {
    gap: 8,
  },
  readinessItem: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  readinessIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  readinessCopy: {
    flex: 1,
    minWidth: 0,
  },
  readinessLabel: {
    fontSize: 13,
    fontWeight: '900',
  },
  readinessDetail: {
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '600',
    marginTop: 2,
  },
  countBadge: {
    minWidth: 28,
    textAlign: 'center',
    borderWidth: 1,
    borderRadius: 14,
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 5,
    fontSize: 11,
    fontWeight: '900',
  },
  actionList: {
    gap: 8,
  },
  actionRow: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  actionIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionCopy: {
    flex: 1,
    minWidth: 0,
  },
  actionLabel: {
    fontSize: 13,
    fontWeight: '900',
  },
  actionDetail: {
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '600',
    marginTop: 2,
  },
  connectionGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  buttonRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  alertInput: {
    minHeight: 116,
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    fontSize: 13,
    lineHeight: 19,
    fontFamily: Platform.select({ web: 'JetBrains Mono, monospace', default: 'monospace' }),
    fontWeight: '600',
    textAlignVertical: 'top',
  },
  previewGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  warningList: {
    gap: 6,
  },
  warningText: {
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  errorInline: {
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  },
  smallMono: {
    fontSize: 11,
    lineHeight: 16,
    fontFamily: Platform.select({ web: 'JetBrains Mono, monospace', default: 'monospace' }),
    fontWeight: '700',
  },
  brokerChip: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  brokerPicker: {
    gap: 6,
  },
  brokerOption: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brokerOptionText: {
    fontSize: 12,
    fontWeight: '900',
  },
  toggleLine: {
    borderTopWidth: 1,
    paddingTop: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  toggleLineCopy: {
    flex: 1,
    minWidth: 0,
  },
  toggleLineLabel: {
    fontSize: 13,
    fontWeight: '900',
  },
  toggleLineDetail: {
    marginTop: 2,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '600',
  },
  feedList: {
    gap: 7,
  },
  feedRow: {
    borderTopWidth: 1,
    paddingTop: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  feedTitle: {
    fontSize: 13,
    fontWeight: '900',
  },
  feedMeta: {
    fontSize: 10,
    marginTop: 3,
    fontWeight: '700',
  },
  feedPrice: {
    fontSize: 13,
    fontWeight: '900',
  },
  emptyText: {
    fontSize: 12,
    fontWeight: '700',
  },
  modalScrim: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 1000,
    elevation: 1000,
    alignItems: 'flex-end',
  },
  customizer: {
    position: 'relative',
    width: '100%',
    maxWidth: 430,
    height: '100%',
    borderLeftWidth: 1,
    padding: 18,
    gap: 16,
    overflow: 'hidden',
  },
  customizerHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  customizerTitle: {
    fontSize: 22,
    fontWeight: '900',
  },
  customizerSub: {
    marginTop: 4,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  closeButton: {
    width: 40,
    height: 40,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  prefEyebrow: {
    marginTop: 18,
    marginBottom: 10,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2.8,
  },
  swatchGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  swatch: {
    width: 42,
    height: 42,
    borderRadius: 11,
    borderColor: 'transparent',
  },
  segmentWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 9,
  },
  segmentChoice: {
    minHeight: 48,
    flex: 1,
    minWidth: 112,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  segmentChoiceText: {
    fontSize: 14,
    fontWeight: '900',
  },
  miniButton: {
    flex: 1,
    minWidth: 104,
    minHeight: 46,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  miniButtonText: {
    fontSize: 13,
    fontWeight: '900',
  },
  prefSlider: {
    marginTop: 14,
    gap: 8,
  },
  prefSliderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  prefLabel: {
    fontSize: 14,
    fontWeight: '800',
  },
  prefValue: {
    fontSize: 14,
    fontWeight: '900',
  },
  prefSliderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rangeInputWrap: {
    flex: 1,
    height: 32,
    justifyContent: 'center',
  },
  stepper: {
    width: 32,
    height: 32,
    borderWidth: 1,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  prefTrack: {
    flex: 1,
    height: 10,
    borderRadius: 999,
    overflow: 'hidden',
  },
  prefTrackFill: {
    height: '100%',
    borderRadius: 999,
  },
  errorState: {
    gap: 10,
  },
  errorTitle: {
    fontSize: 22,
    fontWeight: '900',
  },
  errorText: {
    maxWidth: 560,
    textAlign: 'center',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  errorHint: {
    fontFamily: Platform.select({ web: 'JetBrains Mono, monospace', default: 'monospace' }),
    fontSize: 11,
    fontWeight: '700',
  },
});
