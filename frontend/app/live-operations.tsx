import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl, SafeAreaView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../utils/api';
import { BACKEND_URL } from '../constants/config';

interface JournalOrder {
  client_order_id: string;
  broker_order_id?: string;
  position_id?: string;
  broker?: string;
  ticker?: string;
  option_type?: string;
  strike?: number;
  expiration?: string;
  side?: string;
  quantity?: number;
  filled_qty?: number;
  avg_fill_price?: number;
  status?: string;
  reconciliation_required?: boolean;
  last_error?: string;
  created_at?: string;
  updated_at?: string;
  cancel_requested_at?: string;
}

interface LiveOperationsPayload {
  generated_at: string;
  supported_live_brokers: string[];
  summary: {
    journal_total: number;
    journal_active: number;
    journal_terminal: number;
    ambiguous_or_unconfirmed: number;
    working_trades: number;
    active_fill_monitors: number;
    live_positions: number;
    broker_inventory_imported_positions: number;
    broker_inventory_closed_positions: number;
  };
  position_supervisor: { running: boolean; task_name?: string };
  journal: JournalOrder[];
  unresolved_orders: JournalOrder[];
  broker_inventory: {
    latest_reconciled_at?: string | null;
    imported_positions: number;
    positions_closed_as_absent: number;
  };
}

function formatTime(value?: string | null) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function Stat({ label, value, tone = '#e2e8f0' }: { label: string; value: string | number; tone?: string }) {
  return <View style={s.stat}><Text style={[s.statValue, { color: tone }]}>{value}</Text><Text style={s.statLabel}>{label}</Text></View>;
}

export default function LiveOperationsScreen() {
  const [data, setData] = useState<LiveOperationsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await api.get(`${BACKEND_URL}/api/live-operations?limit=250`);
      setData(response.data);
      setError('');
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Live operations could not be loaded.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  const rows = showAll ? (data?.journal || []) : (data?.unresolved_orders || []);

  const renderOrder = ({ item }: { item: JournalOrder }) => {
    const status = String(item.status || 'unknown').toLowerCase();
    const warning = item.reconciliation_required || ['ambiguous', 'working_unconfirmed'].includes(status);
    const tone = warning ? '#fb923c' : status === 'filled' ? '#4ade80' : '#38bdf8';
    return (
      <View style={[s.orderCard, warning && s.orderCardWarning]}>
        <View style={s.orderTop}>
          <View style={s.orderIdentity}>
            <Text style={s.orderSymbol}>{item.ticker || 'Unknown'} {item.strike || ''} {item.option_type || ''}</Text>
            <Text style={s.orderId}>{item.client_order_id}</Text>
          </View>
          <View style={[s.statusPill, { borderColor: tone + '88', backgroundColor: tone + '18' }]}><Text style={[s.statusText, { color: tone }]}>{status.replaceAll('_', ' ')}</Text></View>
        </View>
        <View style={s.orderGrid}>
          <Text style={s.orderField}>Broker <Text style={s.orderFieldValue}>{item.broker || '-'}</Text></Text>
          <Text style={s.orderField}>Side <Text style={s.orderFieldValue}>{item.side || '-'}</Text></Text>
          <Text style={s.orderField}>Requested <Text style={s.orderFieldValue}>{item.quantity || 0}</Text></Text>
          <Text style={s.orderField}>Filled <Text style={s.orderFieldValue}>{item.filled_qty || 0}</Text></Text>
        </View>
        <Text style={s.orderMeta}>Broker order: {item.broker_order_id || 'not acknowledged'} · Position: {item.position_id || 'entry order'}</Text>
        <Text style={s.orderMeta}>Updated: {formatTime(item.updated_at || item.created_at)}</Text>
        {item.last_error ? <Text style={s.orderError}>{item.last_error}</Text> : null}
      </View>
    );
  };

  if (loading && !data) {
    return <SafeAreaView style={s.container}><View style={s.center}><ActivityIndicator size="large" color="#38bdf8" /><Text style={s.loadingText}>Loading live operations…</Text></View></SafeAreaView>;
  }

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <View><Text style={s.eyebrow}>EXECUTION</Text><Text style={s.title}>Live Operations</Text><Text style={s.subtitle}>Broker journal, monitors, inventory, and autonomous exits</Text></View>
        <TouchableOpacity style={s.refreshButton} onPress={() => { setRefreshing(true); load(); }}><Ionicons name="refresh" size={18} color="#38bdf8" /></TouchableOpacity>
      </View>

      {error ? <View style={s.errorCard}><Ionicons name="warning" size={18} color="#f87171" /><Text style={s.errorText}>{error}</Text></View> : null}

      {data ? <>
        <View style={s.supervisorCard}>
          <View style={[s.liveDot, { backgroundColor: data.position_supervisor.running ? '#22c55e' : '#ef4444' }]} />
          <View style={{ flex: 1 }}><Text style={s.supervisorTitle}>Position supervisor {data.position_supervisor.running ? 'running' : 'stopped'}</Text><Text style={s.supervisorSub}>Inventory: {formatTime(data.broker_inventory.latest_reconciled_at)}</Text></View>
          <Text style={s.brokers}>{data.supported_live_brokers.join(' · ')}</Text>
        </View>

        <View style={s.statsGrid}>
          <Stat label="Active orders" value={data.summary.journal_active} tone={data.summary.journal_active ? '#facc15' : '#4ade80'} />
          <Stat label="Unresolved" value={data.summary.ambiguous_or_unconfirmed} tone={data.summary.ambiguous_or_unconfirmed ? '#fb923c' : '#4ade80'} />
          <Stat label="Monitors" value={data.summary.active_fill_monitors} tone="#38bdf8" />
          <Stat label="Positions" value={data.summary.live_positions} tone="#a78bfa" />
          <Stat label="Working trades" value={data.summary.working_trades} tone="#38bdf8" />
          <Stat label="Journal total" value={data.summary.journal_total} />
        </View>

        <View style={s.sectionHeader}><View><Text style={s.sectionTitle}>{showAll ? 'Order Journal' : 'Unresolved Orders'}</Text><Text style={s.sectionSubtitle}>{showAll ? 'All durable broker intents and outcomes' : 'Ambiguous, unconfirmed, or reconciliation-required orders'}</Text></View><TouchableOpacity onPress={() => setShowAll((value) => !value)}><Text style={s.toggleText}>{showAll ? 'Show unresolved' : 'Show all'}</Text></TouchableOpacity></View>
      </> : null}

      <FlatList
        data={rows}
        renderItem={renderOrder}
        keyExtractor={(item) => item.client_order_id}
        contentContainerStyle={s.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#38bdf8" />}
        ListEmptyComponent={<View style={s.empty}><Ionicons name="checkmark-circle-outline" size={50} color="#14532d" /><Text style={s.emptyTitle}>{showAll ? 'No journal records' : 'No unresolved live orders'}</Text></View>}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#080f1a' }, center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }, loadingText: { color: '#64748b' },
  header: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 }, eyebrow: { color: '#38bdf8', fontSize: 10, fontWeight: '800', letterSpacing: 2 }, title: { color: '#e2e8f0', fontSize: 26, fontWeight: '900' }, subtitle: { color: '#64748b', fontSize: 11, marginTop: 2 }, refreshButton: { width: 38, height: 38, borderRadius: 10, backgroundColor: '#0c2740', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#0ea5e9' },
  errorCard: { flexDirection: 'row', gap: 10, marginHorizontal: 16, marginBottom: 10, padding: 12, borderRadius: 10, backgroundColor: '#2d1515', borderColor: '#7f1d1d', borderWidth: 1 }, errorText: { color: '#fecaca', flex: 1, fontSize: 12 },
  supervisorCard: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 16, marginBottom: 10, padding: 13, borderRadius: 12, backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d' }, liveDot: { width: 10, height: 10, borderRadius: 5 }, supervisorTitle: { color: '#e2e8f0', fontWeight: '800' }, supervisorSub: { color: '#64748b', fontSize: 10, marginTop: 2 }, brokers: { color: '#38bdf8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: 16, gap: 8, marginBottom: 12 }, stat: { width: '31%', minWidth: 100, flexGrow: 1, backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d', borderRadius: 10, padding: 11 }, statValue: { fontSize: 20, fontWeight: '900' }, statLabel: { color: '#64748b', fontSize: 9, marginTop: 3, fontWeight: '700' },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginHorizontal: 18, marginBottom: 8 }, sectionTitle: { color: '#e2e8f0', fontSize: 16, fontWeight: '800' }, sectionSubtitle: { color: '#475569', fontSize: 10, marginTop: 2 }, toggleText: { color: '#38bdf8', fontSize: 11, fontWeight: '800' }, list: { paddingHorizontal: 16, paddingBottom: 20 },
  orderCard: { backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d', borderRadius: 12, padding: 13, marginBottom: 8 }, orderCardWarning: { borderColor: '#9a3412' }, orderTop: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 }, orderIdentity: { flex: 1 }, orderSymbol: { color: '#e2e8f0', fontSize: 15, fontWeight: '800' }, orderId: { color: '#475569', fontSize: 9, marginTop: 3 }, statusPill: { borderWidth: 1, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 7, alignSelf: 'flex-start' }, statusText: { fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }, orderGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 11 }, orderField: { color: '#64748b', fontSize: 10, minWidth: '44%' }, orderFieldValue: { color: '#cbd5e1', fontWeight: '800' }, orderMeta: { color: '#475569', fontSize: 9, marginTop: 7 }, orderError: { color: '#fca5a5', fontSize: 10, marginTop: 8, padding: 8, backgroundColor: '#2d1515', borderRadius: 7 }, empty: { alignItems: 'center', paddingVertical: 70, gap: 10 }, emptyTitle: { color: '#475569', fontSize: 16, fontWeight: '700' },
});
