import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { getTradeCycles } from '../utils/apiClient';

type Filter = 'all' | 'open' | 'wins' | 'losses' | 'reentries' | 'attention';

type DecisionEvidence = {
  exit_trigger?: string;
  reason?: string;
  selected_step?: number;
  completed_steps_before?: number[];
  decision_bid?: number;
  decision_ask?: number | null;
  entry_price?: number;
  return_percent?: number | null;
  confirmations_observed?: number;
  confirmations_required?: number;
  submitted_limit_price?: number;
  quote_observed_at?: string;
};

type TimelineItem = {
  kind?: string;
  timestamp?: string;
  label?: string;
  details?: Record<string, unknown>;
};

type TradeCycle = {
  id: string;
  trade_cycle_id?: string;
  contract_key?: string;
  reentry_of_position_id?: string;
  ticker?: string;
  strike?: number;
  option_type?: string;
  expiration?: string;
  broker?: string;
  status?: string;
  opened_at?: string;
  closed_at?: string;
  entry_price?: number;
  weighted_exit_price?: number | null;
  original_quantity?: number;
  remaining_quantity?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  return_percent?: number;
  max_favorable_excursion_percent?: number | null;
  max_adverse_excursion_percent?: number | null;
  post_exit_highest_return_percent?: number | null;
  exit_triggers?: string[];
  source?: { name?: string; channel?: string; author?: string; raw_message?: string };
  strategy_snapshot?: Record<string, unknown>;
  decision_evidence?: DecisionEvidence[];
  timeline?: TimelineItem[];
  data_quality?: {
    has_source_alert?: boolean;
    has_entry_fill?: boolean;
    has_decision_evidence?: boolean;
    quantity_mismatch?: boolean;
    broker_quantity?: number | null;
    local_quantity?: number | null;
  };
};

type AuditResponse = {
  summary?: {
    cycles?: number;
    open_cycles?: number;
    closed_cycles?: number;
    wins?: number;
    losses?: number;
    win_rate?: number;
    net_pnl?: number;
    gross_profit?: number;
    gross_loss?: number;
    profit_factor?: number | null;
    reentries?: number;
    decision_evidence_coverage?: number;
  };
  cycles?: TradeCycle[];
};

function money(value?: number | null) {
  const number = Number(value ?? 0);
  return `${number < 0 ? '-' : ''}$${Math.abs(number).toFixed(2)}`;
}

function premium(value?: number | null) {
  return value == null ? '--' : `$${Number(value).toFixed(2)}`;
}

function percent(value?: number | null) {
  return value == null ? '--' : `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(1)}%`;
}

function time(value?: string) {
  if (!value) return '--';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function tone(value?: number | null) {
  return Number(value ?? 0) > 0 ? '#22c55e' : Number(value ?? 0) < 0 ? '#f87171' : '#aec0e5';
}

function needsAttention(cycle: TradeCycle) {
  return Boolean(
    cycle.data_quality?.quantity_mismatch
    || !cycle.data_quality?.has_entry_fill
    || (cycle.exit_triggers?.length && !cycle.data_quality?.has_decision_evidence)
  );
}

function cycleMatches(cycle: TradeCycle, filter: Filter) {
  if (filter === 'open') return cycle.status !== 'closed';
  if (filter === 'wins') return Number(cycle.realized_pnl ?? 0) > 0;
  if (filter === 'losses') return Number(cycle.realized_pnl ?? 0) < 0;
  if (filter === 'reentries') return Boolean(cycle.reentry_of_position_id);
  if (filter === 'attention') return needsAttention(cycle);
  return true;
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={s.metric}>
      <Text style={[s.metricValue, color ? { color } : null]} numberOfLines={1}>{value}</Text>
      <Text style={s.metricLabel}>{label}</Text>
    </View>
  );
}

function EvidenceRow({ evidence }: { evidence: DecisionEvidence }) {
  return (
    <View style={s.evidenceRow}>
      <View style={s.evidenceTitleRow}>
        <Text style={s.evidenceTitle}>{evidence.exit_trigger || 'Exit decision'}</Text>
        <Text style={[s.evidenceReturn, { color: tone(evidence.return_percent) }]}>{percent(evidence.return_percent)}</Text>
      </View>
      <View style={s.evidenceGrid}>
        <Text style={s.evidenceText}>Bid {premium(evidence.decision_bid)}</Text>
        <Text style={s.evidenceText}>Ask {premium(evidence.decision_ask)}</Text>
        <Text style={s.evidenceText}>Limit {premium(evidence.submitted_limit_price)}</Text>
        <Text style={s.evidenceText}>
          Step {evidence.selected_step ?? '--'} · confirms {evidence.confirmations_observed ?? '--'}/{evidence.confirmations_required ?? '--'}
        </Text>
      </View>
      {evidence.completed_steps_before && (
        <Text style={s.evidenceFoot}>Completed before decision: {evidence.completed_steps_before.length ? evidence.completed_steps_before.join(', ') : 'none'}</Text>
      )}
      {evidence.reason ? <Text style={s.evidenceFoot}>{evidence.reason}</Text> : null}
    </View>
  );
}

function CycleCard({ cycle }: { cycle: TradeCycle }) {
  const [expanded, setExpanded] = useState(false);
  const pnl = cycle.status === 'closed' ? cycle.realized_pnl : cycle.unrealized_pnl;
  const sourceLabel = cycle.source?.name || cycle.source?.channel || 'Unknown source';
  const evidence = cycle.decision_evidence ?? [];
  const strategyEntries = Object.entries(cycle.strategy_snapshot ?? {});

  return (
    <View style={[s.card, needsAttention(cycle) && s.cardAttention]}>
      <TouchableOpacity style={s.cardButton} onPress={() => setExpanded((value) => !value)} accessibilityRole="button">
        <View style={s.cardTop}>
          <View style={s.contractBlock}>
            <View style={s.contractRow}>
              <Text style={s.contract}>${cycle.ticker} {cycle.strike}{String(cycle.option_type || '').startsWith('C') ? 'C' : 'P'}</Text>
              {cycle.reentry_of_position_id ? <View style={s.reentryPill}><Text style={s.reentryText}>RE-ENTRY</Text></View> : null}
            </View>
            <Text style={s.source}>{sourceLabel} · {cycle.expiration || '--'} · {cycle.broker || '--'}</Text>
          </View>
          <View style={s.pnlBlock}>
            <Text style={[s.pnl, { color: tone(pnl) }]}>{money(pnl)}</Text>
            <Text style={[s.returnText, { color: tone(cycle.return_percent) }]}>{percent(cycle.return_percent)}</Text>
          </View>
        </View>

        <View style={s.statGrid}>
          <Metric label="ENTRY" value={premium(cycle.entry_price)} />
          <Metric label="AVG EXIT" value={premium(cycle.weighted_exit_price)} />
          <Metric label="QTY" value={`${cycle.original_quantity ?? 0} → ${cycle.remaining_quantity ?? 0}`} />
          <Metric label="MFE / MAE" value={`${percent(cycle.max_favorable_excursion_percent)} / ${percent(cycle.max_adverse_excursion_percent)}`} />
          <Metric label="POST-EXIT HIGH" value={percent(cycle.post_exit_highest_return_percent)} />
          <Metric label="STATUS" value={(cycle.status || 'unknown').toUpperCase()} />
        </View>

        <View style={s.cardFooter}>
          <Text style={s.footerText}>{time(cycle.opened_at)}</Text>
          <View style={s.footerRight}>
            {needsAttention(cycle) ? <Ionicons name="warning-outline" size={15} color="#f59e0b" /> : null}
            <Text style={s.footerText}>{evidence.length} decision record{evidence.length === 1 ? '' : 's'}</Text>
            <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={15} color="#68779b" />
          </View>
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={s.details}>
          <View style={s.detailSection}>
            <Text style={s.detailHeading}>SOURCE ALERT</Text>
            <Text style={s.detailText}>{cycle.source?.raw_message || 'Raw source alert was not retained for this cycle.'}</Text>
          </View>

          <View style={s.detailSection}>
            <Text style={s.detailHeading}>EXIT EVIDENCE</Text>
            {evidence.length ? evidence.map((item, index) => <EvidenceRow key={`${cycle.id}-evidence-${index}`} evidence={item} />) : (
              <Text style={s.detailMuted}>No decision snapshot was recorded. Older cycles may predate this audit field.</Text>
            )}
          </View>

          <View style={s.detailSection}>
            <Text style={s.detailHeading}>STRATEGY AT ENTRY</Text>
            {strategyEntries.length ? (
              <View style={s.strategyGrid}>
                {strategyEntries.map(([key, value]) => (
                  <View key={key} style={s.strategyItem}>
                    <Text style={s.strategyKey}>{key.replaceAll('_', ' ')}</Text>
                    <Text style={s.strategyValue} numberOfLines={2}>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</Text>
                  </View>
                ))}
              </View>
            ) : <Text style={s.detailMuted}>No entry settings snapshot was retained for this cycle.</Text>}
          </View>

          <View style={s.detailSection}>
            <Text style={s.detailHeading}>TIMELINE</Text>
            {(cycle.timeline ?? []).map((item, index) => (
              <View key={`${cycle.id}-timeline-${index}`} style={s.timelineRow}>
                <View style={s.timelineDot} />
                <View style={s.timelineBody}>
                  <Text style={s.timelineLabel}>{item.label || item.kind || 'Event'}</Text>
                  <Text style={s.timelineTime}>{time(item.timestamp)}</Text>
                </View>
              </View>
            ))}
          </View>

          <View style={s.identityRow}>
            <Ionicons name="finger-print-outline" size={14} color="#68779b" />
            <Text style={s.identityText} numberOfLines={2}>{cycle.trade_cycle_id || cycle.id}</Text>
          </View>
        </View>
      )}
    </View>
  );
}

export default function TradeAuditScreen() {
  const [data, setData] = useState<AuditResponse>({});
  const [filter, setFilter] = useState<Filter>('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const response = await getTradeCycles(1000);
      setData(response.data ?? {});
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Trade-cycle audit unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(
    () => (data.cycles ?? []).filter((cycle) => cycleMatches(cycle, filter)),
    [data.cycles, filter],
  );
  const summary = data.summary ?? {};
  const filters: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'open', label: 'Open' },
    { key: 'wins', label: 'Wins' },
    { key: 'losses', label: 'Losses' },
    { key: 'reentries', label: 'Re-entries' },
    { key: 'attention', label: 'Attention' },
  ];

  return (
    <SafeAreaView style={s.container}>
      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#f43f5e" />}
      >
        <View style={s.header}>
          <View>
            <Text style={s.eyebrow}>BROKER-CONFIRMED LIFECYCLE</Text>
            <Text style={s.title}>Trade Audit</Text>
          </View>
          <View style={s.coveragePill}>
            <Ionicons name="document-text-outline" size={15} color="#38bdf8" />
            <Text style={s.coverageText}>{Number(summary.decision_evidence_coverage ?? 0).toFixed(0)}% evidence</Text>
          </View>
        </View>

        <View style={s.summaryGrid}>
          <Metric label="NET P&L" value={money(summary.net_pnl)} color={tone(summary.net_pnl)} />
          <Metric label="CYCLES" value={String(summary.cycles ?? 0)} />
          <Metric label="WIN RATE" value={percent(summary.win_rate)} />
          <Metric label="PROFIT FACTOR" value={summary.profit_factor == null ? '--' : Number(summary.profit_factor).toFixed(2)} />
          <Metric label="GROSS PROFIT" value={money(summary.gross_profit)} color="#22c55e" />
          <Metric label="GROSS LOSS" value={money(summary.gross_loss)} color="#f87171" />
          <Metric label="OPEN" value={String(summary.open_cycles ?? 0)} />
          <Metric label="RE-ENTRIES" value={String(summary.reentries ?? 0)} />
        </View>

        <View style={s.filterRail}>
          {filters.map((item) => (
            <TouchableOpacity key={item.key} style={[s.filterButton, filter === item.key && s.filterButtonActive]} onPress={() => setFilter(item.key)}>
              <Text style={[s.filterLabel, filter === item.key && s.filterLabelActive]}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {error ? (
          <View style={s.errorBanner}>
            <Ionicons name="warning-outline" size={16} color="#f59e0b" />
            <Text style={s.errorText}>{error}</Text>
            <TouchableOpacity onPress={load}><Ionicons name="refresh" size={16} color="#f59e0b" /></TouchableOpacity>
          </View>
        ) : null}

        {loading ? (
          <View style={s.loading}><ActivityIndicator color="#f43f5e" /><Text style={s.detailMuted}>Loading trade cycles...</Text></View>
        ) : filtered.length ? filtered.map((cycle) => <CycleCard key={cycle.id} cycle={cycle} />) : (
          <View style={s.empty}><Ionicons name="search-outline" size={38} color="#29213a" /><Text style={s.emptyText}>No cycles match this view.</Text></View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050416' },
  content: { padding: 16, paddingBottom: 48 },
  header: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: 10, marginBottom: 14 },
  eyebrow: { fontSize: 10, color: '#f43f5e', fontWeight: '800', letterSpacing: 1.4, marginBottom: 3 },
  title: { fontSize: 25, color: '#edf3ff', fontWeight: '900' },
  coveragePill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 6, borderWidth: 1, borderColor: '#164e63', backgroundColor: 'rgba(8, 47, 73, 0.56)', borderRadius: 7, paddingHorizontal: 9, paddingVertical: 6 },
  coverageText: { color: '#7dd3fc', fontSize: 11, fontWeight: '800' },
  summaryGrid: { flexDirection: 'row', flexWrap: 'wrap', borderWidth: 1, borderColor: '#29213a', backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 8, marginBottom: 12 },
  metric: { width: '25%', minWidth: 110, minHeight: 58, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8, paddingVertical: 10 },
  metricValue: { color: '#edf3ff', fontSize: 14, fontWeight: '900' },
  metricLabel: { color: '#68779b', fontSize: 9, fontWeight: '800', marginTop: 3, letterSpacing: 0.7 },
  filterRail: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginBottom: 12 },
  filterButton: { borderWidth: 1, borderColor: '#29213a', backgroundColor: 'rgba(16, 9, 28, 0.82)', borderRadius: 7, paddingHorizontal: 12, paddingVertical: 7 },
  filterButtonActive: { borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.16)' },
  filterLabel: { color: '#68779b', fontSize: 11, fontWeight: '800' },
  filterLabelActive: { color: '#fb7185' },
  card: { borderWidth: 1, borderColor: '#29213a', backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 8, marginBottom: 9, overflow: 'hidden' },
  cardAttention: { borderColor: '#92400e' },
  cardButton: { padding: 13 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 10 },
  contractBlock: { flex: 1 },
  contractRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 7 },
  contract: { color: '#edf3ff', fontSize: 17, fontWeight: '900' },
  source: { color: '#68779b', fontSize: 11, marginTop: 3 },
  reentryPill: { borderRadius: 4, borderWidth: 1, borderColor: '#0369a1', backgroundColor: 'rgba(3, 105, 161, 0.17)', paddingHorizontal: 6, paddingVertical: 2 },
  reentryText: { color: '#7dd3fc', fontSize: 9, fontWeight: '900' },
  pnlBlock: { alignItems: 'flex-end' },
  pnl: { fontSize: 17, fontWeight: '900' },
  returnText: { fontSize: 11, fontWeight: '800', marginTop: 2 },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', backgroundColor: 'rgba(5, 4, 22, 0.56)', borderRadius: 7, paddingVertical: 2 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, borderTopWidth: 1, borderTopColor: '#29213a', marginTop: 10, paddingTop: 9 },
  footerRight: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  footerText: { color: '#68779b', fontSize: 10, fontWeight: '700' },
  details: { borderTopWidth: 1, borderTopColor: '#29213a', padding: 13, backgroundColor: 'rgba(5, 4, 22, 0.34)' },
  detailSection: { marginBottom: 14 },
  detailHeading: { color: '#68779b', fontSize: 9, fontWeight: '900', letterSpacing: 1.1, marginBottom: 7 },
  detailText: { color: '#c7d2e5', fontSize: 12, lineHeight: 18 },
  detailMuted: { color: '#68779b', fontSize: 11, lineHeight: 16 },
  evidenceRow: { borderLeftWidth: 3, borderLeftColor: '#f43f5e', backgroundColor: 'rgba(16, 9, 28, 0.9)', borderRadius: 6, padding: 10, marginBottom: 7 },
  evidenceTitleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  evidenceTitle: { color: '#edf3ff', fontSize: 12, fontWeight: '900' },
  evidenceReturn: { fontSize: 12, fontWeight: '900' },
  evidenceGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 7 },
  evidenceText: { color: '#aec0e5', fontSize: 10, fontWeight: '700' },
  evidenceFoot: { color: '#68779b', fontSize: 10, marginTop: 6 },
  strategyGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  strategyItem: { width: '32%', minWidth: 150, borderWidth: 1, borderColor: '#29213a', borderRadius: 6, padding: 8 },
  strategyKey: { color: '#68779b', fontSize: 9, textTransform: 'uppercase', fontWeight: '800' },
  strategyValue: { color: '#c7d2e5', fontSize: 11, fontWeight: '700', marginTop: 3 },
  timelineRow: { flexDirection: 'row', gap: 9, minHeight: 36 },
  timelineDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#38bdf8', marginTop: 5 },
  timelineBody: { flex: 1, borderBottomWidth: 1, borderBottomColor: 'rgba(41, 33, 58, 0.7)', paddingBottom: 7, marginBottom: 7 },
  timelineLabel: { color: '#c7d2e5', fontSize: 11, fontWeight: '700' },
  timelineTime: { color: '#68779b', fontSize: 9, marginTop: 2 },
  identityRow: { flexDirection: 'row', alignItems: 'center', gap: 7, borderTopWidth: 1, borderTopColor: '#29213a', paddingTop: 10 },
  identityText: { flex: 1, color: '#68779b', fontSize: 9 },
  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: '#92400e', backgroundColor: '#1c1500', borderRadius: 7, padding: 10, marginBottom: 10 },
  errorText: { flex: 1, color: '#f59e0b', fontSize: 11 },
  loading: { minHeight: 180, alignItems: 'center', justifyContent: 'center', gap: 10 },
  empty: { minHeight: 200, alignItems: 'center', justifyContent: 'center', gap: 9 },
  emptyText: { color: '#68779b', fontSize: 12, fontWeight: '700' },
});
