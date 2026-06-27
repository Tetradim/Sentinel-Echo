/**
 * Strike Selection Page
 * Select optimal strikes from an options chain snapshot.
 */
import React, { useState } from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import {
  STRIKE_STRATEGIES,
  buildPreviewStrikeChain,
  StrikeChain,
  StrikeContract,
  StrikeOptionType,
  StrikeSelectionDigest,
  StrikeStrategy,
  summarizeStrikeSelection,
} from '../utils/strikeSelectionDigest';

type TabType = 'chain' | 'select' | 'compare';

const TICKERS = ['QQQ', 'SPY', 'AAPL', 'TSLA', 'NVDA'];
const EXPIRATIONS = [
  { value: '7', label: '7D' },
  { value: '14', label: '14D' },
  { value: '21', label: '21D' },
  { value: '30', label: '30D' },
  { value: '45', label: '45D' },
  { value: '60', label: '60D' },
  { value: '90', label: '90D' },
];

function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function contractsFor(chain: StrikeChain, optionType: StrikeOptionType): StrikeContract[] {
  return optionType === 'CALL' ? chain.calls : chain.puts;
}

function Segment<T extends string>({
  items,
  value,
  onChange,
}: {
  items: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.segmentRow}>
      {items.map((item) => (
        <TouchableOpacity
          key={item.value}
          style={[styles.segmentButton, value === item.value && styles.segmentButtonActive]}
          onPress={() => onChange(item.value)}
          accessibilityRole="button"
        >
          <Text style={[styles.segmentText, value === item.value && styles.segmentTextActive]}>
            {item.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.digestStat}>
      <Text style={[styles.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.digestStatLabel}>{label}</Text>
    </View>
  );
}

function StrikeBriefing({ digest, optionType }: { digest: StrikeSelectionDigest; optionType: StrikeOptionType }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#68779b';
  const warnings = digest.warningItems.slice(0, 3);

  return (
    <View style={[styles.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={styles.digestTop}>
        <View style={styles.digestTitleBlock}>
          <Text style={styles.digestEyebrow}>STRIKE READINESS</Text>
          <Text style={styles.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={styles.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[styles.strikeBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[styles.strikeBadgeValue, { color: toneColor }]}>
            {digest.selectedStrike ? `$${digest.selectedStrike}` : '--'}
          </Text>
          <Text style={styles.strikeBadgeLabel}>{optionType}</Text>
        </View>
      </View>

      <View style={styles.digestStats}>
        <DigestStat label="Premium" value={digest.selectedPremiumLabel} />
        <DigestStat label="Delta" value={digest.deltaLabel} color={toneColor} />
        <DigestStat label="Spread" value={digest.spreadLabel} />
        <DigestStat label="Liquidity" value={digest.liquidityLabel} />
      </View>

      <View style={styles.warningList}>
        {warnings.length > 0 ? warnings.map((warning) => (
          <View key={warning.title} style={styles.warningRow}>
            <Ionicons name="warning-outline" size={14} color="#f59e0b" />
            <View style={styles.warningCopy}>
              <Text style={styles.warningTitle}>{warning.title}</Text>
              <Text style={styles.warningDetail}>{warning.detail}</Text>
            </View>
          </View>
        )) : (
          <View style={styles.warningRow}>
            <Ionicons name="checkmark-circle-outline" size={14} color="#22c55e" />
            <Text style={styles.clearText}>Spread, delta, and open interest are usable for review.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

function ContractRow({
  contract,
  selected,
}: {
  contract: StrikeContract;
  selected: boolean;
}) {
  return (
    <View style={[styles.contractRow, selected && styles.contractRowSelected]}>
      <Text style={[styles.contractCell, styles.contractStrike]}>${contract.strike}</Text>
      <Text style={styles.contractCell}>{formatCurrency(contract.bid)}</Text>
      <Text style={styles.contractCell}>{formatCurrency(contract.ask)}</Text>
      <Text style={styles.contractCell}>{formatPercent(contract.iv)}</Text>
      <Text style={styles.contractCell}>{contract.delta.toFixed(2)}</Text>
      <Text style={styles.contractCell}>{contract.theta.toFixed(2)}</Text>
      <Text style={styles.contractCell}>{contract.oi.toLocaleString()}</Text>
    </View>
  );
}

export function StrikeSelectionPage() {
  const [activeTab, setActiveTab] = useState<TabType>('chain');
  const [ticker, setTicker] = useState('QQQ');
  const [expiration, setExpiration] = useState('30');
  const [selectedStrategy, setSelectedStrategy] = useState<StrikeStrategy>('ATM');
  const [selectedType, setSelectedType] = useState<StrikeOptionType>('CALL');

  const chain = buildPreviewStrikeChain({ ticker, expirationDays: expiration });
  const digest = summarizeStrikeSelection({
    chain,
    optionType: selectedType,
    strategy: selectedStrategy,
  });
  const contracts = contractsFor(chain, selectedType);

  const confirmSelection = () => {
    Alert.alert(
      'Strike Selected',
      `${ticker} ${expiration}D ${selectedType} ${digest.selectedStrike} at ${digest.selectedPremiumLabel}`
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>OPTIONS CHAIN</Text>
            <Text style={styles.title}>Strike Selection</Text>
          </View>
          <View style={styles.underlyingBadge}>
            <Text style={styles.underlyingLabel}>{ticker}</Text>
            <Text style={styles.underlyingValue}>{formatCurrency(chain.underlying)}</Text>
          </View>
        </View>

        <StrikeBriefing digest={digest} optionType={selectedType} />

        <View style={styles.controlsCard}>
          <Text style={styles.sectionTitle}>Contract Context</Text>
          <Text style={styles.controlLabel}>Ticker</Text>
          <Segment
            items={TICKERS.map((value) => ({ value, label: value }))}
            value={ticker}
            onChange={setTicker}
          />
          <Text style={styles.controlLabel}>Expiration</Text>
          <Segment
            items={EXPIRATIONS}
            value={expiration}
            onChange={setExpiration}
          />
          <Text style={styles.controlLabel}>Side</Text>
          <Segment
            items={[
              { value: 'CALL', label: 'CALL' },
              { value: 'PUT', label: 'PUT' },
            ]}
            value={selectedType}
            onChange={setSelectedType}
          />
        </View>

        <View style={styles.tabRow}>
          {([
            { id: 'chain', label: 'Chain' },
            { id: 'select', label: 'Select' },
            { id: 'compare', label: 'Compare' },
          ] as { id: TabType; label: string }[]).map((tab) => (
            <TouchableOpacity
              key={tab.id}
              style={[styles.tabButton, activeTab === tab.id && styles.tabButtonActive]}
              onPress={() => setActiveTab(tab.id)}
            >
              <Text style={[styles.tabText, activeTab === tab.id && styles.tabTextActive]}>{tab.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {activeTab === 'chain' && (
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>{selectedType} Chain</Text>
              <Text style={styles.sectionMeta}>{digest.contractCount} contracts</Text>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View>
                <View style={[styles.contractRow, styles.contractHeader]}>
                  {['Strike', 'Bid', 'Ask', 'IV', 'Delta', 'Theta', 'OI'].map((label) => (
                    <Text key={label} style={[styles.contractCell, styles.contractHeaderText]}>{label}</Text>
                  ))}
                </View>
                {contracts.map((contract) => (
                  <ContractRow
                    key={contract.strike}
                    contract={contract}
                    selected={contract.strike === digest.selectedStrike}
                  />
                ))}
              </View>
            </ScrollView>
          </View>
        )}

        {activeTab === 'select' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Selection Strategy</Text>
            <View style={styles.strategyGrid}>
              {STRIKE_STRATEGIES.map((strategy) => (
                <TouchableOpacity
                  key={strategy.id}
                  style={[
                    styles.strategyButton,
                    selectedStrategy === strategy.id && styles.strategyButtonActive,
                  ]}
                  onPress={() => setSelectedStrategy(strategy.id)}
                >
                  <Text style={[
                    styles.strategyTitle,
                    selectedStrategy === strategy.id && styles.strategyTitleActive,
                  ]}>
                    {strategy.name}
                  </Text>
                  <Text style={styles.strategyDetail}>{strategy.detail}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={styles.selectedCard}>
              <View>
                <Text style={styles.selectedEyebrow}>SELECTED CONTRACT</Text>
                <Text style={styles.selectedTitle}>
                  {ticker} {expiration}D {selectedType} ${digest.selectedStrike}
                </Text>
                <Text style={styles.selectedDetail}>
                  {digest.moneynessLabel} / {digest.ivLabel} IV / {digest.liquidityLabel}
                </Text>
              </View>
              <TouchableOpacity style={styles.primaryAction} onPress={confirmSelection}>
                <Ionicons name="checkmark-circle-outline" size={18} color="#070812" />
                <Text style={styles.primaryActionText}>Use Strike</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {activeTab === 'compare' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Strategy Comparison</Text>
            <View style={styles.compareHeaderRow}>
              <Text style={[styles.compareHeaderText, styles.compareHeaderStrategy]}>Strategy</Text>
              <Text style={[styles.compareHeaderText, styles.compareMetricStrike]}>Strike</Text>
              <Text style={[styles.compareHeaderText, styles.compareMetricPremium]}>Mid Premium</Text>
              <Text style={[styles.compareHeaderText, styles.compareMetricDelta]}>Delta</Text>
            </View>
            {digest.comparisonRows.map((row) => (
              <View key={row.strategy} style={styles.compareRow}>
                <View style={styles.compareCopy}>
                  <Text style={styles.compareTitle}>{row.strategyName}</Text>
                  <Text style={styles.compareDetail}>{row.scoreLabel}</Text>
                </View>
                <Text style={[styles.compareMetric, styles.compareMetricStrike]}>${row.strike}</Text>
                <Text style={[styles.compareMetric, styles.compareMetricPremium]}>{row.premiumLabel}</Text>
                <Text style={[styles.compareMetric, styles.compareMetricDelta]}>{row.deltaLabel}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

export default StrikeSelectionPage;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050416' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12, gap: 12 },
  eyebrow: { color: '#f43f5e', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { color: '#edf3ff', fontSize: 26, fontWeight: '900' },
  underlyingBadge: {
    alignItems: 'flex-end',
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    borderColor: '#164766',
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  underlyingLabel: { color: '#fb7185', fontSize: 11, fontWeight: '900' },
  underlyingValue: { color: '#edf3ff', fontSize: 16, fontWeight: '900', marginTop: 1 },
  digestCard: { backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 14, borderWidth: 1, marginBottom: 12, padding: 14 },
  digestTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  digestTitleBlock: { flex: 1 },
  digestEyebrow: { color: '#68779b', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle: { color: '#edf3ff', fontSize: 18, fontWeight: '900' },
  digestDetail: { color: '#aec0e5', fontSize: 12, lineHeight: 17, marginTop: 3 },
  strikeBadge: { minWidth: 86, borderRadius: 10, alignItems: 'center', justifyContent: 'center', paddingVertical: 8 },
  strikeBadgeValue: { fontSize: 18, fontWeight: '900' },
  strikeBadgeLabel: { color: '#68779b', fontSize: 10, fontWeight: '900', marginTop: 1 },
  digestStats: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(41, 33, 58, 0.82)',
  },
  digestStat: { flex: 1, minHeight: 54, borderRadius: 9, backgroundColor: 'transparent', padding: 8, justifyContent: 'center' },
  digestStatValue: { color: '#edf3ff', fontSize: 13, fontWeight: '900' },
  digestStatLabel: { color: '#68779b', fontSize: 9, fontWeight: '800', marginTop: 3, textTransform: 'uppercase' },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#68779b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#aec0e5', flex: 1, fontSize: 12, fontWeight: '700' },
  controlsCard: {
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderColor: '#29213a',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14,
  },
  controlLabel: { color: '#68779b', fontSize: 10, fontWeight: '900', letterSpacing: 1.2, marginBottom: 7, marginTop: 10 },
  segmentRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  segmentButton: {
    minHeight: 38,
    minWidth: 58,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    borderColor: '#29213a',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
  },
  segmentButtonActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  segmentText: { color: '#68779b', fontSize: 12, fontWeight: '900' },
  segmentTextActive: { color: '#fb7185' },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tabButton: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderColor: '#29213a',
    borderRadius: 9,
    borderWidth: 1,
    paddingVertical: 10,
  },
  tabButtonActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  tabText: { color: '#68779b', fontSize: 13, fontWeight: '900' },
  tabTextActive: { color: '#fb7185' },
  section: {
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderColor: '#29213a',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14,
  },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  sectionTitle: { color: '#edf3ff', fontSize: 17, fontWeight: '900' },
  sectionMeta: { color: '#68779b', fontSize: 11, fontWeight: '800' },
  contractRow: {
    flexDirection: 'row',
    minHeight: 40,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(41, 33, 58, 0.82)',
  },
  contractHeader: { backgroundColor: 'transparent', borderTopLeftRadius: 8, borderTopRightRadius: 8 },
  contractRowSelected: { backgroundColor: 'rgba(244, 63, 94, 0.18)' },
  contractCell: { width: 82, color: '#aec0e5', fontSize: 12, fontWeight: '800', textAlign: 'right', paddingHorizontal: 8 },
  contractStrike: { color: '#edf3ff', textAlign: 'left' },
  contractHeaderText: { color: '#68779b', fontSize: 10, textTransform: 'uppercase' },
  strategyGrid: { gap: 8 },
  strategyButton: {
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    borderColor: '#29213a',
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
  },
  strategyButtonActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  strategyTitle: { color: '#edf3ff', fontSize: 14, fontWeight: '900' },
  strategyTitleActive: { color: '#fb7185' },
  strategyDetail: { color: '#68779b', fontSize: 11, fontWeight: '700', lineHeight: 15, marginTop: 3 },
  selectedCard: {
    backgroundColor: 'transparent',
    borderColor: '#164766',
    borderRadius: 12,
    borderWidth: 1,
    gap: 12,
    marginTop: 12,
    padding: 14,
  },
  selectedEyebrow: { color: '#68779b', fontSize: 10, fontWeight: '900', letterSpacing: 1.3, marginBottom: 4 },
  selectedTitle: { color: '#edf3ff', fontSize: 18, fontWeight: '900' },
  selectedDetail: { color: '#aec0e5', fontSize: 12, fontWeight: '700', marginTop: 3 },
  primaryAction: {
    minHeight: 46,
    backgroundColor: '#f43f5e',
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  primaryActionText: { color: '#070812', fontSize: 14, fontWeight: '900' },
  compareHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomColor: 'rgba(41, 33, 58, 0.82)',
    borderBottomWidth: 1,
    gap: 8,
    paddingBottom: 8,
  },
  compareHeaderText: {
    color: '#68779b',
    fontSize: 9,
    fontWeight: '900',
    textAlign: 'right',
    textTransform: 'uppercase',
  },
  compareHeaderStrategy: { flex: 1, textAlign: 'left' },
  compareRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomColor: 'rgba(41, 33, 58, 0.82)',
    borderBottomWidth: 1,
    gap: 8,
    minHeight: 56,
  },
  compareCopy: { flex: 1 },
  compareTitle: { color: '#edf3ff', fontSize: 13, fontWeight: '900' },
  compareDetail: { color: '#68779b', fontSize: 11, fontWeight: '700', marginTop: 2 },
  compareMetric: { color: '#aec0e5', fontSize: 12, fontWeight: '900', textAlign: 'right' },
  compareMetricStrike: { width: 58 },
  compareMetricPremium: { width: 82 },
  compareMetricDelta: { width: 54 },
});
