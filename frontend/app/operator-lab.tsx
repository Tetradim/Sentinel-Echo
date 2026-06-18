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
import { api } from '../utils/api';
import { BACKEND_URL, DEMO_MODE } from '../constants/config';
import { formatDate, getPnLColor } from '../utils/format';

type RunningAction = 'test-alert' | 'simulate-exit' | null;

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
  return '#0ea5e9';
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
      <Ionicons name="chevron-forward" size={18} color="#334155" />
    </TouchableOpacity>
  );
}

export default function OperatorLabScreen() {
  const [events, setEvents] = useState<OperatorEvent[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningAction, setRunningAction] = useState<RunningAction>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshLab = useCallback(async () => {
    if (DEMO_MODE) {
      setEvents(DEMO_EVENTS);
      setPositions(DEMO_POSITIONS);
      setLoadError(null);
      setLoading(false);
      setRefreshing(false);
      return;
    }

    try {
      const [eventsResult, positionsResult] = await Promise.all([
        api.get(`${BACKEND_URL}/api/operator/events?limit=80`),
        api.get(`${BACKEND_URL}/api/positions`),
      ]);
      setEvents(eventsResult.data || []);
      setPositions(positionsResult.data || []);
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

      await api.post(`${BACKEND_URL}/api/operator/test-alert`);
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

      await api.post(`${BACKEND_URL}/api/operator/simulate-exit`, {
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

  const latestEvent = events[0];

  return (
    <SafeAreaView style={s.container}>
      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0ea5e9" />}
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
            <Ionicons name="refresh" size={16} color="#7dd3fc" />
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
              tone="#0ea5e9"
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
              <ActivityIndicator color="#0ea5e9" />
            </View>
          ) : events.length === 0 ? (
            <View style={s.emptyBlock}>
              <Ionicons name="file-tray-outline" size={34} color="#1e2d3d" />
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
              <Ionicons name="briefcase-outline" size={34} color="#1e2d3d" />
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
  container: { flex: 1, backgroundColor: '#080f1a' },
  content: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 20 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 12 },
  eyebrow: { fontSize: 10, color: '#0ea5e9', fontWeight: '800', letterSpacing: 2, marginBottom: 2 },
  title: { fontSize: 26, fontWeight: '800', color: '#e2e8f0' },
  refreshButton: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9', borderRadius: 8, paddingHorizontal: 11, paddingVertical: 8 },
  refreshText: { fontSize: 12, color: '#7dd3fc', fontWeight: '800' },

  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, padding: 10, borderRadius: 8, backgroundColor: '#1c1500', borderWidth: 1, borderColor: '#92400e' },
  errorBannerText: { flex: 1, fontSize: 12, color: '#f59e0b', fontWeight: '600' },

  briefing: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#0b1420', borderWidth: 1, borderColor: '#1e2d3d', borderRadius: 14, padding: 14, marginBottom: 10 },
  briefingCopy: { flex: 1 },
  briefingEyebrow: { fontSize: 10, color: '#64748b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  briefingTitle: { fontSize: 18, fontWeight: '900', color: '#e2e8f0' },
  briefingDetail: { fontSize: 12, lineHeight: 17, color: '#94a3b8', marginTop: 3 },
  briefingGauge: { minWidth: 72, height: 54, borderRadius: 11, backgroundColor: 'rgba(14, 165, 233, 0.12)', alignItems: 'center', justifyContent: 'center' },
  briefingGaugeValue: { fontSize: 22, fontWeight: '900', color: '#7dd3fc' },
  briefingGaugeLabel: { fontSize: 10, color: '#64748b', fontWeight: '800' },

  statsGrid: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  statTile: { flex: 1, alignItems: 'center', backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d', borderRadius: 10, paddingVertical: 11, paddingHorizontal: 6 },
  statValue: { fontSize: 16, fontWeight: '900', color: '#e2e8f0' },
  statLabel: { fontSize: 10, color: '#64748b', fontWeight: '700', marginTop: 3, textAlign: 'center' },

  panel: { backgroundColor: '#0d1826', borderRadius: 12, borderWidth: 1, borderColor: '#1e2d3d', padding: 14, marginBottom: 10 },
  panelHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  panelTitle: { fontSize: 16, color: '#e2e8f0', fontWeight: '900' },
  panelMeta: { fontSize: 11, color: '#64748b', fontWeight: '800' },
  panelPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#10251d', borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 },
  panelPillText: { fontSize: 10, color: '#22c55e', fontWeight: '900' },

  actionStack: { gap: 9 },
  labButton: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#0a1522', borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  labButtonDisabled: { opacity: 0.65 },
  labButtonIcon: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  labButtonTextWrap: { flex: 1 },
  labButtonLabel: { fontSize: 14, color: '#e2e8f0', fontWeight: '900' },
  labButtonSub: { fontSize: 11, color: '#64748b', fontWeight: '700', marginTop: 2 },

  loadingBlock: { alignItems: 'center', paddingVertical: 24 },
  emptyBlock: { alignItems: 'center', paddingVertical: 28, gap: 8 },
  emptyTitle: { color: '#334155', fontSize: 14, fontWeight: '800' },

  eventRow: { flexDirection: 'row', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#132235' },
  eventIcon: { width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  eventBody: { flex: 1 },
  eventTopLine: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  eventAction: { flex: 1, color: '#e2e8f0', fontSize: 13, fontWeight: '900' },
  eventTime: { fontSize: 10, color: '#475569', fontWeight: '700' },
  eventSummary: { color: '#94a3b8', fontSize: 12, lineHeight: 17, marginTop: 2 },
  eventCategory: { color: '#334155', fontSize: 10, fontWeight: '800', marginTop: 3, textTransform: 'uppercase' },

  positionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#132235' },
  positionTickerLine: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  positionTicker: { fontSize: 15, color: '#e2e8f0', fontWeight: '900' },
  positionTypePill: { backgroundColor: '#10251d', borderRadius: 5, paddingHorizontal: 6, paddingVertical: 2 },
  positionTypeText: { color: '#22c55e', fontSize: 10, fontWeight: '900' },
  positionSub: { color: '#64748b', fontSize: 11, marginTop: 3 },
  positionRight: { alignItems: 'flex-end' },
  positionQty: { color: '#94a3b8', fontSize: 12, fontWeight: '800' },
  positionPnl: { fontSize: 12, fontWeight: '900', marginTop: 3 },
});
