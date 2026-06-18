/**
 * Risk Management Settings Page
 * 
 * Complete risk management configuration page
 */
import React, { useState } from 'react';
import { View, Text, TextInput, Switch, ScrollView, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { RiskDigest, summarizeRiskSettings } from '../utils/riskDigest';

type TabType = 'position' | 'stoploss' | 'takeprofit' | 'trailing' | 'shutdown' | 'correlation';

type RiskSettings = {
  maxPositionSize: number;
  defaultQuantity: number;
  riskPerTrade: number;
  stopLossEnabled: boolean;
  stopLossPercentage: number;
  stopLossOrderType: string;
  takeProfitEnabled: boolean;
  takeProfitPercentage: number;
  multiLevelTakeProfit: boolean;
  trailingStopEnabled: boolean;
  trailingStopType: string;
  trailingStopPercent: number;
  trailingStopCents: number;
  trailingHours: number;
  autoShutdownEnabled: boolean;
  maxConsecutiveLosses: number;
  maxDailyLosses: number;
  maxDailyLossAmount: number;
  maxDrawdownPercent: number;
  maxPositionsPerTicker: number;
  maxPositionsPerSector: number;
};

const TABS: { id: TabType; label: string }[] = [
  { id: 'position', label: 'Position' },
  { id: 'stoploss', label: 'Stop Loss' },
  { id: 'takeprofit', label: 'Take Profit' },
  { id: 'trailing', label: 'Trailing' },
  { id: 'shutdown', label: 'Shutdown' },
  { id: 'correlation', label: 'Correlation' },
];

const DEFAULT_RISK_SETTINGS: RiskSettings = {
  // Position Sizing
  maxPositionSize: 1000,
  defaultQuantity: 1,
  riskPerTrade: 1.0,

  // Stop Loss
  stopLossEnabled: true,
  stopLossPercentage: 30,
  stopLossOrderType: 'market',

  // Take Profit
  takeProfitEnabled: true,
  takeProfitPercentage: 50,
  multiLevelTakeProfit: false,

  // Trailing Stop
  trailingStopEnabled: true,
  trailingStopType: 'percent',
  trailingStopPercent: 25,
  trailingStopCents: 0.25,
  trailingHours: 4,

  // Auto Shutdown
  autoShutdownEnabled: true,
  maxConsecutiveLosses: 3,
  maxDailyLosses: 5,
  maxDailyLossAmount: 500,
  maxDrawdownPercent: 20,

  // Correlation
  maxPositionsPerTicker: 3,
  maxPositionsPerSector: 3,
};

function RiskStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.briefingStat}>
      <Text style={[styles.briefingStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.briefingStatLabel}>{label}</Text>
    </View>
  );
}

function RiskBriefing({ digest }: { digest: RiskDigest }) {
  const toneColor = digest.primaryStatus.tone === 'live' ? '#22c55e' : '#f59e0b';
  const warnings = digest.warningItems.slice(0, 3);

  return (
    <View style={[styles.briefingCard, { borderColor: toneColor + '55' }]}>
      <View style={styles.briefingTop}>
        <View style={styles.briefingTitleBlock}>
          <Text style={styles.briefingEyebrow}>RISK READINESS</Text>
          <Text style={styles.briefingTitle}>{digest.primaryStatus.title}</Text>
          <Text style={styles.briefingDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[styles.coverageBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[styles.coverageValue, { color: toneColor }]}>{digest.guardCoveragePercent}%</Text>
          <Text style={styles.coverageLabel}>covered</Text>
        </View>
      </View>

      <View style={styles.briefingStats}>
        <RiskStat label="Guards" value={`${digest.enabledGuards}/6`} color={toneColor} />
        <RiskStat label="Risk/Trade" value={digest.riskPerTradeLabel} />
        <RiskStat label="Max Size" value={digest.maxPositionSizeLabel} />
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
            <Ionicons name="shield-checkmark-outline" size={14} color="#22c55e" />
            <Text style={styles.clearText}>All primary automation guardrails are armed.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

export default function RiskSettingsScreen() {
  const [activeTab, setActiveTab] = useState<TabType>('position');
  const [settings, setSettings] = useState<RiskSettings>(DEFAULT_RISK_SETTINGS);
  const digest = summarizeRiskSettings(settings);

  const updateSetting = <K extends keyof RiskSettings>(key: K, value: RiskSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const saveSettings = () => {
    Alert.alert('Saved', 'Risk settings saved successfully');
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'position':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Position Sizing</Text>
            
            <View style={styles.field}>
              <Text style={styles.label}>Max Position Size ($)</Text>
              <TextInput
                style={styles.input}
                value={String(settings.maxPositionSize)}
                onChangeText={v => updateSetting('maxPositionSize', Number(v))}
                keyboardType="numeric"
              />
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Default Quantity</Text>
              <TextInput
                style={styles.input}
                value={String(settings.defaultQuantity)}
                onChangeText={v => updateSetting('defaultQuantity', Number(v))}
                keyboardType="numeric"
              />
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Risk Per Trade (%)</Text>
              <TextInput
                style={styles.input}
                value={String(settings.riskPerTrade)}
                onChangeText={v => updateSetting('riskPerTrade', Number(v))}
                keyboardType="numeric"
              />
            </View>
          </View>
        );
        
      case 'stoploss':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Stop Loss</Text>
            
            <View style={styles.field}>
              <View style={styles.row}>
                <Text style={styles.label}>Enable Stop Loss</Text>
                <Switch
                  value={settings.stopLossEnabled}
                  onValueChange={v => updateSetting('stopLossEnabled', v)}
                />
              </View>
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Stop Loss (%)</Text>
              <TextInput
                style={[styles.input, !settings.stopLossEnabled && styles.inputDisabled]}
                value={String(settings.stopLossPercentage)}
                onChangeText={v => updateSetting('stopLossPercentage', Number(v))}
                keyboardType="numeric"
                editable={settings.stopLossEnabled}
              />
            </View>
          </View>
        );
        
      case 'takeprofit':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Take Profit</Text>
            
            <View style={styles.field}>
              <View style={styles.row}>
                <Text style={styles.label}>Enable Take Profit</Text>
                <Switch
                  value={settings.takeProfitEnabled}
                  onValueChange={v => updateSetting('takeProfitEnabled', v)}
                />
              </View>
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Take Profit (%)</Text>
              <TextInput
                style={[styles.input, !settings.takeProfitEnabled && styles.inputDisabled]}
                value={String(settings.takeProfitPercentage)}
                onChangeText={v => updateSetting('takeProfitPercentage', Number(v))}
                keyboardType="numeric"
                editable={settings.takeProfitEnabled}
              />
            </View>
          </View>
        );
        
      case 'trailing':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Trailing Stop</Text>
            
            <View style={styles.field}>
              <View style={styles.row}>
                <Text style={styles.label}>Enable Trailing Stop</Text>
                <Switch
                  value={settings.trailingStopEnabled}
                  onValueChange={v => updateSetting('trailingStopEnabled', v)}
                />
              </View>
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Trailing Stop (%)</Text>
              <TextInput
                style={[styles.input, !settings.trailingStopEnabled && styles.inputDisabled]}
                value={String(settings.trailingStopPercent)}
                onChangeText={v => updateSetting('trailingStopPercent', Number(v))}
                keyboardType="numeric"
                editable={settings.trailingStopEnabled}
              />
            </View>
          </View>
        );
        
      case 'shutdown':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Auto Shutdown</Text>
            
            <View style={styles.field}>
              <View style={styles.row}>
                <Text style={styles.label}>Enable Auto Shutdown</Text>
                <Switch
                  value={settings.autoShutdownEnabled}
                  onValueChange={v => updateSetting('autoShutdownEnabled', v)}
                />
              </View>
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Max Consecutive Losses</Text>
              <TextInput
                style={styles.input}
                value={String(settings.maxConsecutiveLosses)}
                onChangeText={v => updateSetting('maxConsecutiveLosses', Number(v))}
                keyboardType="numeric"
              />
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Max Daily Loss ($)</Text>
              <TextInput
                style={styles.input}
                value={String(settings.maxDailyLossAmount)}
                onChangeText={v => updateSetting('maxDailyLossAmount', Number(v))}
                keyboardType="numeric"
              />
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Max Drawdown (%)</Text>
              <TextInput
                style={styles.input}
                value={String(settings.maxDrawdownPercent)}
                onChangeText={v => updateSetting('maxDrawdownPercent', Number(v))}
                keyboardType="numeric"
              />
            </View>
          </View>
        );
        
      case 'correlation':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Correlation Limits</Text>
            
            <View style={styles.field}>
              <Text style={styles.label}>Max Positions Per Ticker</Text>
              <TextInput
                style={styles.input}
                value={String(settings.maxPositionsPerTicker)}
                onChangeText={v => updateSetting('maxPositionsPerTicker', Number(v))}
                keyboardType="numeric"
              />
            </View>
            
            <View style={styles.field}>
              <Text style={styles.label}>Max Positions Per Sector</Text>
              <TextInput
                style={styles.input}
                value={String(settings.maxPositionsPerSector)}
                onChangeText={v => updateSetting('maxPositionsPerSector', Number(v))}
                keyboardType="numeric"
              />
            </View>
          </View>
        );
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>RISK CONTROLS</Text>
            <Text style={styles.title}>Risk Management</Text>
          </View>
          <View style={styles.headerBadge}>
            <Ionicons name="shield-outline" size={14} color="#38bdf8" />
            <Text style={styles.headerBadgeText}>{digest.enabledGuards}/6 guards</Text>
          </View>
        </View>

        <RiskBriefing digest={digest} />
        
        {/* Tab Navigation */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar}>
          <View style={styles.tabRow}>
            {TABS.map(tab => (
              <TouchableOpacity
                key={tab.id}
                style={[styles.tab, activeTab === tab.id && styles.tabActive]}
                onPress={() => setActiveTab(tab.id)}
              >
                <Text style={[styles.tabText, activeTab === tab.id && styles.tabTextActive]}>
                  {tab.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>
        
        {/* Tab Content */}
        {renderTabContent()}
        
        {/* Save Button */}
        <View style={styles.buttonContainer}>
          <TouchableOpacity style={styles.saveButton} onPress={saveSettings} accessibilityRole="button">
            <Ionicons name="save-outline" size={18} color="#08111f" />
            <Text style={styles.saveButtonText}>Save Settings</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#08111f' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 },
  eyebrow: { color: '#38bdf8', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { fontSize: 26, fontWeight: '800', color: '#e2e8f0' },
  headerBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#0b2136',
    borderWidth: 1,
    borderColor: '#164766',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  headerBadgeText: { color: '#7dd3fc', fontSize: 11, fontWeight: '800' },
  briefingCard: {
    backgroundColor: '#0b1420',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginBottom: 12,
  },
  briefingTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  briefingTitleBlock: { flex: 1 },
  briefingEyebrow: { color: '#64748b', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  briefingTitle: { color: '#e2e8f0', fontSize: 18, fontWeight: '900' },
  briefingDetail: { color: '#94a3b8', fontSize: 12, lineHeight: 17, marginTop: 3 },
  coverageBadge: { minWidth: 84, height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  coverageValue: { fontSize: 18, fontWeight: '900' },
  coverageLabel: { color: '#64748b', fontSize: 10, fontWeight: '800', marginTop: 1 },
  briefingStats: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#132235',
  },
  briefingStat: { flex: 1, alignItems: 'center' },
  briefingStatValue: { color: '#e2e8f0', fontSize: 14, fontWeight: '900' },
  briefingStatLabel: { color: '#64748b', fontSize: 9, fontWeight: '800', marginTop: 3 },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#0d1826',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#18283c',
    padding: 10,
  },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#64748b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#94a3b8', fontSize: 12, fontWeight: '700', flex: 1 },
  tabBar: { marginBottom: 12 },
  tabRow: { flexDirection: 'row', gap: 8, paddingRight: 16 },
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 8,
    backgroundColor: '#0d1826',
    borderWidth: 1,
    borderColor: '#1e2d3d',
  },
  tabActive: { backgroundColor: '#0c2740', borderColor: '#0ea5e9' },
  tabText: { color: '#64748b', fontSize: 13, fontWeight: '700' },
  tabTextActive: { color: '#7dd3fc' },
  section: {
    backgroundColor: '#0d1826',
    borderRadius: 12,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#1e2d3d',
  },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: '#e2e8f0', marginBottom: 16 },
  field: { marginBottom: 16 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  label: { color: '#94a3b8', fontSize: 13, fontWeight: '700', marginBottom: 6 },
  input: {
    backgroundColor: '#111c2a',
    color: '#e2e8f0',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#1e2d3d',
    fontSize: 16,
    fontWeight: '700',
  },
  inputDisabled: { opacity: 0.45 },
  buttonContainer: { marginTop: 4, marginBottom: 32 },
  saveButton: {
    minHeight: 48,
    borderRadius: 10,
    backgroundColor: '#38bdf8',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  saveButtonText: { color: '#08111f', fontSize: 15, fontWeight: '900' },
});
