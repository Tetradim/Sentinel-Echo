import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator, Switch, AppState, AppStateStatus,
  Alert,
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

// ── Demo Data ─────────────────────────────────────────────────────────────────
const DEMO_STATUS: BotStatus = {
  discord_connected: true,
  broker_connected: true,
  active_broker: 'IBKR',
  auto_trading_enabled: true,
  last_alert_time: new Date().toISOString(),
};

const DEMO_ALERTS: AlertItem[] = [
  { id: '1', ticker: 'AAPL', strike: 175, option_type: 'CALL', expiration: '2024-05-17', entry_price: 3.50, received_at: '2024-04-18T10:30:00Z', processed: true, trade_executed: true },
  { id: '2', ticker: 'TSLA', strike: 150, option_type: 'PUT', expiration: '2024-05-17', entry_price: 2.80, received_at: '2024-04-18T09:15:00Z', processed: true, trade_executed: true },
  { id: '3', ticker: 'NVDA', strike: 800, option_type: 'CALL', expiration: '2024-04-19', entry_price: 12.50, received_at: '2024-04-17T14:20:00Z', processed: true, trade_executed: false },
  { id: '4', ticker: 'MSFT', strike: 380, option_type: 'CALL', expiration: '2024-05-17', entry_price: 5.20, received_at: '2024-04-17T11:45:00Z', processed: false, trade_executed: false },
];

const DEMO_TRADES: Trade[] = [
  { id: '1', ticker: 'NVDA', strike: 800, option_type: 'CALL', expiration: '2024-04-19', entry_price: 12.50, exit_price: 14.20, current_price: null, quantity: 2, status: 'closed', executed_at: '2024-04-10T09:15:00Z', broker: 'IBKR', simulated: true, realized_pnl: 340, unrealized_pnl: null },
  { id: '2', ticker: 'AAPL', strike: 175, option_type: 'CALL', expiration: '2024-05-17', entry_price: 3.50, exit_price: null, current_price: 4.25, quantity: 5, status: 'open', executed_at: '2024-04-15T10:30:00Z', broker: 'IBKR', simulated: false, realized_pnl: null, unrealized_pnl: 375 },
  { id: '3', ticker: 'TSLA', strike: 150, option_type: 'PUT', expiration: '2024-05-17', entry_price: 2.80, exit_price: null, current_price: 2.10, quantity: 3, status: 'open', executed_at: '2024-04-16T14:20:00Z', broker: 'Alpaca', simulated: false, realized_pnl: null, unrealized_pnl: -210 },
];

const DEMO_PORTFOLIO: PortfolioSummary = {
  total_trades: 47,
  open_positions: 3,
  closed_positions: 44,
  total_realized_pnl: 2840,
  total_unrealized_pnl: 165,
  total_pnl: 3005,
  win_rate: 68.5,
  winning_trades: 30,
  losing_trades: 14,
  best_trade: 850,
  worst_trade: -320,
  average_pnl: 60.4,
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

// ── Types ─────────────────────────────────────────────────────────────────────
interface BotStatus {
  discord_connected: boolean; broker_connected: boolean;
  active_broker: string; auto_trading_enabled: boolean; last_alert_time: string | null;
}
interface AlertItem {
  id: string; ticker: string; strike: number; option_type: string;
  expiration: string; entry_price: number; received_at: string;
  processed: boolean; trade_executed: boolean;
}
interface Trade {
  id: string; ticker: string; strike: number; option_type: string;
  expiration: string; entry_price: number; exit_price: number | null;
  current_price: number | null; quantity: number; status: string;
  executed_at: string | null; broker: string; simulated: boolean;
  realized_pnl: number | null; unrealized_pnl: number | null;
}
interface PortfolioSummary {
  total_trades: number; open_positions: number; closed_positions: number;
  total_realized_pnl: number; total_unrealized_pnl: number; total_pnl: number;
  win_rate: number; winning_trades: number; losing_trades: number;
  best_trade: number; worst_trade: number; average_pnl: number;
}
interface ShutdownSettings {
  max_consecutive_losses: number; max_daily_losses: number; max_daily_loss_amount: number;
  consecutive_losses: number; daily_losses: number;
  shutdown_triggered: boolean; shutdown_reason: string;
}

// ── Small reusable pieces ─────────────────────────────────────────────────────
function SectionHeader({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return (
    <View style={s.sectionHeader}>
      <Text style={s.sectionTitle}>{title}</Text>
      {action && <TouchableOpacity onPress={onAction}><Text style={s.sectionAction}>{action}</Text></TouchableOpacity>}
    </View>
  );
}

function StatPill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={s.statPill}>
      <Text style={[s.statValue, color ? { color } : {}]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function ToggleRow({
  icon, label, sub, enabled, onToggle, loading, accent = '#0ea5e9'
}: {
  icon: string; label: string; sub: string; enabled: boolean;
  onToggle: () => void; loading?: boolean; accent?: string;
}) {
  return (
    <View style={[s.toggleRow, enabled && { borderLeftColor: accent, borderLeftWidth: 2 }]}>
      <View style={[s.toggleIcon, { backgroundColor: enabled ? accent + '22' : '#1a2535' }]}>
        <Ionicons name={icon as any} size={18} color={enabled ? accent : '#475569'} />
      </View>
      <View style={s.toggleText}>
        <Text style={s.toggleLabel}>{label}</Text>
        <Text style={s.toggleSub}>{sub}</Text>
      </View>
      {loading
        ? <ActivityIndicator size="small" color={accent} />
        : <Switch value={enabled} onValueChange={onToggle}
            trackColor={{ false: '#1e2d3d', true: accent }}
            thumbColor="#fff" style={{ transform: [{ scaleX: 0.85 }, { scaleY: 0.85 }] }} />
      }
    </View>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
const READINESS_TONE: Record<ReadinessTone, { accent: string; icon: string }> = {
  live: { accent: '#22c55e', icon: 'checkmark-circle' },
  attention: { accent: '#f59e0b', icon: 'alert-circle' },
  blocked: { accent: '#ef4444', icon: 'warning' },
};

function ReadinessCard({
  readiness,
  onAction,
}: {
  readiness: DashboardReadiness;
  onAction: (target: ReadinessActionTarget) => void;
}) {
  const tone = READINESS_TONE[readiness.tone];

  return (
    <View style={[s.readinessCard, { borderColor: tone.accent + '55' }]}>
      <View style={s.readinessTop}>
        <View style={s.readinessTitleBlock}>
          <Text style={s.readinessEyebrow}>OPERATOR READINESS</Text>
          <View style={s.readinessTitleRow}>
            <Ionicons name={tone.icon as any} size={19} color={tone.accent} />
            <Text style={s.readinessTitle}>{readiness.title}</Text>
          </View>
        </View>
        <View style={[s.readinessScore, { backgroundColor: tone.accent + '18' }]}>
          <Text style={[s.readinessScoreNum, { color: tone.accent }]}>{readiness.score}</Text>
          <Text style={s.readinessScorePct}>%</Text>
        </View>
      </View>

      <Text style={s.readinessSummary}>{readiness.summary}</Text>

      <View style={s.readinessItems}>
        {readiness.items.map((item) => {
          const itemTone = READINESS_TONE[item.state === 'ready' ? 'live' : item.state];
          const canAct = Boolean(item.actionTarget && item.state !== 'ready');

          return (
            <TouchableOpacity
              key={item.id}
              style={s.readinessItem}
              onPress={() => item.actionTarget && onAction(item.actionTarget)}
              activeOpacity={canAct ? 0.75 : 1}
              disabled={!canAct}
            >
              <View style={[s.readinessItemIcon, { backgroundColor: itemTone.accent + '18' }]}>
                <Ionicons name={item.icon as any} size={15} color={itemTone.accent} />
              </View>
              <View style={s.readinessItemText}>
                <Text style={s.readinessItemLabel}>{item.label}</Text>
                <Text style={s.readinessItemDetail}>{item.detail}</Text>
              </View>
              {canAct ? (
                <Text style={[s.readinessItemAction, { color: itemTone.accent }]}>{item.actionLabel}</Text>
              ) : (
                <Ionicons name="checkmark" size={16} color="#22c55e" />
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      <TouchableOpacity
        style={[s.readinessPrimaryAction, { borderColor: tone.accent + '66' }]}
        onPress={() => onAction(readiness.primaryAction.target)}
      >
        <Text style={[s.readinessPrimaryText, { color: tone.accent }]}>{readiness.primaryAction.label}</Text>
        <Ionicons name="arrow-forward" size={15} color={tone.accent} />
      </TouchableOpacity>
    </View>
  );
}

export default function Dashboard() {
  const router = useRouter();

  const [status, setStatus]         = useState<BotStatus | null>(null);
  const [alerts, setAlerts]         = useState<AlertItem[]>([]);
  const [trades, setTrades]         = useState<Trade[]>([]);
  const [portfolio, setPortfolio]   = useState<PortfolioSummary | null>(null);
  const [brokers, setBrokers]       = useState<any[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showBrokerPicker, setShowBrokerPicker] = useState(false);
  const [error, setError]           = useState<string | null>(null);

  // Toggles
  const [autoTrading, setAutoTrading]       = useState(false);
  const [togglingAT, setTogglingAT]         = useState(false);
  const [avgDown, setAvgDown]               = useState(false);
  const [takeProfit, setTakeProfit]         = useState(false);
  const [stopLoss, setStopLoss]             = useState(false);
  const [trailingStop, setTrailingStop]     = useState(false);
  const [autoShutdown, setAutoShutdown]     = useState(false);
  const [shutdownSettings, setShutdownSettings] = useState<ShutdownSettings>({
    max_consecutive_losses: 3, max_daily_losses: 5, max_daily_loss_amount: 500,
    consecutive_losses: 0, daily_losses: 0, shutdown_triggered: false, shutdown_reason: '',
  });
  const [riskSettings, setRiskSettings]     = useState({ take_profit_percentage: 50, stop_loss_percentage: 25 });
  const [trailingSettings, setTrailingSettings] = useState({ trailing_stop_percent: 10 });
  const [simMode, setSimMode]               = useState(false);
  const [premiumBuffer, setPremiumBuffer]   = useState(false);
  const [premiumBufferAmt, setPremiumBufferAmt] = useState(10);

  const fetchData = useCallback(async () => {
    if (DEMO_MODE) {
      // Load demo data
      setStatus(DEMO_STATUS);
      setAlerts(DEMO_ALERTS);
      setTrades(DEMO_TRADES);
      setPortfolio(DEMO_PORTFOLIO);
      setBrokers([
        { id: '1', name: 'IBKR', status: 'connected', account_id: 'DU123456' },
        { id: '2', name: 'Alpaca', status: 'connected', account_id: 'PAPER-123' },
        { id: '3', name: 'Tradier', status: 'disconnected', account_id: '' },
      ]);
      setAutoTrading(true);
      setSimMode(true);
      setAvgDown(true);
      setTakeProfit(true);
      setStopLoss(true);
      setRiskSettings({ take_profit_percentage: 50, stop_loss_percentage: 30 });
      setTrailingStop(true);
      setTrailingSettings({ trailing_stop_percent: 25 });
      setAutoShutdown(true);
      setShutdownSettings(DEMO_SHUTDOWN);
      setPremiumBuffer(true);
      setPremiumBufferAmt(10);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    try {
      setError(null);
      const [statusRes, alertsRes, tradesRes, brokersRes, portfolioRes,
             avgRes, riskRes, trailRes, shutRes, bufRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/status`),
        api.get(`${BACKEND_URL}/api/alerts?limit=4`),
        api.get(`${BACKEND_URL}/api/trades?limit=4`),
        api.get(`${BACKEND_URL}/api/brokers`),
        api.get(`${BACKEND_URL}/api/portfolio`),
        api.get(`${BACKEND_URL}/api/averaging-down-settings`),
        api.get(`${BACKEND_URL}/api/risk-management-settings`),
        api.get(`${BACKEND_URL}/api/trailing-stop-settings`),
        api.get(`${BACKEND_URL}/api/auto-shutdown-settings`),
        api.get(`${BACKEND_URL}/api/premium-buffer-settings`),
      ]);
      setStatus(statusRes.data);
      setSimMode(statusRes.data.simulation_mode ?? false);
      setAlerts(alertsRes.data);
      setTrades(tradesRes.data);
      setBrokers(brokersRes.data);
      setPortfolio(portfolioRes.data);
      setAutoTrading(statusRes.data.auto_trading_enabled);
      setAvgDown(avgRes.data.averaging_down_enabled);
      setTakeProfit(riskRes.data.take_profit_enabled);
      setStopLoss(riskRes.data.stop_loss_enabled);
      setRiskSettings({ take_profit_percentage: riskRes.data.take_profit_percentage, stop_loss_percentage: riskRes.data.stop_loss_percentage });
      setTrailingStop(trailRes.data.trailing_stop_enabled);
      setTrailingSettings({ trailing_stop_percent: trailRes.data.trailing_stop_percent });
      setAutoShutdown(shutRes.data.auto_shutdown_enabled);
      setShutdownSettings({
        max_consecutive_losses: shutRes.data.max_consecutive_losses,
        max_daily_losses: shutRes.data.max_daily_losses,
        max_daily_loss_amount: shutRes.data.max_daily_loss_amount,
        consecutive_losses: shutRes.data.consecutive_losses,
        daily_losses: shutRes.data.daily_losses,
        shutdown_triggered: shutRes.data.shutdown_triggered,
        shutdown_reason: shutRes.data.shutdown_reason,
      });
      setPremiumBuffer(bufRes.data.premium_buffer_enabled);
      setPremiumBufferAmt(bufRes.data.premium_buffer_amount);
      setSimMode(statusRes.data.simulation_mode ?? false);
    } catch (e: any) { 
      console.error('fetch error', e);
      setError(e?.message || 'Failed to connect to backend');
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = { current: null as ReturnType<typeof setInterval> | null };
    const start = () => { if (!interval.current) interval.current = setInterval(fetchData, 5000); };
    const stop  = () => { if (interval.current) { clearInterval(interval.current); interval.current = null; } };
    start();
    const sub = AppState.addEventListener('change', (s: AppStateStatus) => {
      if (s === 'active') {
        fetchData();
        start();
      } else {
        stop();
      }
    });
    return () => { stop(); sub.remove(); };
  }, [fetchData]);

  const onRefresh = useCallback(() => { setRefreshing(true); fetchData(); }, [fetchData]);

  const toggle = (endpoint: string, setter: (v: boolean) => void, current: boolean, loadSetter?: (v: boolean) => void) => async () => {
    loadSetter?.(true);
    try {
      const res = await api.post(`${BACKEND_URL}/api/${endpoint}`);
      const key = Object.keys(res.data).find(k => typeof res.data[k] === 'boolean');
      if (key) setter(res.data[key]);
    } catch { Alert.alert('Error', `Failed to toggle.`); }
    finally { loadSetter?.(false); }
  };

  const testAlertInFlight = useRef(false);
  const sendTestAlert = async () => {
    if (testAlertInFlight.current) return;
    testAlertInFlight.current = true;
    try { await api.post(`${BACKEND_URL}/api/test-alert`); fetchData(); }
    catch { Alert.alert('Error', 'Failed to send test alert.'); }
    finally { setTimeout(() => { testAlertInFlight.current = false; }, 3000); }
  };

  const resetLossCounters = () => Alert.alert(
    'Reset Loss Counters',
    'Clear consecutive and daily loss counts and re-enable auto-trading?',
    [{ text: 'Cancel', style: 'cancel' }, {
      text: 'Reset', style: 'destructive', onPress: async () => {
        try { await api.post(`${BACKEND_URL}/api/reset-loss-counters`); fetchData(); }
        catch { Alert.alert('Error', 'Failed to reset.'); }
      }
    }]
  );

  if (loading) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.centered}>
          <ActivityIndicator size="large" color="#0ea5e9" />
          <Text style={s.loadingText}>Loading...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error && !status) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.centered}>
          <Ionicons name="cloud-offline" size={48} color="#f87171" />
          <Text style={s.errorTitle}>Connection Error</Text>
          <Text style={s.errorText}>{error}</Text>
          <Text style={s.errorHint}>Backend URL: {BACKEND_URL}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={() => { setLoading(true); fetchData(); }}>
            <Ionicons name="refresh" size={18} color="#fff" />
            <Text style={s.retryBtnText}>Retry</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const brokerColor = BROKER_COLORS[status?.active_broker || ''] || '#0ea5e9';
  const brokerName  = BROKER_NAMES[status?.active_broker || ''] || 'None';
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
    <SafeAreaView style={s.container}>
      <ScrollView
        style={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0ea5e9" />}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Header ── */}
        <View style={s.header}>
          <View>
            <Text style={s.headerEyebrow}>TRADING TERMINAL</Text>
            <Text style={s.headerTitle}>Dashboard</Text>
          </View>
          <View style={s.headerRight}>
            <TouchableOpacity style={s.iconBtn} onPress={sendTestAlert}>
              <Ionicons name="flask-outline" size={20} color="#64748b" />
            </TouchableOpacity>
            <TouchableOpacity style={s.iconBtn} onPress={() => router.push('/profiles')}>
              <Ionicons name="people-outline" size={20} color="#64748b" />
            </TouchableOpacity>
          </View>
        </View>

        {/* ── Sim Mode Banner ── */}
        {simMode && (
          <View style={s.simBanner}>
            <Ionicons name="flask" size={15} color="#a78bfa" />
            <Text style={s.simBannerText}>SIMULATION MODE — No real trades will execute</Text>
          </View>
        )}

        {/* ── Shutdown Banner ── */}
        {shutdownSettings.shutdown_triggered && (
          <TouchableOpacity style={s.shutdownBanner} onPress={resetLossCounters}>
            <Ionicons name="warning" size={18} color="#fbbf24" />
            <Text style={s.shutdownText}>Auto-shutdown triggered: {shutdownSettings.shutdown_reason || 'Loss limit reached'}</Text>
            <Text style={s.shutdownReset}>Reset →</Text>
          </TouchableOpacity>
        )}

        {/* ── P&L Card ── */}
        {portfolio && (
          <View style={s.pnlCard}>
            <View style={s.pnlTop}>
              <View>
                <Text style={s.pnlEyebrow}>TOTAL P&L</Text>
                <Text style={[s.pnlBig, { color: getPnLColor(portfolio.total_pnl) }]}>
                  {formatPnL(portfolio.total_pnl)}
                </Text>
              </View>
              <View style={s.pnlWinRate}>
                <Text style={s.pnlWinRateNum}>{portfolio.win_rate.toFixed(0)}%</Text>
                <Text style={s.pnlWinRateLabel}>Win Rate</Text>
              </View>
            </View>
            <View style={s.pnlDivider} />
            <View style={s.pnlStats}>
              <StatPill label="Realized"   value={formatPnL(portfolio.total_realized_pnl)}   color={getPnLColor(portfolio.total_realized_pnl)} />
              <View style={s.pnlStatDiv} />
              <StatPill label="Unrealized" value={formatPnL(portfolio.total_unrealized_pnl)} color={getPnLColor(portfolio.total_unrealized_pnl)} />
              <View style={s.pnlStatDiv} />
              <StatPill label="Open"     value={String(portfolio.open_positions)} />
              <View style={s.pnlStatDiv} />
              <StatPill label="Closed"   value={String(portfolio.closed_positions)} />
            </View>
            <View style={s.pnlWL}>
              <View style={s.pnlWLBadge}>
                <Text style={s.pnlWLNum}>{portfolio.winning_trades}</Text>
                <Text style={[s.pnlWLLabel, { color: '#22c55e' }]}>W</Text>
              </View>
              <View style={[s.pnlWLBadge, { backgroundColor: '#2d1515' }]}>
                <Text style={s.pnlWLNum}>{portfolio.losing_trades}</Text>
                <Text style={[s.pnlWLLabel, { color: '#ef4444' }]}>L</Text>
              </View>
              <View style={s.pnlBestWorst}>
                <Text style={s.pnlBWLabel}>Best: <Text style={{ color: '#22c55e' }}>{formatPnL(portfolio.best_trade)}</Text></Text>
                <Text style={s.pnlBWLabel}>Worst: <Text style={{ color: '#ef4444' }}>{formatPnL(portfolio.worst_trade)}</Text></Text>
              </View>
            </View>
          </View>
        )}

        {/* ── Connection Status ── */}
        <View style={s.connRow}>
          <View style={s.connCard}>
            <View style={[s.connDot, { backgroundColor: status?.discord_connected ? '#22c55e' : '#ef4444' }]} />
            <Ionicons name="logo-discord" size={16} color="#7c8fdb" style={{ marginRight: 6 }} />
            <Text style={s.connLabel}>Discord</Text>
            <Text style={[s.connStatus, { color: status?.discord_connected ? '#22c55e' : '#64748b' }]}>
              {status?.discord_connected ? 'Live' : 'Off'}
            </Text>
          </View>
          <TouchableOpacity
            style={[s.connCard, { borderColor: brokerColor + '44' }]}
            onPress={() => setShowBrokerPicker(!showBrokerPicker)}
          >
            <View style={[s.connDot, { backgroundColor: status?.broker_connected ? '#22c55e' : '#ef4444' }]} />
            <Text style={[s.connLabel, { color: brokerColor }]}>{brokerName}</Text>
            <Text style={[s.connStatus, { color: status?.broker_connected ? '#22c55e' : '#64748b' }]}>
              {status?.broker_connected ? 'Live' : 'Off'}
            </Text>
            <Ionicons name={showBrokerPicker ? 'chevron-up' : 'chevron-down'} size={14} color="#475569" style={{ marginLeft: 4 }} />
          </TouchableOpacity>
        </View>

        {/* ── Broker Picker ── */}
        {showBrokerPicker && (
          <View style={s.brokerPicker}>
            {brokers.map(b => (
              <TouchableOpacity
                key={b.id}
                style={[s.brokerOpt, status?.active_broker === b.id && s.brokerOptActive]}
                onPress={async () => {
                  try { await api.post(`${BACKEND_URL}/api/broker/switch/${b.id}`); setShowBrokerPicker(false); fetchData(); }
                  catch { Alert.alert('Error', 'Failed to switch broker.'); }
                }}
              >
                <View style={[s.brokerOptDot, { backgroundColor: BROKER_COLORS[b.id] || '#64748b' }]} />
                <Text style={s.brokerOptName}>{b.name}</Text>
                {status?.active_broker === b.id && <Ionicons name="checkmark-circle" size={18} color="#22c55e" />}
              </TouchableOpacity>
            ))}
            <TouchableOpacity style={s.brokerConfigBtn} onPress={() => { setShowBrokerPicker(false); router.push('/broker-config'); }}>
              <Ionicons name="key-outline" size={15} color="#0ea5e9" />
              <Text style={s.brokerConfigText}>Configure API Keys</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── Auto Trading ── */}
        <ReadinessCard
          readiness={readiness}
          onAction={(target) => router.push(target as any)}
        />

        <View style={s.card}>
          <View style={s.autoTradingHeader}>
            <View style={[s.atIndicator, { backgroundColor: autoTrading ? '#22c55e' : '#374151' }]} />
            <View style={s.atText}>
              <Text style={s.cardTitle}>Auto Trading</Text>
              <Text style={s.cardSub}>{autoTrading ? 'Executing trades automatically' : 'Trading paused — manual only'}</Text>
            </View>
            {togglingAT
              ? <ActivityIndicator size="small" color="#22c55e" />
              : <Switch value={autoTrading} onValueChange={toggle('toggle-trading', setAutoTrading, autoTrading, setTogglingAT)}
                  trackColor={{ false: '#1e2d3d', true: '#22c55e' }} thumbColor="#fff"
                />
            }
          </View>
          {status?.last_alert_time && (
            <Text style={s.lastAlert}>Last alert: {formatDate(status.last_alert_time)}</Text>
          )}
          {autoTrading && (
            <View style={s.premiumBufferRow}>
              <View style={s.premiumBufferLeft}>
                <Ionicons name="shield-half" size={14} color={premiumBuffer ? '#0ea5e9' : '#334155'} />
                <Text style={[s.premiumBufferLabel, premiumBuffer && { color: '#0ea5e9' }]}>Premium Buffer</Text>
                {premiumBuffer && <Text style={s.premiumBufferAmt}>{premiumBufferAmt}¢</Text>}
              </View>
              <Switch
                value={premiumBuffer}
                onValueChange={async (v) => {
                  setPremiumBuffer(v);
                  try { await api.post(`${BACKEND_URL}/api/toggle-premium-buffer`); }
                  catch { setPremiumBuffer(!v); }
                }}
                trackColor={{ false: '#1e2d3d', true: '#0ea5e9' }}
                thumbColor="#fff"
                style={{ transform: [{ scaleX: 0.75 }, { scaleY: 0.75 }] }}
              />
            </View>
          )}
        </View>

        {/* ── Risk Controls ── */}
        <View style={s.card}>
          <Text style={s.cardGroupTitle}>RISK CONTROLS</Text>
          <ToggleRow icon="trending-down-outline"  label="Averaging Down"  sub="Add to losing positions"     enabled={avgDown}     onToggle={toggle('toggle-averaging-down', setAvgDown, avgDown)}           accent="#f59e0b" />
          <View style={s.toggleDivider} />
          <ToggleRow icon="arrow-up-circle-outline" label="Take Profit"    sub={`Auto-close at +${riskSettings.take_profit_percentage}%`} enabled={takeProfit}  onToggle={toggle('toggle-take-profit', setTakeProfit, takeProfit)}     accent="#22c55e" />
          <View style={s.toggleDivider} />
          <ToggleRow icon="shield-outline"          label="Stop Loss"      sub={`Auto-close at -${riskSettings.stop_loss_percentage}%`}   enabled={stopLoss}    onToggle={toggle('toggle-stop-loss', setStopLoss, stopLoss)}           accent="#ef4444" />
          <View style={s.toggleDivider} />
          <ToggleRow icon="trending-up-outline"     label="Trailing Stop"  sub={`Trails at ${trailingSettings.trailing_stop_percent}%`}    enabled={trailingStop} onToggle={toggle('toggle-trailing-stop', setTrailingStop, trailingStop)} accent="#a78bfa" />
        </View>

        {/* ── Auto Shutdown ── */}
        <View style={s.card}>
          <Text style={s.cardGroupTitle}>AUTO SHUTDOWN</Text>
          <ToggleRow icon="power-outline" label="Auto Shutdown" sub="Stop trading on loss limits" enabled={autoShutdown} onToggle={toggle('toggle-auto-shutdown', setAutoShutdown, autoShutdown)} accent="#f87171" />
          {autoShutdown && (
            <View style={s.shutdownStats}>
              <View style={s.shutdownStat}>
                <Text style={s.shutdownStatNum}>{shutdownSettings.consecutive_losses}</Text>
                <Text style={s.shutdownStatLabel}>/ {shutdownSettings.max_consecutive_losses} consec.</Text>
              </View>
              <View style={s.shutdownStat}>
                <Text style={s.shutdownStatNum}>{shutdownSettings.daily_losses}</Text>
                <Text style={s.shutdownStatLabel}>/ {shutdownSettings.max_daily_losses} daily</Text>
              </View>
              {(shutdownSettings.consecutive_losses > 0 || shutdownSettings.daily_losses > 0) && (
                <TouchableOpacity style={s.resetBtn} onPress={resetLossCounters}>
                  <Text style={s.resetBtnText}>Reset</Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>

        {/* ── Recent Alerts ── */}
        <View style={s.section}>
          <SectionHeader title="Recent Alerts" action="All →" onAction={() => router.push('/alerts')} />
          {alerts.length === 0 ? (
            <View style={s.emptyBox}>
              <Ionicons name="notifications-off-outline" size={32} color="#1e2d3d" />
              <Text style={s.emptyText}>No alerts yet</Text>
            </View>
          ) : alerts.map(a => (
            <View key={a.id} style={s.alertRow}>
              <View style={s.alertLeft}>
                <Text style={s.alertTicker}>${a.ticker}</Text>
                <Text style={s.alertMeta}>${a.strike} {a.option_type} · {a.expiration}</Text>
              </View>
              <View style={s.alertRight}>
                <View style={[s.badge, { backgroundColor: a.trade_executed ? '#14532d' : '#422006' }]}>
                  <Text style={[s.badgeText, { color: a.trade_executed ? '#4ade80' : '#fb923c' }]}>
                    {a.trade_executed ? 'Executed' : 'Pending'}
                  </Text>
                </View>
                <Text style={s.alertPrice}>${a.entry_price.toFixed(2)}</Text>
                <Text style={s.alertTime}>{formatDate(a.received_at)}</Text>
              </View>
            </View>
          ))}
        </View>

        {/* ── Recent Trades ── */}
        <View style={[s.section, { marginBottom: 16 }]}>
          <SectionHeader title="Recent Trades" action="All →" onAction={() => router.push('/trades')} />
          {trades.length === 0 ? (
            <View style={s.emptyBox}>
              <Ionicons name="receipt-outline" size={32} color="#1e2d3d" />
              <Text style={s.emptyText}>No trades yet</Text>
            </View>
          ) : trades.map(t => {
            const pnl = t.realized_pnl ?? t.unrealized_pnl;
            return (
              <View key={t.id} style={s.tradeRow}>
                <View style={s.tradeLeft}>
                  <Text style={s.tradeTicker}>${t.ticker}</Text>
                  <Text style={s.tradeMeta}>{t.quantity}× ${t.strike} {t.option_type}</Text>
                  <Text style={s.tradeTime}>{formatDate(t.executed_at)}</Text>
                </View>
                <View style={s.tradeRight}>
                  <View style={[s.badge, {
                    backgroundColor: t.simulated ? '#2d1f5e' :
                      t.status === 'executed' ? '#14532d' :
                      t.status === 'closed'   ? '#0c2740' : '#1e2d3d'
                  }]}>
                    <Text style={[s.badgeText, {
                      color: t.simulated ? '#a78bfa' :
                        t.status === 'executed' ? '#4ade80' :
                        t.status === 'closed'   ? '#38bdf8' : '#94a3b8'
                    }]}>
                      {t.simulated ? 'SIM' : t.status.toUpperCase()}
                    </Text>
                  </View>
                  {pnl !== null && (
                    <Text style={[s.tradePnl, { color: getPnLColor(pnl) }]}>{formatPnL(pnl)}</Text>
                  )}
                  <Text style={s.tradeEntry}>${t.entry_price.toFixed(2)}</Text>
                </View>
              </View>
            );
          })}
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#080f1a' },
  centered:       { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loadingText:    { color: '#64748b', marginTop: 12, fontSize: 14 },
  scroll:         { flex: 1 },

  header:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 },
  headerEyebrow:  { fontSize: 10, color: '#0ea5e9', fontWeight: '700', letterSpacing: 2, marginBottom: 2 },
  headerTitle:    { fontSize: 26, fontWeight: '800', color: '#e2e8f0' },
  headerRight:    { flexDirection: 'row', gap: 8 },
  iconBtn:        { width: 36, height: 36, borderRadius: 10, backgroundColor: '#0d1826', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#1e2d3d' },

  shutdownBanner: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#2d1f00', borderRadius: 10, marginHorizontal: 16, marginBottom: 10, padding: 12, gap: 8, borderWidth: 1, borderColor: '#92400e' },
  shutdownText:   { flex: 1, color: '#fbbf24', fontSize: 12 },
  shutdownReset:  { color: '#f59e0b', fontSize: 12, fontWeight: '700' },

  pnlCard:        { backgroundColor: '#0d1826', borderRadius: 16, marginHorizontal: 16, marginBottom: 12, padding: 18, borderWidth: 1, borderColor: '#1e2d3d' },
  pnlTop:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 },
  pnlEyebrow:     { fontSize: 10, color: '#475569', letterSpacing: 2, fontWeight: '700', marginBottom: 4 },
  pnlBig:         { fontSize: 38, fontWeight: '800' },
  pnlWinRate:     { alignItems: 'flex-end' },
  pnlWinRateNum:  { fontSize: 24, fontWeight: '700', color: '#e2e8f0' },
  pnlWinRateLabel:{ fontSize: 11, color: '#475569', marginTop: 2 },
  pnlDivider:     { height: 1, backgroundColor: '#1e2d3d', marginBottom: 14 },
  pnlStats:       { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  pnlStatDiv:     { width: 1, height: 28, backgroundColor: '#1e2d3d', marginHorizontal: 4 },
  statPill:       { flex: 1, alignItems: 'center' },
  statValue:      { fontSize: 13, fontWeight: '700', color: '#e2e8f0' },
  statLabel:      { fontSize: 10, color: '#475569', marginTop: 2 },
  pnlWL:          { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pnlWLBadge:     { flexDirection: 'row', alignItems: 'center', backgroundColor: '#14280a', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, gap: 4 },
  pnlWLNum:       { fontSize: 14, fontWeight: '700', color: '#e2e8f0' },
  pnlWLLabel:     { fontSize: 12, fontWeight: '700' },
  pnlBestWorst:   { flex: 1, gap: 3 },
  pnlBWLabel:     { fontSize: 11, color: '#64748b' },

  connRow:        { flexDirection: 'row', marginHorizontal: 16, gap: 8, marginBottom: 10 },
  connCard:       { flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: '#0d1826', borderRadius: 10, padding: 10, gap: 6, borderWidth: 1, borderColor: '#1e2d3d' },
  connDot:        { width: 7, height: 7, borderRadius: 4 },
  connLabel:      { flex: 1, fontSize: 13, fontWeight: '600', color: '#94a3b8' },
  connStatus:     { fontSize: 11, fontWeight: '600' },

  brokerPicker:   { backgroundColor: '#0d1826', borderRadius: 12, marginHorizontal: 16, marginBottom: 10, padding: 6, borderWidth: 1, borderColor: '#1e2d3d' },
  brokerOpt:      { flexDirection: 'row', alignItems: 'center', padding: 10, borderRadius: 8, gap: 10 },
  brokerOptActive:{ backgroundColor: '#0c1f30' },
  brokerOptDot:   { width: 8, height: 8, borderRadius: 4 },
  brokerOptName:  { flex: 1, fontSize: 14, fontWeight: '600', color: '#e2e8f0' },
  brokerConfigBtn:{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#1e2d3d', gap: 6 },
  brokerConfigText:{ color: '#0ea5e9', fontSize: 13, fontWeight: '600' },

  readinessCard:  { backgroundColor: '#0b1420', borderRadius: 14, marginHorizontal: 16, marginBottom: 10, padding: 14, borderWidth: 1 },
  readinessTop:   { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  readinessTitleBlock: { flex: 1 },
  readinessEyebrow:{ fontSize: 10, color: '#64748b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  readinessTitleRow:{ flexDirection: 'row', alignItems: 'center', gap: 7 },
  readinessTitle: { fontSize: 18, color: '#e2e8f0', fontWeight: '800' },
  readinessScore: { minWidth: 56, height: 42, borderRadius: 10, flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', paddingTop: 6 },
  readinessScoreNum:{ fontSize: 22, fontWeight: '900' },
  readinessScorePct:{ fontSize: 12, color: '#64748b', fontWeight: '700' },
  readinessSummary:{ color: '#94a3b8', fontSize: 12, lineHeight: 17, marginTop: 8 },
  readinessItems: { marginTop: 12, borderTopWidth: 1, borderTopColor: '#132235' },
  readinessItem:  { flexDirection: 'row', alignItems: 'center', gap: 9, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: '#132235' },
  readinessItemIcon:{ width: 28, height: 28, borderRadius: 7, alignItems: 'center', justifyContent: 'center' },
  readinessItemText:{ flex: 1 },
  readinessItemLabel:{ color: '#e2e8f0', fontSize: 13, fontWeight: '700' },
  readinessItemDetail:{ color: '#64748b', fontSize: 11, lineHeight: 15, marginTop: 1 },
  readinessItemAction:{ fontSize: 11, fontWeight: '800' },
  readinessPrimaryAction:{ marginTop: 12, borderWidth: 1, borderRadius: 9, paddingVertical: 10, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 7, backgroundColor: '#08111d' },
  readinessPrimaryText:{ fontSize: 13, fontWeight: '800' },

  card:           { backgroundColor: '#0d1826', borderRadius: 14, marginHorizontal: 16, marginBottom: 10, padding: 16, borderWidth: 1, borderColor: '#1e2d3d' },
  cardTitle:      { fontSize: 16, fontWeight: '700', color: '#e2e8f0' },
  cardSub:        { fontSize: 13, color: '#64748b', marginTop: 2 },
  cardGroupTitle: { fontSize: 10, color: '#475569', fontWeight: '700', letterSpacing: 1.5, marginBottom: 12 },
  autoTradingHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  atIndicator:    { width: 4, height: 42, borderRadius: 2 },
  atText:         { flex: 1 },
  lastAlert:      { fontSize: 11, color: '#334155', marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#1e2d3d' },

  toggleRow:      { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingLeft: 8 },
  toggleIcon:     { width: 34, height: 34, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  toggleText:     { flex: 1 },
  toggleLabel:    { fontSize: 14, fontWeight: '600', color: '#e2e8f0' },
  toggleSub:      { fontSize: 12, color: '#475569', marginTop: 1 },
  toggleDivider:  { height: 1, backgroundColor: '#111c2a', marginLeft: 8 },

  shutdownStats:  { flexDirection: 'row', alignItems: 'center', marginTop: 12, gap: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#111c2a' },
  shutdownStat:   { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  shutdownStatNum:{ fontSize: 18, fontWeight: '800', color: '#f87171' },
  shutdownStatLabel:{ fontSize: 11, color: '#64748b' },
  resetBtn:       { marginLeft: 'auto' as any, backgroundColor: '#1e2d3d', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  resetBtnText:   { fontSize: 12, color: '#94a3b8', fontWeight: '600' },

  simBanner:      { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8, backgroundColor: '#1a0f3d', borderRadius: 9, marginHorizontal: 16, marginBottom: 8, padding: 10, borderWidth: 1, borderColor: '#7c3aed' },
  simBannerText:  { fontSize: 11, color: '#a78bfa', fontWeight: '700' as const, flex: 1 },

  premiumBufferRow:  { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: '#111c2a' },
  premiumBufferLeft: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 },
  premiumBufferLabel:{ fontSize: 12, color: '#334155', fontWeight: '600' as const },
  premiumBufferAmt:  { fontSize: 11, color: '#0ea5e9', backgroundColor: '#0c2740', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },

  section:        { paddingHorizontal: 16, marginBottom: 8 },
  sectionHeader:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionTitle:   { fontSize: 14, fontWeight: '700', color: '#94a3b8', letterSpacing: 0.5 },
  sectionAction:  { fontSize: 13, color: '#0ea5e9', fontWeight: '600' },
  emptyBox:       { backgroundColor: '#0d1826', borderRadius: 12, padding: 28, alignItems: 'center', gap: 8, borderWidth: 1, borderColor: '#1e2d3d' },
  emptyText:      { fontSize: 14, color: '#334155' },

  alertRow:       { flexDirection: 'row', backgroundColor: '#0d1826', borderRadius: 10, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: '#1e2d3d' },
  alertLeft:      { flex: 1 },
  alertTicker:    { fontSize: 16, fontWeight: '800', color: '#e2e8f0' },
  alertMeta:      { fontSize: 12, color: '#475569', marginTop: 3 },
  alertRight:     { alignItems: 'flex-end', gap: 4 },
  alertPrice:     { fontSize: 13, fontWeight: '700', color: '#94a3b8' },
  alertTime:      { fontSize: 10, color: '#334155' },
  badge:          { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 4 },
  badgeText:      { fontSize: 10, fontWeight: '700' },

  tradeRow:       { flexDirection: 'row', backgroundColor: '#0d1826', borderRadius: 10, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: '#1e2d3d' },
  tradeLeft:      { flex: 1, gap: 3 },
  tradeTicker:    { fontSize: 16, fontWeight: '800', color: '#e2e8f0' },
  tradeMeta:      { fontSize: 12, color: '#475569' },
  tradeTime:      { fontSize: 10, color: '#334155' },
  tradeRight:     { alignItems: 'flex-end', gap: 4 },
  tradePnl:       { fontSize: 14, fontWeight: '700' },
  tradeEntry:     { fontSize: 12, color: '#64748b' },

  // Error state styles
  errorTitle:     { fontSize: 20, fontWeight: '700', color: '#f87171', marginTop: 16 },
  errorText:      { fontSize: 14, color: '#94a3b8', marginTop: 8, textAlign: 'center' as const, paddingHorizontal: 24 },
  errorHint:      { fontSize: 11, color: '#475569', marginTop: 4, fontFamily: 'monospace' },
  retryBtn:       { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8, backgroundColor: '#0ea5e9', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 8, marginTop: 20 },
  retryBtnText:   { fontSize: 14, fontWeight: '600', color: '#fff' },
});
