import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  RefreshControl, ActivityIndicator, Modal, TextInput, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../utils/api';
import { BACKEND_URL, DEMO_MODE } from '../constants/config';
import { BROKER_COLORS, BROKER_NAMES } from '../constants/brokers';
import { validatePrice, validatePercentage, formatDate, formatPnL, getPnLColor } from '../utils/format';
import {
  filterPositions,
  PositionDigest,
  PositionFilter,
  summarizePositions,
} from '../utils/positionDigest';

interface Position {
  id: string;
  ticker: string;
  strike: number;
  option_type: string;
  expiration: string;
  entry_price: number;
  current_price: number | null;
  original_quantity: number;
  remaining_quantity: number;
  total_cost: number;
  broker: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
  realized_pnl: number;
  unrealized_pnl: number;
  simulated: boolean;
}

interface ExitSubmission {
  status: 'submitted' | 'already_working' | 'filled' | string;
  message?: string;
  position_id: string;
  trade_id?: string;
  order_id?: string;
  client_order_id?: string;
  broker?: string;
  requested_quantity?: number;
  filled_quantity?: number;
  submitted_limit_price?: number;
  realized_pnl?: number;
  simulated?: boolean;
}

const DEMO_POSITIONS: Position[] = [
  {
    id: 'demo-aapl', ticker: 'AAPL', strike: 175, option_type: 'CALL',
    expiration: '2026-08-21', entry_price: 3.5, current_price: 4.25,
    original_quantity: 5, remaining_quantity: 5, total_cost: 1750,
    broker: 'alpaca', status: 'open', opened_at: new Date().toISOString(),
    closed_at: null, realized_pnl: 0, unrealized_pnl: 375, simulated: true,
  },
];

function ExposureStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return <View style={s.digestStat}><Text style={[s.digestStatValue, color ? { color } : {}]}>{value}</Text><Text style={s.digestStatLabel}>{label}</Text></View>;
}

function PositionBriefing({ digest }: { digest: PositionDigest }) {
  const toneColor = digest.primaryStatus.tone === 'live' ? '#22c55e' : digest.primaryStatus.tone === 'attention' ? '#f59e0b' : '#64748b';
  return (
    <View style={[s.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={s.digestTop}>
        <View style={s.digestTitleBlock}>
          <Text style={s.digestEyebrow}>EXPOSURE WATCH</Text>
          <Text style={s.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={s.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[s.digestExposure, { backgroundColor: toneColor + '18' }]}>
          <Text style={[s.digestExposureValue, { color: toneColor }]}>${digest.openExposure.toLocaleString()}</Text>
          <Text style={s.digestExposureLabel}>exposure</Text>
        </View>
      </View>
      <View style={s.digestStats}>
        <ExposureStat label="Expiry" value={String(digest.expiringSoon)} color={digest.expiringSoon ? '#f59e0b' : undefined} />
        <ExposureStat label="Losing" value={String(digest.losingOpen)} color={digest.losingOpen ? '#ef4444' : undefined} />
        <ExposureStat label="Partial" value={String(digest.partial)} color={digest.partial ? '#fb923c' : undefined} />
        <ExposureStat label="Largest" value={digest.topExposureTicker || '-'} />
      </View>
    </View>
  );
}

export default function PositionsScreen() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [filter, setFilter] = useState<PositionFilter>('open');
  const [selected, setSelected] = useState<Position | null>(null);
  const [showSell, setShowSell] = useState(false);
  const [sellPct, setSellPct] = useState('50');
  const [exitPrice, setExitPrice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [lastSubmission, setLastSubmission] = useState<ExitSubmission | null>(null);

  const fetchPositions = useCallback(async () => {
    if (DEMO_MODE) {
      setPositions(DEMO_POSITIONS);
      setLoadError('');
      setLoading(false);
      setRefreshing(false);
      return;
    }
    try {
      const response = await api.get(`${BACKEND_URL}/api/positions`);
      setPositions(Array.isArray(response.data) ? response.data : []);
      setLoadError('');
    } catch (error: any) {
      console.error(error);
      setPositions([]);
      setLoadError(error?.response?.data?.detail || error?.message || 'Positions could not be loaded from Echo.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchPositions(); }, [fetchPositions]);
  const onRefresh = useCallback(() => { setRefreshing(true); fetchPositions(); }, [fetchPositions]);

  const openSell = (position: Position) => {
    setSelected(position);
    setSellPct('50');
    setExitPrice((position.current_price ?? position.entry_price).toString());
    setShowSell(true);
  };

  const sellPosition = async () => {
    if (!selected) return;
    const priceResult = validatePrice(exitPrice);
    const percentageResult = validatePercentage(sellPct, { min: 1, max: 100 });
    if (priceResult.error) { Alert.alert('Invalid reference price', priceResult.error); return; }
    if (percentageResult.error) { Alert.alert('Invalid percentage', percentageResult.error); return; }

    setSubmitting(true);
    try {
      const response = await api.post(`${BACKEND_URL}/api/positions/${selected.id}/sell`, null, {
        params: {
          sell_percentage: percentageResult.value,
          exit_price: priceResult.value,
        },
      });
      const result = response.data as ExitSubmission;
      setLastSubmission(result);
      const orderReference = result.order_id || result.client_order_id || 'pending broker reconciliation';
      const title = result.status === 'filled' ? 'Exit filled' : result.status === 'already_working' ? 'Exit already working' : 'Exit submitted';
      const details = result.status === 'filled'
        ? `${result.requested_quantity || 0} contract(s) filled\nRealized P&L: ${formatPnL(result.realized_pnl || 0)}`
        : `${result.requested_quantity || 0} contract(s) routed to ${result.broker || selected.broker}\nOrder: ${orderReference}\nThe position will change only after broker fills.`;
      Alert.alert(title, details);
      setShowSell(false);
      setSelected(null);
      await fetchPositions();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      Alert.alert('Exit not confirmed', typeof detail === 'string' ? detail : detail?.message || 'The exit could not be confirmed. Review live operations before retrying.');
    } finally {
      setSubmitting(false);
    }
  };

  const openPositions = positions.filter((position) => position.status === 'open' || position.status === 'partial');
  const totalUnrealized = openPositions.reduce((sum, position) => sum + (position.unrealized_pnl || 0), 0);
  const totalRealized = positions.reduce((sum, position) => sum + (position.realized_pnl || 0), 0);
  const digest = summarizePositions(positions);
  const filteredPositions = filterPositions(positions, filter);
  const filterOptions: { key: PositionFilter; label: string; count: number }[] = [
    { key: 'open', label: 'Open', count: digest.open },
    { key: 'all', label: 'All', count: digest.total },
    { key: 'closed', label: 'Closed', count: digest.closed },
    { key: 'attention', label: 'Watch', count: filterPositions(positions, 'attention').length },
  ];

  const renderItem = ({ item: position }: { item: Position }) => {
    const brokerColor = BROKER_COLORS[position.broker] || '#64748b';
    const brokerName = BROKER_NAMES[position.broker] || position.broker;
    const isOpen = position.status !== 'closed';
    const current = position.current_price ?? position.entry_price;
    const unrealized = position.unrealized_pnl || ((current - position.entry_price) * position.remaining_quantity * 100);
    const pnlValue = isOpen ? unrealized : position.realized_pnl;
    const pnlColor = getPnLColor(pnlValue);

    return (
      <View style={[s.card, !isOpen && s.cardClosed]}>
        <View style={s.cardTop}>
          <View style={s.tickerRow}>
            <Text style={s.ticker}>${position.ticker}</Text>
            <View style={[s.typePill, { backgroundColor: position.option_type === 'CALL' ? '#14532d' : '#450a0a' }]}>
              <Text style={[s.typeText, { color: position.option_type === 'CALL' ? '#4ade80' : '#f87171' }]}>{position.option_type}</Text>
            </View>
            {position.simulated && <View style={s.simPill}><Text style={s.simText}>SIM</Text></View>}
          </View>
          <View style={s.badges}>
            <View style={[s.badge, { backgroundColor: brokerColor + '22', borderColor: brokerColor + '44', borderWidth: 1 }]}><Text style={[s.badgeText, { color: brokerColor }]}>{brokerName}</Text></View>
            <View style={[s.badge, { backgroundColor: position.status === 'open' ? '#14532d' : position.status === 'partial' ? '#422006' : '#1e2d3d' }]}><Text style={[s.badgeText, { color: position.status === 'open' ? '#4ade80' : position.status === 'partial' ? '#fb923c' : '#64748b' }]}>{position.status.toUpperCase()}</Text></View>
          </View>
        </View>

        <View style={s.grid}>
          {[
            { label: 'STRIKE', value: `$${position.strike}` },
            { label: 'ENTRY', value: `$${position.entry_price.toFixed(2)}` },
            { label: 'CURRENT', value: `$${current.toFixed(2)}` },
            { label: 'QTY', value: `${position.remaining_quantity}/${position.original_quantity}` },
          ].map(({ label, value }) => <View key={label} style={s.gridCell}><Text style={s.gridLabel}>{label}</Text><Text style={s.gridValue}>{value}</Text></View>)}
        </View>

        <View style={[s.pnlBar, { backgroundColor: (pnlValue || 0) >= 0 ? '#14280a' : '#2d1515' }]}>
          <Text style={s.pnlLabel}>{isOpen ? 'Unrealized' : 'Realized'}</Text>
          <View style={s.pnlRight}><Ionicons name={(pnlValue || 0) >= 0 ? 'trending-up' : 'trending-down'} size={14} color={pnlColor} /><Text style={[s.pnlValue, { color: pnlColor }]}>{formatPnL(pnlValue)}</Text></View>
        </View>

        <View style={s.footer}>
          <View style={s.footerLeft}><Ionicons name="calendar-outline" size={12} color="#334155" /><Text style={s.footerText}>Exp: {position.expiration}</Text><Text style={s.footerDot}>·</Text><Text style={s.footerText}>{formatDate(isOpen ? position.opened_at : (position.closed_at || position.opened_at))}</Text></View>
          {isOpen && <TouchableOpacity style={s.sellBtn} onPress={() => openSell(position)}><Text style={s.sellBtnText}>Submit Exit</Text></TouchableOpacity>}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <View><Text style={s.eyebrow}>PORTFOLIO</Text><Text style={s.title}>Positions</Text></View>
        <View style={s.headerStats}><Text style={[s.headerPnl, { color: getPnLColor(totalUnrealized) }]}>{formatPnL(totalUnrealized)}</Text><Text style={s.headerPnlSub}>unrealized · {openPositions.length} open</Text></View>
      </View>

      {loadError ? <View style={s.errorCard}><Ionicons name="cloud-offline-outline" size={18} color="#f87171" /><View style={{ flex: 1 }}><Text style={s.errorTitle}>Backend data unavailable</Text><Text style={s.errorText}>{loadError}</Text></View><TouchableOpacity onPress={fetchPositions}><Text style={s.retryText}>Retry</Text></TouchableOpacity></View> : null}
      {lastSubmission && !loadError ? <View style={s.submissionCard}><Ionicons name="receipt-outline" size={18} color="#38bdf8" /><View style={{ flex: 1 }}><Text style={s.submissionTitle}>{lastSubmission.status.replaceAll('_', ' ')}</Text><Text style={s.submissionText}>{lastSubmission.message || lastSubmission.order_id || lastSubmission.client_order_id}</Text></View></View> : null}

      <PositionBriefing digest={digest} />
      <View style={s.strip}>
        <View style={s.stripCell}><Text style={[s.stripValue, { color: getPnLColor(totalUnrealized) }]}>{formatPnL(totalUnrealized)}</Text><Text style={s.stripLabel}>Unrealized</Text></View><View style={s.stripDiv} />
        <View style={s.stripCell}><Text style={[s.stripValue, { color: getPnLColor(totalRealized) }]}>{formatPnL(totalRealized)}</Text><Text style={s.stripLabel}>Realized</Text></View><View style={s.stripDiv} />
        <View style={s.stripCell}><Text style={s.stripValue}>{openPositions.length}</Text><Text style={s.stripLabel}>Open</Text></View><View style={s.stripDiv} />
        <View style={s.stripCell}><Text style={s.stripValue}>{positions.filter((position) => position.status === 'closed').length}</Text><Text style={s.stripLabel}>Closed</Text></View>
      </View>

      <View style={s.filterBar}>{filterOptions.map(({ key, label, count }) => <TouchableOpacity key={key} style={[s.filterBtn, filter === key && s.filterBtnActive]} onPress={() => setFilter(key)}><Text style={[s.filterText, filter === key && s.filterTextActive]}>{label}</Text><Text style={[s.filterCount, filter === key && s.filterCountActive]}>{count}</Text></TouchableOpacity>)}</View>

      {loading ? <View style={s.centered}><ActivityIndicator size="large" color="#0ea5e9" /></View> : <FlatList data={filteredPositions} renderItem={renderItem} keyExtractor={(item) => item.id} contentContainerStyle={s.list} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0ea5e9" />} ListEmptyComponent={<View style={s.empty}><Ionicons name="briefcase-outline" size={48} color="#1e2d3d" /><Text style={s.emptyTitle}>{loadError ? 'No broker-backed data' : 'No positions'}</Text></View>} />}

      <Modal visible={showSell} transparent animationType="fade" onRequestClose={() => setShowSell(false)}>
        <View style={s.overlay}><View style={s.modal}>
          <Text style={s.modalTitle}>Submit Position Exit</Text>
          <Text style={s.modalSub}>{selected?.ticker} {selected?.strike} {selected?.option_type} · {selected?.remaining_quantity} contract(s) · {selected?.broker}</Text>
          <Text style={s.modalLabel}>Exit Percentage</Text>
          <View style={s.pctRow}>{['25', '50', '75', '100'].map((percentage) => <TouchableOpacity key={percentage} style={[s.pctBtn, sellPct === percentage && s.pctBtnActive]} onPress={() => setSellPct(percentage)}><Text style={[s.pctText, sellPct === percentage && s.pctTextActive]}>{percentage}%</Text></TouchableOpacity>)}</View>
          <TextInput style={s.modalInput} value={sellPct} onChangeText={setSellPct} keyboardType="decimal-pad" placeholder="%" placeholderTextColor="#334155" />
          <Text style={s.modalLabel}>Reference Price</Text>
          <Text style={s.modalHint}>Echo will fetch the current broker bid/ask and choose the live limit price. This value is only the reference/slippage boundary.</Text>
          <TextInput style={s.modalInput} value={exitPrice} onChangeText={setExitPrice} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor="#334155" />
          <View style={s.modalBtns}><TouchableOpacity style={s.modalCancel} onPress={() => setShowSell(false)}><Text style={s.modalCancelText}>Cancel</Text></TouchableOpacity><TouchableOpacity style={s.modalConfirm} onPress={sellPosition} disabled={submitting}>{submitting ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.modalConfirmText}>Submit {sellPct}% Exit</Text>}</TouchableOpacity></View>
        </View></View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#080f1a' }, centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 }, eyebrow: { fontSize: 10, color: '#0ea5e9', fontWeight: '700', letterSpacing: 2, marginBottom: 2 }, title: { fontSize: 26, fontWeight: '800', color: '#e2e8f0' }, headerStats: { alignItems: 'flex-end' }, headerPnl: { fontSize: 20, fontWeight: '800' }, headerPnlSub: { fontSize: 11, color: '#475569', marginTop: 1 },
  errorCard: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 16, marginBottom: 10, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: '#7f1d1d', backgroundColor: '#2d1515' }, errorTitle: { color: '#fecaca', fontWeight: '800' }, errorText: { color: '#fca5a5', fontSize: 11, marginTop: 2 }, retryText: { color: '#38bdf8', fontWeight: '800' },
  submissionCard: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 16, marginBottom: 10, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: '#0c4a6e', backgroundColor: '#082f49' }, submissionTitle: { color: '#7dd3fc', fontWeight: '800', textTransform: 'capitalize' }, submissionText: { color: '#bae6fd', fontSize: 11, marginTop: 2 },
  strip: { flexDirection: 'row', marginHorizontal: 16, backgroundColor: '#0d1826', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#1e2d3d', alignItems: 'center' }, stripCell: { flex: 1, alignItems: 'center' }, stripValue: { fontSize: 14, fontWeight: '800', color: '#e2e8f0' }, stripLabel: { fontSize: 9, color: '#475569', marginTop: 3, fontWeight: '600', letterSpacing: 0.5 }, stripDiv: { width: 1, height: 30, backgroundColor: '#1e2d3d' },
  digestCard: { backgroundColor: '#0b1420', borderRadius: 14, marginHorizontal: 16, marginBottom: 10, padding: 14, borderWidth: 1 }, digestTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }, digestTitleBlock: { flex: 1 }, digestEyebrow: { fontSize: 10, color: '#64748b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 }, digestTitle: { fontSize: 18, fontWeight: '800', color: '#e2e8f0' }, digestDetail: { fontSize: 12, lineHeight: 17, color: '#94a3b8', marginTop: 3 }, digestExposure: { minWidth: 94, height: 42, borderRadius: 10, alignItems: 'center', justifyContent: 'center' }, digestExposureValue: { fontSize: 17, fontWeight: '900' }, digestExposureLabel: { fontSize: 10, color: '#64748b', fontWeight: '700', marginTop: 1 }, digestStats: { flexDirection: 'row', marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#132235' }, digestStat: { flex: 1, alignItems: 'center' }, digestStatValue: { fontSize: 14, fontWeight: '800', color: '#e2e8f0' }, digestStatLabel: { fontSize: 9, color: '#64748b', marginTop: 3, fontWeight: '700' },
  filterBar: { flexDirection: 'row', paddingHorizontal: 16, gap: 8, marginBottom: 10 }, filterBtn: { flex: 1, alignItems: 'center', paddingHorizontal: 8, paddingVertical: 7, borderRadius: 8, backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d' }, filterBtnActive: { backgroundColor: '#0c2740', borderColor: '#0ea5e9' }, filterText: { fontSize: 13, color: '#475569', fontWeight: '600' }, filterTextActive: { color: '#0ea5e9' }, filterCount: { fontSize: 11, color: '#334155', fontWeight: '800', marginTop: 2 }, filterCountActive: { color: '#7dd3fc' },
  list: { paddingHorizontal: 16, paddingBottom: 16 }, card: { backgroundColor: '#0d1826', borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#1e2d3d' }, cardClosed: { opacity: 0.7 }, cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }, tickerRow: { flexDirection: 'row', alignItems: 'center', gap: 7 }, ticker: { fontSize: 18, fontWeight: '800', color: '#e2e8f0' }, typePill: { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 }, typeText: { fontSize: 11, fontWeight: '700' }, simPill: { backgroundColor: '#2d1f5e', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }, simText: { fontSize: 10, color: '#a78bfa', fontWeight: '700' }, badges: { flexDirection: 'row', gap: 6 }, badge: { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 }, badgeText: { fontSize: 10, fontWeight: '700' },
  grid: { flexDirection: 'row', gap: 4, marginBottom: 10 }, gridCell: { flex: 1, backgroundColor: '#111c2a', borderRadius: 7, padding: 8, alignItems: 'center' }, gridLabel: { fontSize: 9, color: '#334155', fontWeight: '700', letterSpacing: 1, marginBottom: 3 }, gridValue: { fontSize: 13, fontWeight: '700', color: '#e2e8f0' }, pnlBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 10, borderRadius: 8, marginBottom: 10 }, pnlLabel: { fontSize: 11, color: '#64748b', fontWeight: '600' }, pnlRight: { flexDirection: 'row', alignItems: 'center', gap: 5 }, pnlValue: { fontSize: 15, fontWeight: '800' }, footer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, footerLeft: { flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1 }, footerText: { fontSize: 10, color: '#334155' }, footerDot: { fontSize: 10, color: '#1e2d3d' }, sellBtn: { backgroundColor: '#0c2740', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 7, borderWidth: 1, borderColor: '#0ea5e9' }, sellBtnText: { fontSize: 12, color: '#0ea5e9', fontWeight: '700' }, empty: { alignItems: 'center', paddingVertical: 64, gap: 10 }, emptyTitle: { fontSize: 18, fontWeight: '700', color: '#334155' },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', alignItems: 'center', justifyContent: 'center', padding: 24 }, modal: { backgroundColor: '#0d1826', borderRadius: 16, padding: 24, width: '100%', maxWidth: 400, borderWidth: 1, borderColor: '#1e2d3d' }, modalTitle: { fontSize: 18, fontWeight: '800', color: '#e2e8f0', marginBottom: 4 }, modalSub: { fontSize: 13, color: '#475569', marginBottom: 20 }, modalLabel: { fontSize: 12, color: '#64748b', fontWeight: '600', marginBottom: 8 }, modalHint: { fontSize: 11, color: '#475569', lineHeight: 15, marginTop: -4, marginBottom: 8 }, modalInput: { backgroundColor: '#111c2a', borderRadius: 9, padding: 13, color: '#e2e8f0', fontSize: 16, fontWeight: '700', borderWidth: 1, borderColor: '#1e2d3d', marginBottom: 16 }, pctRow: { flexDirection: 'row', gap: 8, marginBottom: 10 }, pctBtn: { flex: 1, padding: 10, borderRadius: 8, backgroundColor: '#1e2d3d', alignItems: 'center' }, pctBtnActive: { backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9' }, pctText: { fontSize: 13, color: '#64748b', fontWeight: '700' }, pctTextActive: { color: '#0ea5e9' }, modalBtns: { flexDirection: 'row', gap: 10, marginTop: 4 }, modalCancel: { flex: 1, padding: 14, borderRadius: 9, backgroundColor: '#1e2d3d', alignItems: 'center' }, modalCancelText: { color: '#64748b', fontWeight: '700' }, modalConfirm: { flex: 1, padding: 14, borderRadius: 9, backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9', alignItems: 'center' }, modalConfirmText: { color: '#0ea5e9', fontWeight: '700' },
});
