import React, { useCallback, useEffect, useState } from 'react';
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
import {
  armLiveTrading,
  disarmLiveTrading,
  getAlertChains,
  getLiveReadiness,
  getOperatorEvents,
  getReconciliation,
  panicStop,
} from '../utils/apiClient';

type RunningAction = 'arm-live' | 'disarm-live' | 'panic-stop' | null;

type OperatorEvent = {
  id?: string;
  action?: string;
  summary?: string;
  created_at?: string;
  operator?: string;
};

type LiveReadiness = {
  ready?: boolean;
  blocking_issues?: { code?: string; summary?: string }[];
  runtime_state?: Record<string, unknown>;
};

type ReconciliationRow = {
  alert_id?: string;
  trade_id?: string;
  position_id?: string;
  trade_status?: string;
  position_status?: string;
};

function statusTone(ready?: boolean) {
  return ready ? '#22c55e' : '#f59e0b';
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={s.section}>
      <Text style={s.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function ActionButton({
  label,
  icon,
  tone,
  busy,
  onPress,
}: {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  tone: string;
  busy: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={[s.actionButton, { borderColor: tone }]} onPress={onPress} disabled={busy}>
      {busy ? <ActivityIndicator size="small" color={tone} /> : <Ionicons name={icon} size={17} color={tone} />}
      <Text style={[s.actionButtonText, { color: tone }]}>{label}</Text>
    </TouchableOpacity>
  );
}

export default function OperatorLabScreen() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningAction, setRunningAction] = useState<RunningAction>(null);
  const [events, setEvents] = useState<OperatorEvent[]>([]);
  const [readiness, setReadiness] = useState<LiveReadiness | null>(null);
  const [reconciliationRows, setReconciliationRows] = useState<ReconciliationRow[]>([]);
  const [chainCount, setChainCount] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [eventsRes, readinessRes, reconciliationRes, chainsRes] = await Promise.all([
        getOperatorEvents(20),
        getLiveReadiness(),
        getReconciliation(20),
        getAlertChains(20),
      ]);
      setEvents(eventsRes.data?.events ?? eventsRes.data ?? []);
      setReadiness(readinessRes.data ?? null);
      setReconciliationRows(reconciliationRes.data?.rows ?? reconciliationRes.data?.items ?? []);
      setChainCount((chainsRes.data?.chains ?? chainsRes.data?.items ?? []).length);
    } catch (error: any) {
      Alert.alert('Refresh failed', error.response?.data?.detail || error.message || 'Could not load operator data.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const runAction = useCallback(async (action: RunningAction) => {
    setRunningAction(action);
    try {
      if (action === 'arm-live') {
        await armLiveTrading({ duration_minutes: 120, confirmation: 'ARM LIVE TRADING', reason: 'operator live execution request' });
      } else if (action === 'disarm-live') {
        await disarmLiveTrading();
      } else if (action === 'panic-stop') {
        await panicStop();
      }
      await refresh();
    } catch (error: any) {
      Alert.alert('Action failed', error.response?.data?.detail || error.message || 'Operator action failed.');
    } finally {
      setRunningAction(null);
    }
  }, [refresh]);

  if (loading) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.loading}><ActivityIndicator color="#22c55e" /><Text style={s.muted}>Loading operator state...</Text></View>
      </SafeAreaView>
    );
  }

  const ready = Boolean(readiness?.ready);
  const blockers = readiness?.blocking_issues ?? [];

  return (
    <SafeAreaView style={s.container}>
      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); refresh(); }} />}
      >
        <View style={s.header}>
          <View>
            <Text style={s.eyebrow}>OPERATOR</Text>
            <Text style={s.title}>Live Controls</Text>
          </View>
          <View style={[s.statusPill, { borderColor: statusTone(ready) }]}>
            <Ionicons name={ready ? 'checkmark-circle' : 'alert-circle'} size={15} color={statusTone(ready)} />
            <Text style={[s.statusText, { color: statusTone(ready) }]}>{ready ? 'READY' : 'ATTENTION'}</Text>
          </View>
        </View>

        <Section title="Execution Controls">
          <View style={s.actionGrid}>
            <ActionButton label="Arm Live" icon="flash" tone="#22c55e" busy={runningAction === 'arm-live'} onPress={() => runAction('arm-live')} />
            <ActionButton label="Disarm" icon="pause-circle" tone="#f59e0b" busy={runningAction === 'disarm-live'} onPress={() => runAction('disarm-live')} />
            <ActionButton label="Panic Stop" icon="stop-circle" tone="#ef4444" busy={runningAction === 'panic-stop'} onPress={() => runAction('panic-stop')} />
          </View>
        </Section>

        <Section title="Readiness">
          {blockers.length ? blockers.map((issue) => (
            <View key={issue.code || issue.summary} style={s.row}>
              <Ionicons name="warning-outline" size={16} color="#f59e0b" />
              <Text style={s.rowText}>{issue.summary || issue.code}</Text>
            </View>
          )) : <Text style={s.muted}>No readiness blockers reported.</Text>}
        </Section>

        <Section title="Broker Reconciliation">
          <Text style={s.metric}>{reconciliationRows.length} recent row(s)</Text>
          <Text style={s.muted}>{chainCount} alert chain(s) loaded</Text>
        </Section>

        <Section title="Recent Operator Events">
          {events.length ? events.map((event, index) => (
            <View key={event.id || String(index)} style={s.eventRow}>
              <Text style={s.eventTitle}>{event.action || 'operator_event'}</Text>
              <Text style={s.muted}>{event.summary || event.operator || event.created_at || 'No summary'}</Text>
            </View>
          )) : <Text style={s.muted}>No operator events reported.</Text>}
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#080d16' },
  content: { padding: 18, gap: 14 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  eyebrow: { color: '#68779b', fontSize: 12, fontWeight: '800', letterSpacing: 1 },
  title: { color: '#f8fafc', fontSize: 28, fontWeight: '800' },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 },
  statusText: { fontSize: 12, fontWeight: '800' },
  section: { backgroundColor: '#101826', borderColor: '#1f2a3d', borderWidth: 1, borderRadius: 12, padding: 14, gap: 10 },
  sectionTitle: { color: '#e5eefb', fontSize: 15, fontWeight: '800' },
  actionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  actionButton: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  actionButtonText: { fontWeight: '800' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rowText: { color: '#e5eefb', flex: 1 },
  muted: { color: '#8aa0bf' },
  metric: { color: '#f8fafc', fontSize: 22, fontWeight: '800' },
  eventRow: { borderTopColor: '#1f2a3d', borderTopWidth: 1, paddingTop: 10 },
  eventTitle: { color: '#f8fafc', fontWeight: '800' },
});
