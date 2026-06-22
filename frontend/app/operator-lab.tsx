import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { DEMO_MODE } from '../constants/config';
import { formatDate, getPnLColor } from '../utils/format';
import {
  armLiveTrading,
  createOperatorTestAlert,
  disarmLiveTrading,
  getAlertChains,
  getLiveReadiness,
  getOperatorEvents,
  getPositions,
  getReconciliation,
  panicStop,
  simulateOperatorExit,
} from '../utils/apiClient';
import { summarizeAlertChains, type AlertChainReport } from '../utils/alertChainDigest';
import { summarizeBridgeAlertDecisions } from '../utils/alertAuditDigest';
import { summarizeLiveSafety } from '../utils/liveSafetyDigest';
import { summarizeReconciliation } from '../utils/reconciliationDigest';

type RunningAction = 'test-alert' | 'simulate-exit' | 'arm-live' | 'disarm-live' | 'panic-stop' | 'reconciliation' | null;

interface OperatorEvent {
  id: string;
  timestamp: string;
  category: string;
  action: string;
  summary: string;
  severity?: string;
  details?: Record<string, unknown>;
}

interface Position {
  id: string;
  ticker: string;
  strike: number;
  option_type: string;
  expiration: string;
  entry_price: number;
  current_price: number | null;
  remaining_quantity: number;
  original_quantity: number;
  status: string;
  broker: string;
  realized_pnl?: number;
  unrealized_pnl?: number;
  simulated?: boolean;
}

interface LiveReadiness {
  ready_for_live?: boolean;
  blocking_issues?: { code: string; summary: string }[];
  checks?: Record<string, any>;
}

interface ReconciliationRow {
  alert_id?: string;
  ticker?: string;
  trade_id?: string;
  trade_status?: string;
  order_id?: string;
  position_id?: string;
  position_status?: string;
  simulated?: boolean;
  attention_reason?: string;
}

const DEMO_EVENTS: OperatorEvent[] = [
  {
    id: 'demo-event-alert',
    timestamp: '2026-06-18T14:20:00Z',
    category: 'test_lab',
    action: 'test_alert_created',
    summary: 'Created simulated SPY alert, trade, and position.',
    severity: 'info',
    details: { ticker: 'SPY', position_id: 'demo-position-1' },
  },
  {
    id: 'demo-event-exit',
    timestamp: '2026-06-18T14:08:00Z',
    category: 'test_lab',
    action: 'simulated_exit',
    summary: 'Sold 1 contract from a test position.',
    severity: 'info',
    details: { realized_pnl: 55 },
  },
];

const DEMO_POSITIONS: Position[] = [
  {
    id: 'demo-position-1',
    ticker: 'SPY',
    strike: 500,
    option_type: 'CALL',
    expiration: '2026-06-26',
    entry_price: 1.25,
    current_price: 1.8,
    remaining_quantity: 1,
    original_quantity: 1,
    status: 'open',
    broker: 'ibkr',
    unrealized_pnl: 55,
    simulated: true,
  },
];

const DEMO_READINESS: LiveReadiness = {
  ready_for_live: false,
  blocking_issues: [{ code: 'simulation_mode_enabled', summary: 'Simulation mode is enabled.' }],
  checks: {
    runtime: { live_trading_armed: false, live_trading_armed_until: '' },
    trading: { simulation_mode: true, auto_trading_enabled: false },
    broker: { active_broker: 'ibkr', connected: true },
  },
};

const DEMO_RECONCILIATION: ReconciliationRow[] = [
  {
    alert_id: 'demo-alert',
    ticker: 'SPY',
    trade_id: 'demo-trade',
    trade_status: 'simulated',
    position_id: 'demo-position-1',
    position_status: 'open',
    simulated: true,
    attention_reason: '',
  },
];

const DEMO_ALERT_CHAINS: AlertChainReport = {
  summary: {
    total: 1,
    seen_count: 1,
    parsed_count: 1,
    accepted_count: 1,
    alert_inserted_count: 1,
    trade_requested_count: 1,
    trade_linked_count: 1,
    position_linked_count: 1,
    attention_count: 0,
    deterministic: true,
  },
  rows: [
    {
      chain_key: 'demo-chain',
      source: 'operator_test',
      ticker: 'SPY',
      alert_id: 'demo-alert',
      trade_id: 'demo-trade',
      position_id: 'demo-position-1',
      status: 'reconciled',
      deterministic: true,
    },
  ],
};

function formatMoney(value: unknown): string {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return '$0.00';
  const sign = numeric > 0 ? '+' : numeric < 0 ? '-' : '';
  return `${sign}$${Math.abs(numeric).toFixed(2)}`;
}

function eventTone(event: OperatorEvent): string {
  if (event.severity === 'error') return '#ef4444';
  if (event.severity === 'warning') return '#f59e0b';
  if (event.action.includes('exit')) return '#fb923c';
  return '#f43f5e';
}

function actionLabel(action: string): string {
  return action
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <View style={s.statTile}>
      <Text style={[s.statValue, tone ? { color: tone } : null]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function LabButton({
  icon,
  label,
  subLabel,
  tone,
  disabled,
  busy,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  subLabel: string;
  tone: string;
  disabled?: boolean;
  busy?: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      style={[s.labButton, { borderColor: tone + '66' }, disabled ? s.labButtonDisabled : null]}
      onPress={onPress}
      disabled={disabled}
      activeOpacity={0.75}
      accessibilityRole="button"
    >
      <View style={[s.labButtonIcon, { backgroundColor: tone + '1f' }]}>
        {busy ? (
          <ActivityIndicator size="small" color={tone} />
        ) : (
          <Ionicons name={icon} size={20} color={tone} />
        )}
      </View>
      <View style={s.labButtonTextWrap}>
        <Text style={s.labButtonLabel}>{label}</Text>
        <Text style={s.labButtonSub}>{subLabel}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color="#68779b" />
    </TouchableOpacity>
  );
}

export default function OperatorLabScreen() {
  const [events, setEvents] = useState<OperatorEvent[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [liveReadiness, setLiveReadiness] = useState<LiveReadiness | null>(null);
  const [reconciliationRows, setReconciliationRows] = useState<ReconciliationRow[]>([]);
  const [alertChainReport, setAlertChainReport] = useState<AlertChainReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningAction, setRunningAction] = useState<RunningAction>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshLab = useCallback(async () => {
    if (DEMO_MODE) {
      setEvents(DEMO_EVENTS);
      setPositions(DEMO_POSITIONS);
      setLiveReadiness(DEMO_READINESS);
      setReconciliationRows(DEMO_RECONCILIATION);
      setAlertChainReport(DEMO_ALERT_CHAINS);
      setLoadError(null);
      setLoading(false);
      setRefreshing(false);
      return;
    }

    try {
      const [eventsResult, positionsResult, readinessResult, reconciliationResult, alertChainsResult] = await Promise.all([
        getOperatorEvents(80),
        getPositions(),
        getLiveReadiness(),
        getReconciliation(80),
        getAlertChains(80),
      ]);
      setEvents(eventsResult.data || []);
      setPositions(positionsResult.data || []);
      setLiveReadiness(readinessResult.data || null);
      setReconciliationRows(reconciliationResult.data || []);
      setAlertChainReport(alertChainsResult.data || null);
      setLoadError(null);
    } catch (error) {
      console.error(error);
      setLoadError('Operator lab could not load. Check the backend connection and refresh.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refreshLab();
  }, [refreshLab]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    refreshLab();
  }, [refreshLab]);

  const openPositions = useMemo(
    () => positions.filter((position) => ['open', 'partial'].includes(position.status)),
    [positions]
  );
  const simulatedPositions = useMemo(
    () => positions.filter((position) => position.simulated),
    [positions]
  );
  const totalUnrealized = openPositions.reduce(
    (sum, position) => sum + (position.unrealized_pnl || 0),
    0
  );

  const runTestAlert = useCallback(async () => {
    setRunningAction('test-alert');
    try {
      if (DEMO_MODE) {
        setEvents((current) => [
          {
            id: `demo-event-${Date.now()}`,
            timestamp: new Date().toISOString(),
            category: 'test_lab',
            action: 'test_alert_created',
            summary: 'Created simulated SPY alert, trade, and position.',
            severity: 'info',
            details: { ticker: 'SPY' },
          },
          ...current,
        ]);
        Alert.alert('Test alert created', 'Operator event logged.');
        return;
      }

      await createOperatorTestAlert();
      await refreshLab();
      Alert.alert('Test alert created', 'Operator event logged.');
    } catch (error: any) {
      Alert.alert('Action failed', error.response?.data?.detail || 'Could not create a test alert.');
    } finally {
      setRunningAction(null);
    }
  }, [refreshLab]);

  const runSimulatedExit = useCallback(async () => {
    setRunningAction('simulate-exit');
    try {
      if (DEMO_MODE) {
        setEvents((current) => [
          {
            id: `demo-exit-${Date.now()}`,
            timestamp: new Date().toISOString(),
            category: 'test_lab',
            action: 'simulated_exit',
            summary: 'Sold 1 contract from a test position.',
            severity: 'info',
            details: { realized_pnl: 55 },
          },
          ...current,
        ]);
        Alert.alert('Exit simulated', 'Operator event logged.');
        return;
      }

      await simulateOperatorExit({
        sell_percentage: 50,
        exit_price: 1.8,
      });
      await refreshLab();
      Alert.alert('Exit simulated', 'Operator event logged.');
    } catch (error: any) {
      Alert.alert('Action failed', error.response?.data?.detail || 'Could not simulate an exit.');
    } finally {
      setRunningAction(null);
    }
  }, [refreshLab]);

  const runArmLive = useCallback(async () => {
    setRunningAction('arm-live');
    try {
      if (DEMO_MODE) {
        Alert.alert('Live arm blocked', 'Simulation mode is enabled in demo mode.');
        return;
      }
      await armLiveTrading({
        duration_minutes: 60,
        confirmation: 'ARM LIVE TRADING',
        reason: 'operator lab arm request',
      });
      await refreshLab();
      Alert.alert('Live trading armed', 'Live trading is armed for 60 minutes.');
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      const message = Array.isArray(detail?.blocking_issues)
        ? detail.blocking_issues[0]?.summary
        : detail || 'Live readiness blocked arming.';
      Alert.alert('Arm blocked', String(message));
    } finally {
      setRunningAction(null);
    }
  }, [refreshLab]);

  const runDisarmLive = useCallback(async () => {
    setRunningAction('disarm-live');
    try {
      if (!DEMO_MODE) {
        await disarmLiveTrading();
        await refreshLab();
      }
      Alert.alert('Live trading disarmed', 'Runtime live arming is cleared.');
    } catch (error: any) {
      Alert.alert('Action failed', error.response?.data?.detail || 'Could not disarm live trading.');
    } finally {
      setRunningAction(null);
    }
  }, [refreshLab]);

  const runPanicStop = useCallback(async () => {
    setRunningAction('panic-stop');
    try {
      if (!DEMO_MODE) {
        await panicStop();
        await refreshLab();
      }
      Alert.alert('Panic stop applied', 'Auto trading is disabled and live trading is disarmed.');
    } catch (error: any) {
      Alert.alert('Action failed', error.response?.data?.detail || 'Could not apply panic stop.');
    } finally {
      setRunningAction(null);
    }
  }, [refreshLab]);

  const refreshReconciliation = useCallback(async () => {
    setRunningAction('reconciliation');
    try {
      if (DEMO_MODE) {
        setReconciliationRows(DEMO_RECONCILIATION);
        setAlertChainReport(DEMO_ALERT_CHAINS);
        return;
      }
      const [response, alertChainsResponse] = await Promise.all([
        getReconciliation(80),
        getAlertChains(80),
      ]);
      setReconciliationRows(response.data || []);
      setAlertChainReport(alertChainsResponse.data || null);
    } catch (error: any) {
      Alert.alert('Refresh failed', error.response?.data?.detail || 'Could not load reconciliation.');
    } finally {
      setRunningAction(null);
    }
  }, []);

  const latestEvent = events[0];
  const liveSafety = useMemo(() => summarizeLiveSafety(liveReadiness), [liveReadiness]);
  const reconciliation = useMemo(
    () => summarizeReconciliation(reconciliationRows),
    [reconciliationRows]
  );
  const bridgeAlerts = useMemo(() => summarizeBridgeAlertDecisions(events), [events]);
  const alertChains = useMemo(() => summarizeAlertChains(alertChainReport), [alertChainReport]);

  return (
    <SafeAreaView style={s.container}>
      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#f43f5e" />}
      >
        <View style={s.header}>
          <View>
            <Text style={s.eyebrow}>OPERATOR TEST LAB</Text>
            <Text style={s.title}>Lab</Text>
          </View>
          <TouchableOpacity
            style={s.refreshButton}
            onPress={onRefresh}
            disabled={refreshing}
            accessibilityRole="button"
          >
            <Ionicons name="refresh" size={16} color="#fb7185" />
            <Text style={s.refreshText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        {loadError && (
          <View style={s.errorBanner}>
            <Ionicons name="warning-outline" size={16} color="#f59e0b" />
            <Text style={s.errorBannerText}>{loadError}</Text>
          </View>
        )}

        <View style={s.briefing}>
          <View style={s.briefingCopy}>
            <Text style={s.briefingEyebrow}>RUNBOOK STATE</Text>
            <Text style={s.briefingTitle}>
              {latestEvent ? actionLabel(latestEvent.action) : 'No Lab Events'}
            </Text>
            <Text style={s.briefingDetail}>
              {latestEvent ? latestEvent.summary : 'Create a test alert to begin the event trail.'}
            </Text>
          </View>
          <View style={s.briefingGauge}>
            <Text style={s.briefingGaugeValue}>{events.length}</Text>
            <Text style={s.briefingGaugeLabel}>events</Text>
          </View>
        </View>

        <View style={s.statsGrid}>
          <StatTile label="Open Positions" value={String(openPositions.length)} tone="#22c55e" />
          <StatTile label="Simulated" value={String(simulatedPositions.length)} tone="#a78bfa" />
          <StatTile label="Unrealized" value={formatMoney(totalUnrealized)} tone={getPnLColor(totalUnrealized)} />
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <View>
              <Text style={s.panelTitle}>Live Safety</Text>
              <Text style={s.panelSub}>{liveSafety.detail}</Text>
            </View>
            <View style={[s.panelPill, liveSafety.tone === 'blocked' ? s.panelPillBlocked : null]}>
              <Ionicons
                name={liveSafety.isArmed ? 'radio-button-on-outline' : 'shield-checkmark-outline'}
                size={13}
                color={liveSafety.tone === 'blocked' ? '#ef4444' : '#22c55e'}
              />
              <Text style={[s.panelPillText, liveSafety.tone === 'blocked' ? s.panelPillTextBlocked : null]}>
                {liveSafety.title}
              </Text>
            </View>
          </View>

          <View style={s.actionStack}>
            <LabButton
              icon="radio-outline"
              label="Arm Live"
              subLabel={liveSafety.canArm ? 'Arm for 60 minutes' : `${liveSafety.blockerCount} blocker(s)`}
              tone="#ef4444"
              busy={runningAction === 'arm-live'}
              disabled={runningAction !== null || !liveSafety.canArm}
              onPress={runArmLive}
            />
            <LabButton
              icon="radio-button-off-outline"
              label="Disarm"
              subLabel={liveSafety.isArmed ? `Armed until ${liveSafety.armedUntilLabel}` : 'Runtime is not armed'}
              tone="#38bdf8"
              busy={runningAction === 'disarm-live'}
              disabled={runningAction !== null}
              onPress={runDisarmLive}
            />
            <LabButton
              icon="stop-circle-outline"
              label="Panic Stop"
              subLabel="Disable automation and set shutdown state"
              tone="#f43f5e"
              busy={runningAction === 'panic-stop'}
              disabled={runningAction !== null}
              onPress={runPanicStop}
            />
          </View>
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <View>
              <Text style={s.panelTitle}>Reconciliation</Text>
              <Text style={s.panelSub}>{reconciliation.detail}</Text>
            </View>
            <TouchableOpacity
              style={s.refreshButton}
              onPress={refreshReconciliation}
              disabled={runningAction !== null}
              accessibilityRole="button"
            >
              {runningAction === 'reconciliation' ? (
                <ActivityIndicator size="small" color="#fb7185" />
              ) : (
                <Ionicons name="git-compare-outline" size={16} color="#fb7185" />
              )}
              <Text style={s.refreshText}>Reconciliation</Text>
            </TouchableOpacity>
          </View>
          <View style={s.statsGrid}>
            <StatTile label="Chains" value={String(reconciliation.total)} tone="#38bdf8" />
            <StatTile label="Attention" value={String(reconciliation.attentionCount)} tone={reconciliation.attentionCount > 0 ? '#f59e0b' : '#22c55e'} />
            <StatTile label="Pending" value={String(reconciliation.pendingCount)} tone="#a78bfa" />
          </View>
          {reconciliationRows.slice(0, 4).map((row) => (
            <View key={`${row.alert_id}-${row.trade_id || 'none'}`} style={s.eventRow}>
              <View style={[s.eventIcon, { backgroundColor: (row.attention_reason ? '#f59e0b' : '#22c55e') + '1f' }]}>
                <Ionicons name={row.attention_reason ? 'warning-outline' : 'checkmark-circle-outline'} size={16} color={row.attention_reason ? '#f59e0b' : '#22c55e'} />
              </View>
              <View style={s.eventBody}>
                <View style={s.eventTopLine}>
                  <Text style={s.eventAction}>{row.ticker || 'Unknown'} chain</Text>
                  <Text style={s.eventTime}>{row.trade_status || 'no trade'}</Text>
                </View>
                <Text style={s.eventSummary}>{row.attention_reason || `Trade ${row.trade_id || 'none'} linked to position ${row.position_id || 'none'}.`}</Text>
                <Text style={s.eventCategory}>{row.simulated === false ? 'LIVE' : 'SIMULATED'}</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <View>
              <Text style={s.panelTitle}>Alert Chain Proof</Text>
              <Text style={s.panelSub}>{alertChains.detail}</Text>
            </View>
            <View style={[s.panelPill, alertChains.attentionCount > 0 ? s.panelPillBlocked : null]}>
              <Ionicons
                name={alertChains.attentionCount > 0 ? 'warning-outline' : 'checkmark-circle-outline'}
                size={13}
                color={alertChains.attentionCount > 0 ? '#ef4444' : '#22c55e'}
              />
              <Text style={[s.panelPillText, alertChains.attentionCount > 0 ? s.panelPillTextBlocked : null]}>
                {alertChains.stateLabel}
              </Text>
            </View>
          </View>
          <View style={s.statsGrid}>
            <StatTile label="Seen" value={String(alertChains.stageCounts.seen)} tone="#38bdf8" />
            <StatTile label="Parsed" value={String(alertChains.stageCounts.parsed)} tone="#22c55e" />
            <StatTile label="Decided" value={String(alertChains.stageCounts.decided)} tone="#a78bfa" />
          </View>
          <View style={s.statsGrid}>
            <StatTile label="Placed" value={String(alertChains.stageCounts.placed)} tone="#fb923c" />
            <StatTile label="Reconciled" value={String(alertChains.stageCounts.reconciled)} tone="#22c55e" />
            <StatTile label="Attention" value={String(alertChains.attentionCount)} tone={alertChains.attentionCount > 0 ? '#f59e0b' : '#68779b'} />
          </View>
          {alertChains.rows.length === 0 ? (
            <View style={s.emptyBlock}>
              <Ionicons name="git-network-outline" size={34} color="#29213a" />
              <Text style={s.emptyTitle}>No alert chains</Text>
            </View>
          ) : (
            alertChains.rows.slice(0, 5).map((row, index) => {
              const needsReview = row.status === 'attention' || !row.deterministic;
              const tone = needsReview ? '#f59e0b' : '#22c55e';
              return (
                <View key={`${row.key}-${index}`} style={s.eventRow}>
                  <View style={[s.eventIcon, { backgroundColor: tone + '1f' }]}>
                    <Ionicons name={needsReview ? 'warning-outline' : 'checkmark-circle-outline'} size={16} color={tone} />
                  </View>
                  <View style={s.eventBody}>
                    <View style={s.eventTopLine}>
                      <Text style={s.eventAction}>{row.tickerLabel} chain</Text>
                      <Text style={s.eventTime}>{row.status}</Text>
                    </View>
                    <Text style={s.eventSummary}>{row.attentionReason || row.decisionReason || row.linkageLabel}</Text>
                    <Text style={s.eventCategory}>{row.sourceEvidenceLabel} / {row.deterministic ? 'DETERMINISTIC' : 'REVIEW'}</Text>
                  </View>
                </View>
              );
            })
          )}
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <View>
              <Text style={s.panelTitle}>Bridge Alerts</Text>
              <Text style={s.panelSub}>{bridgeAlerts.detail}</Text>
            </View>
            <View style={[s.panelPill, bridgeAlerts.skippedCount > 0 ? s.panelPillBlocked : null]}>
              <Ionicons
                name={bridgeAlerts.skippedCount > 0 ? 'warning-outline' : 'checkmark-circle-outline'}
                size={13}
                color={bridgeAlerts.skippedCount > 0 ? '#ef4444' : '#22c55e'}
              />
              <Text style={[s.panelPillText, bridgeAlerts.skippedCount > 0 ? s.panelPillTextBlocked : null]}>
                {bridgeAlerts.stateLabel}
              </Text>
            </View>
          </View>
          <View style={s.statsGrid}>
            <StatTile label="Seen" value={String(bridgeAlerts.total)} tone="#38bdf8" />
            <StatTile label="Accepted" value={String(bridgeAlerts.acceptedCount)} tone="#22c55e" />
            <StatTile label="Skipped" value={String(bridgeAlerts.skippedCount)} tone={bridgeAlerts.skippedCount > 0 ? '#f59e0b' : '#68779b'} />
          </View>
          {bridgeAlerts.rows.length === 0 ? (
            <View style={s.emptyBlock}>
              <Ionicons name="notifications-outline" size={34} color="#29213a" />
              <Text style={s.emptyTitle}>No bridge alerts</Text>
            </View>
          ) : (
            bridgeAlerts.rows.slice(0, 5).map((row, index) => {
              const skipped = row.status === 'skipped';
              const tone = skipped ? '#f59e0b' : '#22c55e';
              return (
                <View key={`${row.id}-${index}`} style={s.eventRow}>
                  <View style={[s.eventIcon, { backgroundColor: tone + '1f' }]}>
                    <Ionicons name={skipped ? 'warning-outline' : 'checkmark-circle-outline'} size={16} color={tone} />
                  </View>
                  <View style={s.eventBody}>
                    <View style={s.eventTopLine}>
                      <Text style={s.eventAction}>{row.tickerLabel}</Text>
                      <Text style={s.eventTime}>{formatDate(row.timestamp)}</Text>
                    </View>
                    <Text style={s.eventSummary}>{row.skipReason || row.summary}</Text>
                    {row.rawTextPreview ? <Text style={s.eventSummary}>{row.rawTextPreview}</Text> : null}
                    <Text style={s.eventCategory}>
                      {row.channelLabel} / {row.authorLabel} / parser {row.parserConfidence} / source {row.sourceLabel}
                    </Text>
                  </View>
                </View>
              );
            })
          )}
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Test Bench</Text>
            <View style={s.panelPill}>
              <Ionicons name="shield-checkmark-outline" size={13} color="#22c55e" />
              <Text style={s.panelPillText}>Simulation</Text>
            </View>
          </View>

          <View style={s.actionStack}>
            <LabButton
              icon="notifications-outline"
              label="Create Test Alert"
              subLabel="SPY alert, trade, and position"
              tone="#f43f5e"
              busy={runningAction === 'test-alert'}
              disabled={runningAction !== null}
              onPress={runTestAlert}
            />
            <LabButton
              icon="exit-outline"
              label="Sell 50% Test Position"
              subLabel="Uses the first open position"
              tone="#fb923c"
              busy={runningAction === 'simulate-exit'}
              disabled={runningAction !== null}
              onPress={runSimulatedExit}
            />
          </View>
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Activity Log</Text>
            <Text style={s.panelMeta}>{events.length} total</Text>
          </View>

          {loading ? (
            <View style={s.loadingBlock}>
              <ActivityIndicator color="#f43f5e" />
            </View>
          ) : events.length === 0 ? (
            <View style={s.emptyBlock}>
              <Ionicons name="file-tray-outline" size={34} color="#29213a" />
              <Text style={s.emptyTitle}>No events</Text>
            </View>
          ) : (
            events.slice(0, 12).map((event) => {
              const tone = eventTone(event);
              return (
                <View key={event.id} style={s.eventRow}>
                  <View style={[s.eventIcon, { backgroundColor: tone + '1f' }]}>
                    <Ionicons name={event.action.includes('exit') ? 'exit-outline' : 'flask-outline'} size={16} color={tone} />
                  </View>
                  <View style={s.eventBody}>
                    <View style={s.eventTopLine}>
                      <Text style={s.eventAction}>{actionLabel(event.action)}</Text>
                      <Text style={s.eventTime}>{formatDate(event.timestamp)}</Text>
                    </View>
                    <Text style={s.eventSummary}>{event.summary}</Text>
                    <Text style={s.eventCategory}>{event.category}</Text>
                  </View>
                </View>
              );
            })
          )}
        </View>

        <View style={s.panel}>
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Open Positions</Text>
            <Text style={s.panelMeta}>{openPositions.length} open</Text>
          </View>

          {openPositions.length === 0 ? (
            <View style={s.emptyBlock}>
              <Ionicons name="briefcase-outline" size={34} color="#29213a" />
              <Text style={s.emptyTitle}>No open positions</Text>
            </View>
          ) : (
            openPositions.slice(0, 5).map((position) => (
              <View key={position.id} style={s.positionRow}>
                <View>
                  <View style={s.positionTickerLine}>
                    <Text style={s.positionTicker}>${position.ticker}</Text>
                    <View style={s.positionTypePill}>
                      <Text style={s.positionTypeText}>{position.option_type}</Text>
                    </View>
                  </View>
                  <Text style={s.positionSub}>
                    {position.strike} {position.expiration} - {position.broker}
                  </Text>
                </View>
                <View style={s.positionRight}>
                  <Text style={s.positionQty}>
                    {position.remaining_quantity}/{position.original_quantity}
                  </Text>
                  <Text style={[s.positionPnl, { color: getPnLColor(position.unrealized_pnl || 0) }]}>
                    {formatMoney(position.unrealized_pnl || 0)}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050416' },
  content: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 20 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 12 },
  eyebrow: { fontSize: 10, color: '#f43f5e', fontWeight: '800', letterSpacing: 2, marginBottom: 2 },
  title: { fontSize: 26, fontWeight: '800', color: '#edf3ff' },
  refreshButton: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(244, 63, 94, 0.18)', borderWidth: 1, borderColor: '#f43f5e', borderRadius: 8, paddingHorizontal: 11, paddingVertical: 8 },
  refreshText: { fontSize: 12, color: '#fb7185', fontWeight: '800' },

  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, padding: 10, borderRadius: 8, backgroundColor: '#1c1500', borderWidth: 1, borderColor: '#92400e' },
  errorBannerText: { flex: 1, fontSize: 12, color: '#f59e0b', fontWeight: '600' },

  briefing: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: 'rgba(16, 9, 28, 0.88)', borderWidth: 1, borderColor: '#29213a', borderRadius: 14, padding: 14, marginBottom: 10 },
  briefingCopy: { flex: 1 },
  briefingEyebrow: { fontSize: 10, color: '#68779b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  briefingTitle: { fontSize: 18, fontWeight: '900', color: '#edf3ff' },
  briefingDetail: { fontSize: 12, lineHeight: 17, color: '#aec0e5', marginTop: 3 },
  briefingGauge: { minWidth: 72, height: 54, borderRadius: 11, backgroundColor: 'rgba(14, 165, 233, 0.12)', alignItems: 'center', justifyContent: 'center' },
  briefingGaugeValue: { fontSize: 22, fontWeight: '900', color: '#fb7185' },
  briefingGaugeLabel: { fontSize: 10, color: '#68779b', fontWeight: '800' },

  statsGrid: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  statTile: { flex: 1, alignItems: 'center', backgroundColor: 'rgba(16, 9, 28, 0.82)', borderWidth: 1, borderColor: '#29213a', borderRadius: 10, paddingVertical: 11, paddingHorizontal: 6 },
  statValue: { fontSize: 16, fontWeight: '900', color: '#edf3ff' },
  statLabel: { fontSize: 10, color: '#68779b', fontWeight: '700', marginTop: 3, textAlign: 'center' },

  panel: { backgroundColor: 'rgba(16, 9, 28, 0.82)', borderRadius: 12, borderWidth: 1, borderColor: '#29213a', padding: 14, marginBottom: 10 },
  panelHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  panelTitle: { fontSize: 16, color: '#edf3ff', fontWeight: '900' },
  panelSub: { marginTop: 3, fontSize: 11, lineHeight: 16, color: '#aec0e5', fontWeight: '700', maxWidth: 520 },
  panelMeta: { fontSize: 11, color: '#68779b', fontWeight: '800' },
  panelPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#10251d', borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 },
  panelPillBlocked: { backgroundColor: '#2a1014' },
  panelPillText: { fontSize: 10, color: '#22c55e', fontWeight: '900' },
  panelPillTextBlocked: { color: '#ef4444' },

  actionStack: { gap: 9 },
  labButton: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#0a1522', borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  labButtonDisabled: { opacity: 0.65 },
  labButtonIcon: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  labButtonTextWrap: { flex: 1 },
  labButtonLabel: { fontSize: 14, color: '#edf3ff', fontWeight: '900' },
  labButtonSub: { fontSize: 11, color: '#68779b', fontWeight: '700', marginTop: 2 },

  loadingBlock: { alignItems: 'center', paddingVertical: 24 },
  emptyBlock: { alignItems: 'center', paddingVertical: 28, gap: 8 },
  emptyTitle: { color: '#68779b', fontSize: 14, fontWeight: '800' },

  eventRow: { flexDirection: 'row', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: 'rgba(41, 33, 58, 0.82)' },
  eventIcon: { width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  eventBody: { flex: 1 },
  eventTopLine: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  eventAction: { flex: 1, color: '#edf3ff', fontSize: 13, fontWeight: '900' },
  eventTime: { fontSize: 10, color: '#68779b', fontWeight: '700' },
  eventSummary: { color: '#aec0e5', fontSize: 12, lineHeight: 17, marginTop: 2 },
  eventCategory: { color: '#68779b', fontSize: 10, fontWeight: '800', marginTop: 3, textTransform: 'uppercase' },

  positionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: 'rgba(41, 33, 58, 0.82)' },
  positionTickerLine: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  positionTicker: { fontSize: 15, color: '#edf3ff', fontWeight: '900' },
  positionTypePill: { backgroundColor: '#10251d', borderRadius: 5, paddingHorizontal: 6, paddingVertical: 2 },
  positionTypeText: { color: '#22c55e', fontSize: 10, fontWeight: '900' },
  positionSub: { color: '#68779b', fontSize: 11, marginTop: 3 },
  positionRight: { alignItems: 'flex-end' },
  positionQty: { color: '#aec0e5', fontSize: 12, fontWeight: '800' },
  positionPnl: { fontSize: 12, fontWeight: '900', marginTop: 3 },
});
