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

const MOCK_CHAIN: StrikeChain = {
  underlying: 450,
  calls: [
    { strike: 430, bid: 21.5, ask: 22.5, iv: 28, delta: 0.72, theta: -0.15, oi: 8500 },
    { strike: 440, bid: 14.2, ask: 15.0, iv: 26, delta: 0.55, theta: -0.12, oi: 12000 },
    { strike: 450, bid: 8.8, ask: 9.5, iv: 25, delta: 0.33, theta: -0.1, oi: 15000 },
    { strike: 460, bid: 4.5, ask: 5.0, iv: 26, delta: 0.2, theta: -0.08, oi: 11000 },
    { strike: 470, bid: 2.1, ask: 2.5, iv: 29, delta: 0.09, theta: -0.05, oi: 9000 },
  ],
  puts: [
    { strike: 430, bid: 2.0, ask: 2.5, iv: 27, delta: -0.08, theta: -0.05, oi: 7500 },
    { strike: 440, bid: 4.2, ask: 5.0, iv: 26, delta: -0.18, theta: -0.08, oi: 10000 },
    { strike: 450, bid: 8.5, ask: 9.5, iv: 25, delta: -0.32, theta: -0.1, oi: 14000 },
    { strike: 460, bid: 14.0, ask: 15.5, iv: 26, delta: -0.48, theta: -0.12, oi: 11000 },
    { strike: 470, bid: 21.0, ask: 23.0, iv: 28, delta: -0.65, theta: -0.15, oi: 8000 },
  ],
};

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
    '#64748b';
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

  const chain = MOCK_CHAIN;
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
                <Ionicons name="checkmark-circle-outline" size={18} color="#08111f" />
                <Text style={styles.primaryActionText}>Use Strike</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {activeTab === 'compare' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Strategy Comparison</Text>
            {digest.comparisonRows.map((row) => (
              <View key={row.strategy} style={styles.compareRow}>
                <View style={styles.compareCopy}>
                  <Text style={styles.compareTitle}>{row.strategyName}</Text>
                  <Text style={styles.compareDetail}>{row.scoreLabel}</Text>
                </View>
                <Text style={styles.compareMetric}>${row.strike}</Text>
                <Text style={styles.compareMetric}>{row.premiumLabel}</Text>
                <Text style={styles.compareMetric}>{row.deltaLabel}</Text>
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
  container: { flex: 1, backgroundColor: '#08111f' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12, gap: 12 },
  eyebrow: { color: '#38bdf8', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { color: '#e2e8f0', fontSize: 26, fontWeight: '900' },
  underlyingBadge: {
    alignItems: 'flex-end',
    backgroundColor: '#0b2136',
    borderColor: '#164766',
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  underlyingLabel: { color: '#7dd3fc', fontSize: 11, fontWeight: '900' },
  underlyingValue: { color: '#e2e8f0', fontSize: 16, fontWeight: '900', marginTop: 1 },
  digestCard: { backgroundColor: '#0b1420', borderRadius: 14, borderWidth: 1, marginBottom: 12, padding: 14 },
  digestTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  digestTitleBlock: { flex: 1 },
  digestEyebrow: { color: '#64748b', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  digestTitle: { color: '#e2e8f0', fontSize: 18, fontWeight: '900' },
  digestDetail: { color: '#94a3b8', fontSize: 12, lineHeight: 17, marginTop: 3 },
  strikeBadge: { minWidth: 86, borderRadius: 10, alignItems: 'center', justifyContent: 'center', paddingVertical: 8 },
  strikeBadgeValue: { fontSize: 18, fontWeight: '900' },
  strikeBadgeLabel: { color: '#64748b', fontSize: 10, fontWeight: '900', marginTop: 1 },
  digestStats: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#132235',
  },
  digestStat: { flex: 1, minHeight: 54, borderRadius: 9, backgroundColor: '#08111f', padding: 8, justifyContent: 'center' },
  digestStatValue: { color: '#e2e8f0', fontSize: 13, fontWeight: '900' },
  digestStatLabel: { color: '#64748b', fontSize: 9, fontWeight: '800', marginTop: 3, textTransform: 'uppercase' },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#64748b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#94a3b8', flex: 1, fontSize: 12, fontWeight: '700' },
  controlsCard: {
    backgroundColor: '#0d1826',
    borderColor: '#1e2d3d',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14,
  },
  controlLabel: { color: '#64748b', fontSize: 10, fontWeight: '900', letterSpacing: 1.2, marginBottom: 7, marginTop: 10 },
  segmentRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  segmentButton: {
    minHeight: 38,
    minWidth: 58,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#111c2a',
    borderColor: '#1e2d3d',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
  },
  segmentButtonActive: { backgroundColor: '#0b2136', borderColor: '#38bdf8' },
  segmentText: { color: '#64748b', fontSize: 12, fontWeight: '900' },
  segmentTextActive: { color: '#7dd3fc' },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tabButton: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#0d1826',
    borderColor: '#1e2d3d',
    borderRadius: 9,
    borderWidth: 1,
    paddingVertical: 10,
  },
  tabButtonActive: { backgroundColor: '#0b2136', borderColor: '#38bdf8' },
  tabText: { color: '#64748b', fontSize: 13, fontWeight: '900' },
  tabTextActive: { color: '#7dd3fc' },
  section: {
    backgroundColor: '#0d1826',
    borderColor: '#1e2d3d',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14,
  },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  sectionTitle: { color: '#e2e8f0', fontSize: 17, fontWeight: '900' },
  sectionMeta: { color: '#64748b', fontSize: 11, fontWeight: '800' },
  contractRow: {
    flexDirection: 'row',
    minHeight: 40,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#132235',
  },
  contractHeader: { backgroundColor: '#08111f', borderTopLeftRadius: 8, borderTopRightRadius: 8 },
  contractRowSelected: { backgroundColor: '#0b2136' },
  contractCell: { width: 82, color: '#94a3b8', fontSize: 12, fontWeight: '800', textAlign: 'right', paddingHorizontal: 8 },
  contractStrike: { color: '#e2e8f0', textAlign: 'left' },
  contractHeaderText: { color: '#64748b', fontSize: 10, textTransform: 'uppercase' },
  strategyGrid: { gap: 8 },
  strategyButton: {
    backgroundColor: '#111c2a',
    borderColor: '#1e2d3d',
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
  },
  strategyButtonActive: { backgroundColor: '#0b2136', borderColor: '#38bdf8' },
  strategyTitle: { color: '#e2e8f0', fontSize: 14, fontWeight: '900' },
  strategyTitleActive: { color: '#7dd3fc' },
  strategyDetail: { color: '#64748b', fontSize: 11, fontWeight: '700', lineHeight: 15, marginTop: 3 },
  selectedCard: {
    backgroundColor: '#08111f',
    borderColor: '#164766',
    borderRadius: 12,
    borderWidth: 1,
    gap: 12,
    marginTop: 12,
    padding: 14,
  },
  selectedEyebrow: { color: '#64748b', fontSize: 10, fontWeight: '900', letterSpacing: 1.3, marginBottom: 4 },
  selectedTitle: { color: '#e2e8f0', fontSize: 18, fontWeight: '900' },
  selectedDetail: { color: '#94a3b8', fontSize: 12, fontWeight: '700', marginTop: 3 },
  primaryAction: {
    minHeight: 46,
    backgroundColor: '#38bdf8',
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  primaryActionText: { color: '#08111f', fontSize: 14, fontWeight: '900' },
  compareRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomColor: '#132235',
    borderBottomWidth: 1,
    gap: 8,
    minHeight: 56,
  },
  compareCopy: { flex: 1 },
  compareTitle: { color: '#e2e8f0', fontSize: 13, fontWeight: '900' },
  compareDetail: { color: '#64748b', fontSize: 11, fontWeight: '700', marginTop: 2 },
  compareMetric: { width: 62, color: '#94a3b8', fontSize: 12, fontWeight: '900', textAlign: 'right' },
});
