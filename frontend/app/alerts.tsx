import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../utils/api';
import { BACKEND_URL, DEMO_MODE } from '../constants/config';
import {
  AlertDigest,
  AlertFilter,
  filterAlerts,
  summarizeAlerts,
} from '../utils/alertDigest';

// Demo alerts
const DEMO_ALERTS: AlertItem[] = [
  { id: '1', ticker: 'AAPL', strike: 175, option_type: 'CALL', expiration: '2024-05-17', entry_price: 3.50, raw_message: 'BTO AAPL 175C May 17', channel_name: 'alerts', received_at: '2024-04-18T10:30:00Z', processed: true, trade_executed: true },
  { id: '2', ticker: 'TSLA', strike: 150, option_type: 'PUT', expiration: '2024-05-17', entry_price: 2.80, raw_message: 'BTO TSLA 150P May 17', channel_name: 'alerts', received_at: '2024-04-18T09:15:00Z', processed: true, trade_executed: true },
  { id: '3', ticker: 'NVDA', strike: 800, option_type: 'CALL', expiration: '2024-04-19', entry_price: 12.50, raw_message: 'BTO NVDA 800C Apr 19', channel_name: 'alerts', received_at: '2024-04-17T14:20:00Z', processed: true, trade_executed: false },
  { id: '4', ticker: 'MSFT', strike: 380, option_type: 'CALL', expiration: '2024-05-17', entry_price: 5.20, raw_message: 'STC MSFT 380C May 17', channel_name: 'alerts', received_at: '2024-04-17T11:45:00Z', processed: false, trade_executed: false },
  { id: '5', ticker: 'GOOGL', strike: 155, option_type: 'CALL', expiration: '2024-05-17', entry_price: 2.10, raw_message: 'BTO GOOGL 155C May 17', channel_name: 'alerts', received_at: '2024-04-17T08:30:00Z', processed: true, trade_executed: true },
  { id: '6', ticker: 'META', strike: 480, option_type: 'CALL', expiration: '2024-05-17', entry_price: 8.50, raw_message: 'BTO META 480C May 17', channel_name: 'alerts', received_at: '2024-04-16T16:00:00Z', processed: true, trade_executed: true },
];

interface AlertItem {
  id: string; ticker: string; strike: number; option_type: string;
  expiration: string; entry_price: number; raw_message: string;
  channel_name: string; received_at: string; processed: boolean; trade_executed: boolean;
}

function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={s.digestStat}>
      <Text style={[s.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={s.digestStatLabel}>{label}</Text>
    </View>
  );
}

function AlertBriefing({ digest }: { digest: AlertDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#64748b';

  return (
    <View style={[s.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={s.digestTop}>
        <View style={s.digestTitleBlock}>
          <Text style={s.digestEyebrow}>ALERT FLOW</Text>
          <Text style={s.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={s.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[s.digestRate, { backgroundColor: toneColor + '18' }]}>
          <Text style={[s.digestRateValue, { color: toneColor }]}>{digest.executionRate}</Text>
          <Text style={s.digestRateSuffix}>%</Text>
        </View>
      </View>
      <View style={s.digestStats}>
        <DigestStat label="Executed" value={String(digest.executed)} color="#22c55e" />
        <DigestStat label="Review" value={String(digest.needsReview)} color={digest.needsReview ? '#f59e0b' : undefined} />
        <DigestStat label="Unparsed" value={String(digest.unparsed)} color={digest.unparsed ? '#ef4444' : undefined} />
        <DigestStat label="Top Ticker" value={digest.topTicker || '-'} />
      </View>
    </View>
  );
}

export default function AlertsScreen() {
  const [alerts, setAlerts]     = useState<AlertItem[]>([]);
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter]     = useState<AlertFilter>('all');

  const fetchAlerts = useCallback(async () => {
    if (DEMO_MODE) {
      setAlerts(DEMO_ALERTS);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    try {
      const r = await api.get(`${BACKEND_URL}/api/alerts?limit=200`);
      setAlerts(r.data);
    } catch (e) { 
      console.error(e);
      setAlerts(DEMO_ALERTS);
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);
  const onRefresh = useCallback(() => { setRefreshing(true); fetchAlerts(); }, [fetchAlerts]);

  const digest = summarizeAlerts(alerts);
  const filterOptions: { key: AlertFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: digest.total },
    { key: 'executed', label: 'Executed', count: digest.executed },
    { key: 'review', label: 'Review', count: digest.needsReview },
    { key: 'unparsed', label: 'Unparsed', count: digest.unparsed },
  ];
  const filtered = filterAlerts(alerts, filter);

  const fmt = (d: string) => new Date(d).toLocaleString();

  const renderItem = ({ item: a }: { item: AlertItem }) => {
    const statusLabel = a.trade_executed ? 'Executed' : a.processed ? 'Review' : 'Unparsed';
    const statusColor = a.trade_executed ? '#22c55e' : a.processed ? '#f59e0b' : '#ef4444';
    const statusBg = a.trade_executed ? '#14532d' : a.processed ? '#422006' : '#2d1515';

    return (
      <View style={s.card}>
        <View style={s.cardTop}>
          <View style={s.tickerWrap}>
            <Text style={s.ticker}>${a.ticker}</Text>
            <View style={[s.typePill, { backgroundColor: a.option_type === 'CALL' ? '#14532d' : '#450a0a' }]}>
              <Text style={[s.typeText, { color: a.option_type === 'CALL' ? '#4ade80' : '#f87171' }]}>
                {a.option_type}
              </Text>
            </View>
          </View>
          <View style={[s.statusPill, { backgroundColor: statusBg }]}>
            <View style={[s.statusDot, { backgroundColor: statusColor }]} />
            <Text style={[s.statusText, { color: statusColor }]}>{statusLabel}</Text>
          </View>
        </View>

      <View style={s.grid}>
        <View style={s.gridItem}>
          <Text style={s.gridLabel}>STRIKE</Text>
          <Text style={s.gridValue}>${a.strike}</Text>
        </View>
        <View style={s.gridItem}>
          <Text style={s.gridLabel}>EXPIRY</Text>
          <Text style={s.gridValue}>{a.expiration}</Text>
        </View>
        <View style={s.gridItem}>
          <Text style={s.gridLabel}>ENTRY</Text>
          <Text style={s.gridValue}>${a.entry_price.toFixed(2)}</Text>
        </View>
      </View>

      <View style={s.cardBottom}>
        {a.channel_name ? (
          <View style={s.channelRow}>
            <Ionicons name="chatbubble-outline" size={12} color="#334155" />
            <Text style={s.channelText}>#{a.channel_name}</Text>
          </View>
        ) : <View />}
        <Text style={s.timestamp}>{fmt(a.received_at)}</Text>
      </View>
    </View>
    );
  };

  return (
    <SafeAreaView style={s.container}>
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.eyebrow}>DISCORD ALERTS</Text>
          <Text style={s.title}>Alerts</Text>
        </View>
        <View style={s.countBadge}>
          <Text style={s.countText}>{alerts.length}</Text>
        </View>
      </View>

      <AlertBriefing digest={digest} />

      {/* Filter bar */}
      <View style={s.filterBar}>
        {filterOptions.map(({ key, label, count }) => (
          <TouchableOpacity key={key} style={[s.filterBtn, filter === key && s.filterBtnActive]} onPress={() => setFilter(key)}>
            <Text style={[s.filterText, filter === key && s.filterTextActive]}>
              {label}
            </Text>
            <Text style={[s.filterCount, filter === key && s.filterCountActive]}>{count}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={s.centered}><ActivityIndicator size="large" color="#0ea5e9" /></View>
      ) : (
        <FlatList
          data={filtered}
          renderItem={renderItem}
          keyExtractor={i => i.id}
          contentContainerStyle={s.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0ea5e9" />}
          ListEmptyComponent={
            <View style={s.empty}>
              <Ionicons name="notifications-off-outline" size={48} color="#1e2d3d" />
              <Text style={s.emptyTitle}>No alerts</Text>
              <Text style={s.emptySub}>Alerts from Discord will appear here</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#080f1a' },
  centered:       { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 },
  eyebrow:        { fontSize: 10, color: '#0ea5e9', fontWeight: '700', letterSpacing: 2, marginBottom: 2 },
  title:          { fontSize: 26, fontWeight: '800', color: '#e2e8f0' },
  countBadge:     { backgroundColor: '#0d1826', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: '#1e2d3d' },
  countText:      { fontSize: 16, fontWeight: '700', color: '#94a3b8' },

  digestCard:     { backgroundColor: '#0b1420', borderRadius: 14, marginHorizontal: 16, marginBottom: 12, padding: 14, borderWidth: 1 },
  digestTop:      { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  digestTitleBlock:{ flex: 1 },
  digestEyebrow:  { fontSize: 10, color: '#64748b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle:    { fontSize: 18, fontWeight: '800', color: '#e2e8f0' },
  digestDetail:   { fontSize: 12, lineHeight: 17, color: '#94a3b8', marginTop: 3 },
  digestRate:     { minWidth: 58, height: 42, borderRadius: 10, flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', paddingTop: 6 },
  digestRateValue:{ fontSize: 22, fontWeight: '900' },
  digestRateSuffix:{ fontSize: 12, color: '#64748b', fontWeight: '700' },
  digestStats:    { flexDirection: 'row', marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#132235' },
  digestStat:     { flex: 1, alignItems: 'center' },
  digestStatValue:{ fontSize: 14, fontWeight: '800', color: '#e2e8f0' },
  digestStatLabel:{ fontSize: 9, color: '#64748b', marginTop: 3, fontWeight: '700' },

  filterBar:      { flexDirection: 'row', paddingHorizontal: 16, gap: 8, marginBottom: 12 },
  filterBtn:      { flex: 1, alignItems: 'center', paddingHorizontal: 8, paddingVertical: 7, borderRadius: 8, backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d' },
  filterBtnActive:{ backgroundColor: '#0c2740', borderColor: '#0ea5e9' },
  filterText:     { fontSize: 13, color: '#475569', fontWeight: '600' },
  filterTextActive:{ color: '#0ea5e9' },
  filterCount:    { fontSize: 11, color: '#334155', fontWeight: '800', marginTop: 2 },
  filterCountActive:{ color: '#7dd3fc' },

  list:           { paddingHorizontal: 16, paddingBottom: 16 },

  card:           { backgroundColor: '#0d1826', borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#1e2d3d' },
  cardTop:        { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  tickerWrap:     { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ticker:         { fontSize: 18, fontWeight: '800', color: '#e2e8f0' },
  typePill:       { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 },
  typeText:       { fontSize: 11, fontWeight: '700' },
  statusPill:     { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 6 },
  statusDot:      { width: 6, height: 6, borderRadius: 3 },
  statusText:     { fontSize: 11, fontWeight: '700' },

  grid:           { flexDirection: 'row', marginBottom: 12, gap: 4 },
  gridItem:       { flex: 1, backgroundColor: '#111c2a', borderRadius: 7, padding: 8, alignItems: 'center' },
  gridLabel:      { fontSize: 9, color: '#334155', fontWeight: '700', letterSpacing: 1, marginBottom: 3 },
  gridValue:      { fontSize: 14, fontWeight: '700', color: '#e2e8f0' },

  cardBottom:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  channelRow:     { flexDirection: 'row', alignItems: 'center', gap: 5 },
  channelText:    { fontSize: 11, color: '#334155' },
  timestamp:      { fontSize: 10, color: '#334155' },

  empty:          { alignItems: 'center', paddingVertical: 64, gap: 10 },
  emptyTitle:     { fontSize: 18, fontWeight: '700', color: '#1e2d3d' },
  emptySub:       { fontSize: 13, color: '#1e2d3d' },
});
