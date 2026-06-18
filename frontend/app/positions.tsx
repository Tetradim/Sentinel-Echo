import React, { useEffect, useState, useCallback } from 'react';
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

// Demo data for when backend is unavailable
const DEMO_POSITIONS: Position[] = [
  {
    id: '1', ticker: 'AAPL', strike: 175, option_type: 'CALL',
    expiration: '2024-05-17', entry_price: 3.50, current_price: 4.25,
    original_quantity: 5, remaining_quantity: 5, total_cost: 1750,
    broker: 'IBKR', status: 'open', opened_at: '2024-04-15T10:30:00Z',
    closed_at: null, realized_pnl: 0, unrealized_pnl: 375, simulated: false
  },
  {
    id: '2', ticker: 'TSLA', strike: 150, option_type: 'PUT',
    expiration: '2024-05-17', entry_price: 2.80, current_price: 2.10,
    original_quantity: 3, remaining_quantity: 3, total_cost: 840,
    broker: 'Alpaca', status: 'open', opened_at: '2024-04-16T14:20:00Z',
    closed_at: null, realized_pnl: 0, unrealized_pnl: -210, simulated: false
  },
  {
    id: '3', ticker: 'NVDA', strike: 800, option_type: 'CALL',
    expiration: '2024-04-19', entry_price: 12.50, current_price: 14.20,
    original_quantity: 2, remaining_quantity: 0, total_cost: 2500,
    broker: 'IBKR', status: 'closed', opened_at: '2024-04-10T09:15:00Z',
    closed_at: '2024-04-17T15:45:00Z', realized_pnl: 340, unrealized_pnl: 0, simulated: true
  },
  {
    id: '4', ticker: 'MSFT', strike: 380, option_type: 'CALL',
    expiration: '2024-05-17', entry_price: 5.20, current_price: 5.80,
    original_quantity: 4, remaining_quantity: 2, total_cost: 2080,
    broker: 'Tradier', status: 'partial', opened_at: '2024-04-12T11:00:00Z',
    closed_at: null, realized_pnl: 120, unrealized_pnl: 120, simulated: false
  },
];

interface Position {
  id: string; ticker: string; strike: number; option_type: string;
  expiration: string; entry_price: number; current_price: number | null;
  original_quantity: number; remaining_quantity: number; total_cost: number;
  broker: string; status: string; opened_at: string; closed_at: string | null;
  realized_pnl: number; unrealized_pnl: number; simulated: boolean;
}

function ExposureStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={s.digestStat}>
      <Text style={[s.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={s.digestStatLabel}>{label}</Text>
    </View>
  );
}

function PositionBriefing({ digest }: { digest: PositionDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#64748b';

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
  const [positions, setPositions]   = useState<Position[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter]         = useState<PositionFilter>('open');
  const [selected, setSelected]     = useState<Position | null>(null);
  const [showSell, setShowSell]     = useState(false);
  const [sellPct, setSellPct]       = useState('50');
  const [exitPrice, setExitPrice]   = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError]   = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (DEMO_MODE) {
      // Use demo data
      setPositions(DEMO_POSITIONS);
      setLoadError(null);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    try {
      const r = await api.get(`${BACKEND_URL}/api/positions`);
      setPositions(r.data);
      setLoadError(null);
    } catch (e) { 
      console.error(e); 
      setLoadError('Live positions could not load. Check the backend connection and refresh.');
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);
  const onRefresh = useCallback(() => { setRefreshing(true); fetch(); }, [fetch]);

  const openSell = (p: Position) => {
    setSelected(p); setSellPct('50');
    setExitPrice(p.current_price?.toString() || p.entry_price.toString());
    setShowSell(true);
  };

  const sellPosition = async () => {
    if (!selected) return;
    const priceR = validatePrice(exitPrice);
    const pctR   = validatePercentage(sellPct, { min: 1, max: 100 });
    if (priceR.error) { Alert.alert('Invalid Price', priceR.error); return; }
    if (pctR.error)   { Alert.alert('Invalid %', pctR.error); return; }
    setSubmitting(true);
    try {
      const res = await api.post(`${BACKEND_URL}/api/positions/${selected.id}/sell`, null, {
        params: { sell_percentage: pctR.value, exit_price: priceR.value }
      });
      Alert.alert('Sold', `${sellPct}% of ${selected.ticker}\nP&L: ${formatPnL(res.data.realized_pnl)}`);
      setShowSell(false); setSelected(null); fetch();
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || 'Failed to sell'); }
    finally { setSubmitting(false); }
  };

  const openPositions = positions.filter(p => p.status === 'open' || p.status === 'partial');
  const totalUnrealized = openPositions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0);
  const totalRealized   = positions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0);
  const digest = summarizePositions(positions);
  const filteredPositions = filterPositions(positions, filter);
  const filterOptions: { key: PositionFilter; label: string; count: number }[] = [
    { key: 'open', label: 'Open', count: digest.open },
    { key: 'all', label: 'All', count: digest.total },
    { key: 'closed', label: 'Closed', count: digest.closed },
    { key: 'attention', label: 'Watch', count: filterPositions(positions, 'attention').length },
  ];

  const renderItem = ({ item: p }: { item: Position }) => {
    const bColor  = BROKER_COLORS[p.broker] || '#64748b';
    const bName   = BROKER_NAMES[p.broker] || p.broker;
    const isOpen  = p.status !== 'closed';
    const curr    = p.current_price ?? p.entry_price;
    const upnl    = p.unrealized_pnl || ((curr - p.entry_price) * p.remaining_quantity * 100);
    const pnlColor = getPnLColor(isOpen ? upnl : p.realized_pnl);
    const pnlVal   = isOpen ? upnl : p.realized_pnl;
    const pnlLabel = isOpen ? 'Unrealized' : 'Realized';

    return (
      <View style={[s.card, !isOpen && s.cardClosed]}>
        {/* Header */}
        <View style={s.cardTop}>
          <View style={s.tickerRow}>
            <Text style={s.ticker}>${p.ticker}</Text>
            <View style={[s.typePill, { backgroundColor: p.option_type === 'CALL' ? '#14532d' : '#450a0a' }]}>
              <Text style={[s.typeText, { color: p.option_type === 'CALL' ? '#4ade80' : '#f87171' }]}>{p.option_type}</Text>
            </View>
            {p.simulated && (
              <View style={s.simPill}><Text style={s.simText}>SIM</Text></View>
            )}
          </View>
          <View style={s.badges}>
            <View style={[s.badge, { backgroundColor: bColor + '22', borderColor: bColor + '44', borderWidth: 1 }]}>
              <Text style={[s.badgeText, { color: bColor }]}>{bName}</Text>
            </View>
            <View style={[s.badge, {
              backgroundColor: p.status === 'open' ? '#14532d' : p.status === 'partial' ? '#422006' : '#1e2d3d'
            }]}>
              <Text style={[s.badgeText, {
                color: p.status === 'open' ? '#4ade80' : p.status === 'partial' ? '#fb923c' : '#64748b'
              }]}>{p.status.toUpperCase()}</Text>
            </View>
          </View>
        </View>

        {/* Stats */}
        <View style={s.grid}>
          {[
            { label: 'STRIKE',  value: `$${p.strike}` },
            { label: 'ENTRY',   value: `$${p.entry_price.toFixed(2)}` },
            { label: 'CURRENT', value: `$${curr.toFixed(2)}` },
            { label: 'QTY',     value: `${p.remaining_quantity}/${p.original_quantity}` },
          ].map(({ label, value }) => (
            <View key={label} style={s.gridCell}>
              <Text style={s.gridLabel}>{label}</Text>
              <Text style={s.gridValue}>{value}</Text>
            </View>
          ))}
        </View>

        {/* P&L bar */}
        <View style={[s.pnlBar, { backgroundColor: (pnlVal || 0) >= 0 ? '#14280a' : '#2d1515' }]}>
          <Text style={s.pnlLabel}>{pnlLabel}</Text>
          <View style={s.pnlRight}>
            <Ionicons name={(pnlVal || 0) >= 0 ? 'trending-up' : 'trending-down'} size={14} color={pnlColor} />
            <Text style={[s.pnlValue, { color: pnlColor }]}>{formatPnL(pnlVal)}</Text>
          </View>
        </View>

        {/* Footer */}
        <View style={s.footer}>
          <View style={s.footerLeft}>
            <Ionicons name="calendar-outline" size={12} color="#334155" />
            <Text style={s.footerText}>Exp: {p.expiration}</Text>
            <Text style={s.footerDot}>·</Text>
            <Text style={s.footerText}>{formatDate(isOpen ? p.opened_at : (p.closed_at || p.opened_at))}</Text>
          </View>
          {isOpen && (
            <TouchableOpacity style={s.sellBtn} onPress={() => openSell(p)}>
              <Text style={s.sellBtnText}>Sell</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={s.container}>
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.eyebrow}>PORTFOLIO</Text>
          <Text style={s.title}>Positions</Text>
        </View>
        <View style={s.headerStats}>
          <Text style={[s.headerPnl, { color: getPnLColor(totalUnrealized) }]}>
            {formatPnL(totalUnrealized)}
          </Text>
          <Text style={s.headerPnlSub}>unrealized · {openPositions.length} open</Text>
        </View>
      </View>

      <PositionBriefing digest={digest} />

      {loadError && (
        <View style={s.errorBanner}>
          <Ionicons name="warning-outline" size={16} color="#f59e0b" />
          <Text style={s.errorBannerText}>{loadError}</Text>
        </View>
      )}

      {/* Summary strip */}
      <View style={s.strip}>
        <View style={s.stripCell}>
          <Text style={[s.stripValue, { color: getPnLColor(totalUnrealized) }]}>{formatPnL(totalUnrealized)}</Text>
          <Text style={s.stripLabel}>Unrealized</Text>
        </View>
        <View style={s.stripDiv} />
        <View style={s.stripCell}>
          <Text style={[s.stripValue, { color: getPnLColor(totalRealized) }]}>{formatPnL(totalRealized)}</Text>
          <Text style={s.stripLabel}>Realized</Text>
        </View>
        <View style={s.stripDiv} />
        <View style={s.stripCell}>
          <Text style={s.stripValue}>{openPositions.length}</Text>
          <Text style={s.stripLabel}>Open</Text>
        </View>
        <View style={s.stripDiv} />
        <View style={s.stripCell}>
          <Text style={s.stripValue}>{positions.filter(p => p.status === 'closed').length}</Text>
          <Text style={s.stripLabel}>Closed</Text>
        </View>
      </View>

      {/* Filters */}
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
          data={filteredPositions}
          renderItem={renderItem}
          keyExtractor={i => i.id}
          contentContainerStyle={s.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#0ea5e9" />}
          ListEmptyComponent={
            <View style={s.empty}>
              <Ionicons name="briefcase-outline" size={48} color="#1e2d3d" />
              <Text style={s.emptyTitle}>No positions</Text>
            </View>
          }
        />
      )}

      {/* Sell Modal */}
      <Modal visible={showSell} transparent animationType="fade">
        <View style={s.overlay}>
          <View style={s.modal}>
            <Text style={s.modalTitle}>Sell Position</Text>
            <Text style={s.modalSub}>{selected?.ticker} {selected?.strike} {selected?.option_type} · {selected?.remaining_quantity} contracts</Text>

            <Text style={s.modalLabel}>Sell Percentage</Text>
            <View style={s.pctRow}>
              {['25', '50', '75', '100'].map(pct => (
                <TouchableOpacity key={pct} style={[s.pctBtn, sellPct === pct && s.pctBtnActive]} onPress={() => setSellPct(pct)}>
                  <Text style={[s.pctText, sellPct === pct && s.pctTextActive]}>{pct}%</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput
              style={s.modalInput} value={sellPct} onChangeText={setSellPct}
              keyboardType="decimal-pad" placeholder="%" placeholderTextColor="#334155"
            />

            <Text style={s.modalLabel}>Exit Price</Text>
            <TextInput
              style={s.modalInput} value={exitPrice} onChangeText={setExitPrice}
              keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor="#334155"
            />

            <View style={s.modalBtns}>
              <TouchableOpacity style={s.modalCancel} onPress={() => setShowSell(false)}>
                <Text style={s.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.modalConfirm} onPress={sellPosition} disabled={submitting}>
                {submitting ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.modalConfirmText}>Sell {sellPct}%</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container:  { flex: 1, backgroundColor: '#080f1a' },
  centered:   { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 },
  eyebrow:    { fontSize: 10, color: '#0ea5e9', fontWeight: '700', letterSpacing: 2, marginBottom: 2 },
  title:      { fontSize: 26, fontWeight: '800', color: '#e2e8f0' },
  headerStats:{ alignItems: 'flex-end' },
  headerPnl:  { fontSize: 20, fontWeight: '800' },
  headerPnlSub: { fontSize: 11, color: '#475569', marginTop: 1 },

  strip:      { flexDirection: 'row', marginHorizontal: 16, backgroundColor: '#0d1826', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#1e2d3d', alignItems: 'center' },
  stripCell:  { flex: 1, alignItems: 'center' },
  stripValue: { fontSize: 14, fontWeight: '800', color: '#e2e8f0' },
  stripLabel: { fontSize: 9, color: '#475569', marginTop: 3, fontWeight: '600', letterSpacing: 0.5 },
  stripDiv:   { width: 1, height: 30, backgroundColor: '#1e2d3d' },

  digestCard: { backgroundColor: '#0b1420', borderRadius: 14, marginHorizontal: 16, marginBottom: 10, padding: 14, borderWidth: 1 },
  digestTop:  { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  digestTitleBlock: { flex: 1 },
  digestEyebrow: { fontSize: 10, color: '#64748b', fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle: { fontSize: 18, fontWeight: '800', color: '#e2e8f0' },
  digestDetail: { fontSize: 12, lineHeight: 17, color: '#94a3b8', marginTop: 3 },
  digestExposure: { minWidth: 94, height: 42, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  digestExposureValue: { fontSize: 17, fontWeight: '900' },
  digestExposureLabel: { fontSize: 10, color: '#64748b', fontWeight: '700', marginTop: 1 },
  digestStats: { flexDirection: 'row', marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#132235' },
  digestStat: { flex: 1, alignItems: 'center' },
  digestStatValue: { fontSize: 14, fontWeight: '800', color: '#e2e8f0' },
  digestStatLabel: { fontSize: 9, color: '#64748b', marginTop: 3, fontWeight: '700' },

  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginBottom: 10, padding: 10, borderRadius: 8, backgroundColor: '#1c1500', borderWidth: 1, borderColor: '#92400e' },
  errorBannerText: { flex: 1, fontSize: 12, color: '#f59e0b', fontWeight: '600' },

  filterBar:  { flexDirection: 'row', paddingHorizontal: 16, gap: 8, marginBottom: 10 },
  filterBtn:  { flex: 1, alignItems: 'center', paddingHorizontal: 8, paddingVertical: 7, borderRadius: 8, backgroundColor: '#0d1826', borderWidth: 1, borderColor: '#1e2d3d' },
  filterBtnActive: { backgroundColor: '#0c2740', borderColor: '#0ea5e9' },
  filterText: { fontSize: 13, color: '#475569', fontWeight: '600' },
  filterTextActive: { color: '#0ea5e9' },
  filterCount: { fontSize: 11, color: '#334155', fontWeight: '800', marginTop: 2 },
  filterCountActive: { color: '#7dd3fc' },

  list:       { paddingHorizontal: 16, paddingBottom: 16 },
  card:       { backgroundColor: '#0d1826', borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#1e2d3d' },
  cardClosed: { opacity: 0.7 },
  cardTop:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  tickerRow:  { flexDirection: 'row', alignItems: 'center', gap: 7 },
  ticker:     { fontSize: 18, fontWeight: '800', color: '#e2e8f0' },
  typePill:   { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 },
  typeText:   { fontSize: 11, fontWeight: '700' },
  simPill:    { backgroundColor: '#2d1f5e', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  simText:    { fontSize: 10, color: '#a78bfa', fontWeight: '700' },
  badges:     { flexDirection: 'row', gap: 6 },
  badge:      { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 },
  badgeText:  { fontSize: 10, fontWeight: '700' },

  grid:       { flexDirection: 'row', gap: 4, marginBottom: 10 },
  gridCell:   { flex: 1, backgroundColor: '#111c2a', borderRadius: 7, padding: 8, alignItems: 'center' },
  gridLabel:  { fontSize: 9, color: '#334155', fontWeight: '700', letterSpacing: 1, marginBottom: 3 },
  gridValue:  { fontSize: 13, fontWeight: '700', color: '#e2e8f0' },

  pnlBar:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 10, borderRadius: 8, marginBottom: 10 },
  pnlLabel:   { fontSize: 11, color: '#64748b', fontWeight: '600' },
  pnlRight:   { flexDirection: 'row', alignItems: 'center', gap: 5 },
  pnlValue:   { fontSize: 15, fontWeight: '800' },

  footer:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  footerLeft: { flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1 },
  footerText: { fontSize: 10, color: '#334155' },
  footerDot:  { fontSize: 10, color: '#1e2d3d' },
  sellBtn:    { backgroundColor: '#0c2740', paddingHorizontal: 16, paddingVertical: 6, borderRadius: 7, borderWidth: 1, borderColor: '#0ea5e9' },
  sellBtnText:{ fontSize: 12, color: '#0ea5e9', fontWeight: '700' },

  empty:      { alignItems: 'center', paddingVertical: 64, gap: 10 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: '#1e2d3d' },

  overlay:    { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', alignItems: 'center', justifyContent: 'center', padding: 24 },
  modal:      { backgroundColor: '#0d1826', borderRadius: 16, padding: 24, width: '100%', maxWidth: 400, borderWidth: 1, borderColor: '#1e2d3d' },
  modalTitle: { fontSize: 18, fontWeight: '800', color: '#e2e8f0', marginBottom: 4 },
  modalSub:   { fontSize: 13, color: '#475569', marginBottom: 20 },
  modalLabel: { fontSize: 12, color: '#64748b', fontWeight: '600', marginBottom: 8 },
  modalInput: { backgroundColor: '#111c2a', borderRadius: 9, padding: 13, color: '#e2e8f0', fontSize: 16, fontWeight: '700', borderWidth: 1, borderColor: '#1e2d3d', marginBottom: 16 },
  pctRow:     { flexDirection: 'row', gap: 8, marginBottom: 10 },
  pctBtn:     { flex: 1, padding: 10, borderRadius: 8, backgroundColor: '#1e2d3d', alignItems: 'center' },
  pctBtnActive: { backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9' },
  pctText:    { fontSize: 13, color: '#64748b', fontWeight: '700' },
  pctTextActive: { color: '#0ea5e9' },
  modalBtns:  { flexDirection: 'row', gap: 10, marginTop: 4 },
  modalCancel:  { flex: 1, padding: 14, borderRadius: 9, backgroundColor: '#1e2d3d', alignItems: 'center' },
  modalCancelText: { color: '#64748b', fontWeight: '700' },
  modalConfirm:  { flex: 1, padding: 14, borderRadius: 9, backgroundColor: '#0c2740', borderWidth: 1, borderColor: '#0ea5e9', alignItems: 'center' },
  modalConfirmText: { color: '#0ea5e9', fontWeight: '700' },
});
