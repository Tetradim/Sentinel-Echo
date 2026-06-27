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
  DigestAlert,
  filterAlerts,
  getAlertActionSummary,
  getAlertExecutionStatus,
  getAlertReasonLabel,
  getAlertSourceSummary,
  getExitTriggerLabel,
  summarizeAlerts,
} from '../utils/alertDigest';

// Demo alerts
const DEMO_ALERTS: AlertItem[] = [
  { id: '1', ticker: 'AAPL', strike: 175, option_type: 'CALL', expiration: '2024-05-17', entry_price: 3.50, alert_type: 'buy', raw_message: 'BTO AAPL 175C May 17', source_name: 'MikesTrades mirror-alerts', author_name: 'MikeInvesting', channel_name: 'alerts', received_at: '2024-04-18T10:30:00Z', processed: true, trade_executed: true, trade_result: 'filled' },
  { id: '2', ticker: 'TSLA', strike: 150, option_type: 'PUT', expiration: '2024-05-17', entry_price: 2.80, alert_type: 'buy', raw_message: 'BTO TSLA 150P May 17', source_name: 'alerts', author_name: 'Analyst', channel_name: 'alerts', received_at: '2024-04-18T09:15:00Z', processed: true, trade_executed: true, trade_result: 'filled' },
  { id: '3', ticker: 'NVDA', strike: 800, option_type: 'CALL', expiration: '2024-04-19', entry_price: 12.50, alert_type: 'buy', raw_message: 'BTO NVDA 800C Apr 19', source_name: 'alerts', author_name: 'Analyst', channel_name: 'alerts', received_at: '2024-04-17T14:20:00Z', processed: true, trade_executed: false, skip_reason: 'blocked: max positions per ticker', trade_result: 'skipped: blocked: max positions per ticker' },
  { id: '4', ticker: 'MSFT', strike: 380, option_type: 'CALL', expiration: '2024-05-17', entry_price: 5.20, alert_type: 'sell', sell_percentage: 80, exit_trigger: 'sell_alert', raw_message: 'SOLD 80% MSFT 380C May 17', source_name: 'MikesTrades mirror-alerts', author_name: 'MikeInvesting', channel_name: 'alerts', received_at: '2024-04-17T11:45:00Z', processed: true, trade_executed: true, trade_result: 'sold 80%' },
  { id: '5', ticker: 'GOOGL', strike: 155, option_type: 'CALL', expiration: '2024-05-17', entry_price: 2.10, alert_type: 'buy', raw_message: 'BTO GOOGL 155C May 17', source_name: 'alerts', author_name: 'Analyst', channel_name: 'alerts', received_at: '2024-04-17T08:30:00Z', processed: true, trade_executed: true, trade_result: 'filled' },
  { id: '6', ticker: 'META', strike: 480, option_type: 'CALL', expiration: '2024-05-17', entry_price: 8.50, alert_type: 'buy', raw_message: 'BTO META 480C May 17', source_name: 'alerts', author_name: 'Analyst', channel_name: 'alerts', received_at: '2024-04-16T16:00:00Z', processed: true, trade_executed: true, trade_result: 'filled' },
];

interface AlertItem extends DigestAlert {
  id: string; ticker?: string | null; strike?: number | null; option_type?: string | null;
  expiration?: string | null; entry_price?: number | null; raw_message?: string | null;
  channel_name?: string | null; received_at?: string | null;
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
    '#68779b';

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
        <DigestStat label="Skipped" value={String(digest.skipped)} color={digest.skipped ? '#f59e0b' : undefined} />
        <DigestStat label="Unparsed" value={String(digest.unparsed)} color={digest.unparsed ? '#ef4444' : undefined} />
        <DigestStat label="Exits" value={String(digest.exits)} color={digest.exits ? '#14b8a6' : undefined} />
      </View>
    </View>
  );
}

export default function AlertsScreen() {
  const [alerts, setAlerts]     = useState<AlertItem[]>([]);
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter]     = useState<AlertFilter>('all');
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchAlerts = useCallback(async () => {
    if (DEMO_MODE) {
      setAlerts(DEMO_ALERTS);
      setLoadError(null);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    try {
      const r = await api.get(`${BACKEND_URL}/api/alerts?limit=200`);
      setAlerts(r.data);
      setLoadError(null);
    } catch (e) { 
      console.error(e);
      setLoadError('Live alerts could not load. Check the backend connection and refresh.');
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);
  const onRefresh = useCallback(() => { setRefreshing(true); fetchAlerts(); }, [fetchAlerts]);
  const retryFetchAlerts = useCallback(() => {
    if (alerts.length === 0) setLoading(true);
    else setRefreshing(true);
    fetchAlerts();
  }, [alerts.length, fetchAlerts]);

  const digest = summarizeAlerts(alerts);
  const filterOptions: { key: AlertFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: digest.total },
    { key: 'executed', label: 'Executed', count: digest.executed },
    { key: 'review', label: 'Review', count: digest.needsReview },
    { key: 'skipped', label: 'Skipped', count: digest.skipped },
    { key: 'unparsed', label: 'Unparsed', count: digest.unparsed },
    { key: 'exits', label: 'Exits', count: digest.exits },
  ];
  const filtered = filterAlerts(alerts, filter);

  const fmt = (d?: string | null) => d ? new Date(d).toLocaleString() : '-';
  const formatMoney = (value?: number | string | null) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric > 0 ? `$${numeric.toFixed(2)}` : '-';
  };

  const renderItem = ({ item: a }: { item: AlertItem }) => {
    const status = getAlertExecutionStatus(a);
    const source = getAlertSourceSummary(a);
    const action = getAlertActionSummary(a);
    const reason = getAlertReasonLabel(a);
    const exitTrigger = getExitTriggerLabel(a);
    const ticker = String(a.ticker || 'UNKNOWN').toUpperCase().replace(/^\$/, '');
    const optionType = String(a.option_type || '').toUpperCase();
    const typeColor = optionType === 'PUT' ? '#f87171' : '#4ade80';

    return (
      <View style={s.card}>
        <View style={s.cardTop}>
          <View style={s.tickerWrap}>
            <Text style={s.ticker}>${ticker}</Text>
            {optionType ? (
              <View style={[s.typePill, { backgroundColor: optionType === 'CALL' ? '#14532d' : '#450a0a' }]}>
                <Text style={[s.typeText, { color: typeColor }]}>{optionType}</Text>
              </View>
            ) : null}
            <View style={s.actionPill}>
              <Text style={s.actionText}>{action}</Text>
            </View>
          </View>
          <View style={[s.statusPill, { backgroundColor: status.backgroundColor }]}>
            <View style={[s.statusDot, { backgroundColor: status.color }]} />
            <Text style={[s.statusText, { color: status.color }]}>{status.label}</Text>
          </View>
        </View>

      <View style={s.grid}>
        <View style={s.gridItem}>
          <Text style={s.gridLabel}>STRIKE</Text>
          <Text style={s.gridValue}>{a.strike ? `$${a.strike}` : '-'}</Text>
        </View>
        <View style={s.gridItem}>
          <Text style={s.gridLabel}>EXPIRY</Text>
          <Text style={s.gridValue}>{a.expiration || '-'}</Text>
        </View>
        <View style={s.gridItem}>
          <Text style={s.gridLabel}>{exitTrigger ? 'PRICE' : 'ENTRY'}</Text>
          <Text style={s.gridValue}>{formatMoney(a.entry_price)}</Text>
        </View>
      </View>

      <View style={s.auditBlock}>
        <View style={s.auditRow}>
          <Text style={s.auditLabel}>SOURCE</Text>
          <Text style={s.auditValue}>{source}</Text>
        </View>
        {exitTrigger ? (
          <View style={s.auditRow}>
            <Text style={s.auditLabel}>EXIT TRIGGER</Text>
            <Text style={[s.auditValue, s.exitValue]}>{exitTrigger}</Text>
          </View>
        ) : null}
        {reason ? (
          <View style={s.auditRow}>
            <Text style={s.auditLabel}>REASON</Text>
            <Text style={s.auditValue}>{reason}</Text>
          </View>
        ) : null}
      </View>

      <View style={s.cardBottom}>
        {a.channel_name ? (
          <View style={s.channelRow}>
            <Ionicons name="chatbubble-outline" size={12} color="#68779b" />
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

      {loadError && (
        <View style={s.errorBanner}>
          <Ionicons name="warning-outline" size={16} color="#f59e0b" />
          <Text style={s.errorBannerText}>{loadError}</Text>
          <TouchableOpacity
            style={s.errorBannerRetry}
            onPress={retryFetchAlerts}
            accessibilityRole="button"
          >
            <Ionicons name="refresh" size={13} color="#050416" />
            <Text style={s.errorBannerRetryText}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

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
        <View style={s.centered}><ActivityIndicator size="large" color="#f43f5e" /></View>
      ) : (
        <FlatList
          data={filtered}
          renderItem={renderItem}
          keyExtractor={i => i.id}
          contentContainerStyle={s.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#f43f5e" />}
          ListEmptyComponent={
            <View style={s.empty}>
              <Ionicons name="notifications-off-outline" size={48} color="#29213a" />
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
  container:      { flex: 1, backgroundColor: '#050416' },
  centered:       { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 },
  eyebrow:        { fontSize: 10, color: '#f43f5e', fontWeight: '700', letterSpacing: 2, marginBottom: 2 },
  title:          { fontSize: 26, fontWeight: '800', color: '#edf3ff' },
  countBadge:     { backgroundColor: 'rgba(16, 9, 28, 0.82)', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: '#29213a' },
  countText:      { fontSize: 16, fontWeight: '700', color: '#aec0e5' },

  digestCard:     { backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 14, marginHorizontal: 16, marginBottom: 12, padding: 14, borderWidth: 1 },
  digestTop:      { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  digestTitleBlock:{ flex: 1 },
  digestEyebrow:  { fontSize: 10, color: '#68779b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle:    { fontSize: 18, fontWeight: '800', color: '#edf3ff' },
  digestDetail:   { fontSize: 12, lineHeight: 17, color: '#aec0e5', marginTop: 3 },
  digestRate:     { minWidth: 58, height: 42, borderRadius: 10, flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', paddingTop: 6 },
  digestRateValue:{ fontSize: 22, fontWeight: '900' },
  digestRateSuffix:{ fontSize: 12, color: '#68779b', fontWeight: '700' },
  digestStats:    { flexDirection: 'row', marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: 'rgba(41, 33, 58, 0.82)' },
  digestStat:     { flex: 1, alignItems: 'center' },
  digestStatValue:{ fontSize: 14, fontWeight: '800', color: '#edf3ff' },
  digestStatLabel:{ fontSize: 9, color: '#68779b', marginTop: 3, fontWeight: '700' },

  errorBanner:    { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginBottom: 10, padding: 10, borderRadius: 8, backgroundColor: '#1c1500', borderWidth: 1, borderColor: '#92400e' },
  errorBannerText:{ flex: 1, fontSize: 12, color: '#f59e0b', fontWeight: '600' },
  errorBannerRetry:{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#f59e0b', paddingHorizontal: 9, paddingVertical: 6, borderRadius: 6 },
  errorBannerRetryText:{ fontSize: 11, color: '#050416', fontWeight: '900' },

  filterBar:      { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 16, gap: 8, marginBottom: 12 },
  filterBtn:      { minWidth: 82, flexGrow: 1, alignItems: 'center', paddingHorizontal: 8, paddingVertical: 7, borderRadius: 8, backgroundColor: 'rgba(16, 9, 28, 0.82)', borderWidth: 1, borderColor: '#29213a' },
  filterBtnActive:{ backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  filterText:     { fontSize: 13, color: '#68779b', fontWeight: '600' },
  filterTextActive:{ color: '#f43f5e' },
  filterCount:    { fontSize: 11, color: '#68779b', fontWeight: '800', marginTop: 2 },
  filterCountActive:{ color: '#fb7185' },

  list:           { paddingHorizontal: 16, paddingBottom: 16 },

  card:           { backgroundColor: 'rgba(16, 9, 28, 0.82)', borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#29213a' },
  cardTop:        { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  tickerWrap:     { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ticker:         { fontSize: 18, fontWeight: '800', color: '#edf3ff' },
  typePill:       { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 },
  typeText:       { fontSize: 11, fontWeight: '700' },
  actionPill:     { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5, backgroundColor: 'rgba(20, 184, 166, 0.14)', borderWidth: 1, borderColor: 'rgba(20, 184, 166, 0.3)' },
  actionText:     { fontSize: 10, fontWeight: '800', color: '#5eead4' },
  statusPill:     { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 6 },
  statusDot:      { width: 6, height: 6, borderRadius: 3 },
  statusText:     { fontSize: 11, fontWeight: '700' },

  grid:           { flexDirection: 'row', marginBottom: 12, gap: 4 },
  gridItem:       { flex: 1, backgroundColor: 'rgba(21, 16, 33, 0.72)', borderRadius: 7, padding: 8, alignItems: 'center' },
  gridLabel:      { fontSize: 9, color: '#68779b', fontWeight: '700', letterSpacing: 1, marginBottom: 3 },
  gridValue:      { fontSize: 14, fontWeight: '700', color: '#edf3ff' },

  auditBlock:     { borderTopWidth: 1, borderTopColor: 'rgba(41, 33, 58, 0.82)', paddingTop: 10, marginBottom: 10, gap: 7 },
  auditRow:       { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  auditLabel:     { width: 78, fontSize: 9, color: '#68779b', fontWeight: '800', letterSpacing: 0.8 },
  auditValue:     { flex: 1, fontSize: 11, lineHeight: 15, color: '#aec0e5', fontWeight: '600' },
  exitValue:      { color: '#5eead4' },

  cardBottom:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  channelRow:     { flexDirection: 'row', alignItems: 'center', gap: 5 },
  channelText:    { fontSize: 11, color: '#68779b' },
  timestamp:      { fontSize: 10, color: '#68779b' },

  empty:          { alignItems: 'center', paddingVertical: 64, gap: 10 },
  emptyTitle:     { fontSize: 18, fontWeight: '700', color: '#29213a' },
  emptySub:       { fontSize: 13, color: '#29213a' },
});
