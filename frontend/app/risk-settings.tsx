/**
 * Risk Management Settings Page
 * 
 * Complete risk management configuration page
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../utils/api';
import { RiskDigest, summarizeRiskSettings } from '../utils/riskDigest';
import { normalizeRiskSettingsState, type LossLadderStep, type RiskSettingsState } from '../utils/riskSettingsState';
import { BACKEND_URL } from '../constants/config';

type TabType = 'position' | 'stoploss' | 'takeprofit' | 'trailing' | 'intelligence' | 'shutdown' | 'correlation';

type RiskSettings = RiskSettingsState;

const TABS: { id: TabType; label: string }[] = [
  { id: 'position', label: 'Position' },
  { id: 'stoploss', label: 'Stop Loss' },
  { id: 'takeprofit', label: 'Take Profit' },
  { id: 'trailing', label: 'Trailing' },
  { id: 'intelligence', label: 'Intelligence' },
  { id: 'shutdown', label: 'Shutdown' },
  { id: 'correlation', label: 'Correlation' },
];

const DEFAULT_RISK_SETTINGS: RiskSettings = {
  // Position Sizing
  maxPositionSize: 1000,
  defaultQuantity: 1,
  riskPerTrade: 1.0,
  smartSizingEnabled: true,
  smartSizingAgreementPercent: 100,
  smartSizingMixedPercent: 50,
  smartSizingConflictPercent: 25,
  entrySlippageSizingEnabled: true,
  entrySlippageMode: 'tiered',
  entrySlippageWarningPercent: 10,
  entrySlippageSeverePercent: 20,
  entrySlippageWarningSizePercent: 50,
  entrySlippageSevereSizePercent: 25,
  marketableEntryEnabled: true,
  riskBudgetSizingEnabled: true,
  maxLossPerTrade: 100,
  coordinatedExitEnabled: true,
  coordinatedExitQuoteMaxAgeSeconds: 15,
  coordinatedNormalStopLossPercent: 35,
  coordinatedHighRiskStopLossPercent: 50,
  coordinatedHighRiskSizePercent: 25,
  coordinatedEmergencyStopLossPercent: 50,
  coordinatedStopRequiredConfirmations: 2,
  coordinatedStopConfirmationIntervalSeconds: 1,
  coordinatedRunnerReserveQuantity: 1,
  coordinatedProfitStage1Percent: 25,
  coordinatedProfitStage1SellPercent: 50,
  coordinatedProfitStage2Percent: 35,
  coordinatedProfitStage2SellPercent: 25,
  coordinatedFastScalpProfitStage1Percent: 10,
  coordinatedFastScalpProfitStage2Percent: 20,
  coordinatedLowActivationPercent: 15,
  coordinatedLowTrailingPercent: 15,
  coordinatedMediumActivationPercent: 20,
  coordinatedMediumTrailingPercent: 15,
  coordinatedHighActivationPercent: 12,
  coordinatedHighTrailingPercent: 10,
  coordinatedProgressiveTrailingEnabled: true,
  coordinatedTrailingMode: 'tightening',
  coordinatedTrailingStepGainPercent: 10,
  coordinatedTrailingStepTightenPercent: 1,
  coordinatedTrailingMinPercent: 8,
  coordinatedTrailingVolatilityGatePercent: 8,
  coordinatedElasticActivationPercent: 5,
  coordinatedElasticMinActivationCents: 3,
  coordinatedElasticTrailingStartPercent: 6,
  coordinatedElasticTrailingStepGainPercent: 10,
  coordinatedElasticTrailingStepWidenPercent: 1,
  coordinatedElasticTrailingMaxPercent: 10,
  coordinatedTrailingSpreadMultiplier: 2,
  coordinatedLossLadderEnabled: true,
  coordinatedLossLadder: [
    { loss_percent: 12, quantity_mode: 'percent_original', quantity: 10, confirmations: 2 },
    { loss_percent: 18, quantity_mode: 'percent_original', quantity: 20, confirmations: 2 },
    { loss_percent: 25, quantity_mode: 'percent_original', quantity: 30, confirmations: 2 },
    { loss_percent: 35, quantity_mode: 'percent_remaining', quantity: 100, confirmations: 1 },
  ],
  fillConfirmationTimeoutSeconds: 180,
  exitRepriceIntervalSeconds: 5,
  profitExitRepriceIntervalSeconds: 3,
  reversalExitEnabled: true,
  reversalWarningConfirmations: 3,
  reversalConfirmedConfirmations: 5,
  reversalWarningSellPercent: 25,
  reversalPremiumDrawdownPercent: 12,
  reversalReduceMinReturnPercent: 5,
  reversalReduceMinMfePercent: 20,
  adaptiveTrailingEnabled: true,
  adaptiveTrailingMinPercent: 8,
  adaptiveTrailingMaxPercent: 35,
  zeroDteLiquidationEnabled: true,
  zeroDteLiquidationTime: '15:40',

  // Stop Loss
  stopLossEnabled: true,
  stopLossPercentage: 30,
  stopLossOrderType: 'market',

  // Take Profit
  takeProfitEnabled: true,
  takeProfitPercentage: 50,
  takeProfitSellPercentage: 100,
  multiLevelTakeProfit: false,
  breakEvenEnabled: false,
  breakEvenActivationType: 'percent',
  breakEvenActivationPercentage: 10,
  breakEvenActivationCents: 10,

  // Trailing Stop
  trailingStopEnabled: true,
  trailingStopType: 'percent',
  trailingStopPercent: 25,
  trailingStopActivationPercent: 10,
  trailingStopCents: 0.25,
  trailingHours: 4,

  // Auto Shutdown
  autoShutdownEnabled: true,
  maxConsecutiveLosses: 3,
  maxDailyLosses: 5,
  maxDailyLossAmount: 250,
  maxDrawdownPercent: 20,

  // Correlation
  maxPositionsPerTicker: 3,
  maxPositionsPerSector: 3,
};

function isPositive(value: number): boolean {
  return Number.isFinite(value) && value > 0;
}

function isNonNegative(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

function getRiskSettingsValidationErrors(settings: RiskSettings): string[] {
  const errors: string[] = [];
  const positiveFields: [string, number][] = [
    ['Max position size', settings.maxPositionSize],
    ['Risk per trade', settings.riskPerTrade],
    ['Agreement size percent', settings.smartSizingAgreementPercent],
    ['Mixed size percent', settings.smartSizingMixedPercent],
    ['Conflict size percent', settings.smartSizingConflictPercent],
    ['Entry slippage warning', settings.entrySlippageWarningPercent],
    ['Entry slippage severe', settings.entrySlippageSeverePercent],
    ['Entry slippage warning size', settings.entrySlippageWarningSizePercent],
    ['Entry slippage severe size', settings.entrySlippageSevereSizePercent],
    ['Maximum loss per trade', settings.maxLossPerTrade],
    ['Exit quote maximum age', settings.coordinatedExitQuoteMaxAgeSeconds],
    ['Normal hard stop', settings.coordinatedNormalStopLossPercent],
    ['High-risk hard stop', settings.coordinatedHighRiskStopLossPercent],
    ['High-risk size percent', settings.coordinatedHighRiskSizePercent],
    ['Emergency stop', settings.coordinatedEmergencyStopLossPercent],
    ['Stop confirmation interval', settings.coordinatedStopConfirmationIntervalSeconds],
    ['First target', settings.coordinatedProfitStage1Percent],
    ['First target sell percent', settings.coordinatedProfitStage1SellPercent],
    ['Second target', settings.coordinatedProfitStage2Percent],
    ['Second target sell percent', settings.coordinatedProfitStage2SellPercent],
    ['Fast-scalp first target', settings.coordinatedFastScalpProfitStage1Percent],
    ['Fast-scalp second target', settings.coordinatedFastScalpProfitStage2Percent],
    ['Low-premium activation', settings.coordinatedLowActivationPercent],
    ['Low-premium trail', settings.coordinatedLowTrailingPercent],
    ['Medium-premium activation', settings.coordinatedMediumActivationPercent],
    ['Medium-premium trail', settings.coordinatedMediumTrailingPercent],
    ['High-premium activation', settings.coordinatedHighActivationPercent],
    ['High-premium trail', settings.coordinatedHighTrailingPercent],
    ['Trailing staircase gain step', settings.coordinatedTrailingStepGainPercent],
    ['Trailing staircase tightening', settings.coordinatedTrailingStepTightenPercent],
    ['Trailing staircase minimum', settings.coordinatedTrailingMinPercent],
    ['Trailing volatility gate', settings.coordinatedTrailingVolatilityGatePercent],
    ['Order confirmation timeout', settings.fillConfirmationTimeoutSeconds],
    ['Risk exit reprice interval', settings.exitRepriceIntervalSeconds],
    ['Profit exit reprice interval', settings.profitExitRepriceIntervalSeconds],
    ['Elastic minimum activation cents', settings.coordinatedElasticMinActivationCents],
    ['Elastic starting trail', settings.coordinatedElasticTrailingStartPercent],
    ['Elastic gain step', settings.coordinatedElasticTrailingStepGainPercent],
    ['Elastic widening step', settings.coordinatedElasticTrailingStepWidenPercent],
    ['Elastic maximum trail', settings.coordinatedElasticTrailingMaxPercent],
    ['Trailing spread multiplier', settings.coordinatedTrailingSpreadMultiplier],
    ['Stop loss percent', settings.stopLossPercentage],
    ['Take profit percent', settings.takeProfitPercentage],
    ['Take profit sell percent', settings.takeProfitSellPercentage],
    ['Break-even activation percent', settings.breakEvenActivationPercentage],
    ['Break-even activation cents', settings.breakEvenActivationCents],
    ['Trailing stop percent', settings.trailingStopPercent],
    ['Trailing stop cents', settings.trailingStopCents],
    ['Trailing hours', settings.trailingHours],
    ['Reversal warning sell percent', settings.reversalWarningSellPercent],
    ['Reversal premium drawdown percent', settings.reversalPremiumDrawdownPercent],
    ['Adaptive trailing minimum percent', settings.adaptiveTrailingMinPercent],
    ['Adaptive trailing maximum percent', settings.adaptiveTrailingMaxPercent],
    ['Max daily loss amount', settings.maxDailyLossAmount],
    ['Max drawdown percent', settings.maxDrawdownPercent],
  ];

  positiveFields.forEach(([label, value]) => {
    if (!isPositive(value)) errors.push(`${label} must be greater than 0.`);
  });

  const percentageFields: [string, number][] = [
    ['Agreement size percent', settings.smartSizingAgreementPercent],
    ['Mixed size percent', settings.smartSizingMixedPercent],
    ['Conflict size percent', settings.smartSizingConflictPercent],
    ['Entry slippage warning size', settings.entrySlippageWarningSizePercent],
    ['Entry slippage severe size', settings.entrySlippageSevereSizePercent],
    ['Trailing stop activation percent', settings.trailingStopActivationPercent],
    ['Normal hard stop', settings.coordinatedNormalStopLossPercent],
    ['High-risk hard stop', settings.coordinatedHighRiskStopLossPercent],
    ['High-risk size percent', settings.coordinatedHighRiskSizePercent],
    ['Emergency stop', settings.coordinatedEmergencyStopLossPercent],
    ['First target sell percent', settings.coordinatedProfitStage1SellPercent],
    ['Second target sell percent', settings.coordinatedProfitStage2SellPercent],
    ['Low-premium trail', settings.coordinatedLowTrailingPercent],
    ['Medium-premium trail', settings.coordinatedMediumTrailingPercent],
    ['High-premium trail', settings.coordinatedHighTrailingPercent],
  ];
  percentageFields.forEach(([label, value]) => {
    if (value > 100) errors.push(`${label} cannot exceed 100.`);
  });
  if (!isNonNegative(settings.trailingStopActivationPercent)) {
    errors.push('Trailing stop activation percent must be 0 or more.');
  }
  if (!isNonNegative(settings.coordinatedElasticActivationPercent)) {
    errors.push('Elastic activation percent must be 0 or more.');
  }
  if (settings.coordinatedElasticTrailingMaxPercent < settings.coordinatedElasticTrailingStartPercent) {
    errors.push('Elastic maximum trail must be at least the starting trail.');
  }
  settings.coordinatedLossLadder.forEach((step, index) => {
    if (!isPositive(step.loss_percent) || !isPositive(step.quantity) || !Number.isInteger(step.confirmations) || step.confirmations < 1) {
      errors.push(`Loss ladder step ${index + 1} requires positive loss and quantity values plus whole-number confirmations.`);
    }
  });

  if (!Number.isInteger(settings.defaultQuantity) || settings.defaultQuantity < 1) {
    errors.push('Default quantity must be a whole number of at least 1.');
  }
  if (!Number.isInteger(settings.coordinatedStopRequiredConfirmations) || settings.coordinatedStopRequiredConfirmations < 1) {
    errors.push('Stop confirmations must be a whole number of at least 1.');
  }
  if (!Number.isInteger(settings.coordinatedRunnerReserveQuantity) || settings.coordinatedRunnerReserveQuantity < 0) {
    errors.push('Runner reserve must be a whole number of 0 or more.');
  }
  if (!Number.isInteger(settings.maxConsecutiveLosses) || settings.maxConsecutiveLosses < 1) {
    errors.push('Max consecutive losses must be a whole number of at least 1.');
  }
  if (!Number.isInteger(settings.maxDailyLosses) || settings.maxDailyLosses < 1) {
    errors.push('Max daily losses must be a whole number of at least 1.');
  }
  if (!Number.isInteger(settings.maxPositionsPerTicker) || !isNonNegative(settings.maxPositionsPerTicker)) {
    errors.push('Max positions per ticker must be a whole number of 0 or more.');
  }
  if (!Number.isInteger(settings.maxPositionsPerSector) || !isNonNegative(settings.maxPositionsPerSector)) {
    errors.push('Max positions per sector must be a whole number of 0 or more.');
  }
  if (!Number.isInteger(settings.reversalWarningConfirmations) || settings.reversalWarningConfirmations < 1) {
    errors.push('Reversal warning confirmations must be a whole number of at least 1.');
  }
  if (!Number.isInteger(settings.reversalConfirmedConfirmations)
      || settings.reversalConfirmedConfirmations <= settings.reversalWarningConfirmations) {
    errors.push('Confirmed reversal count must be greater than the warning count.');
  }
  if (settings.adaptiveTrailingMaxPercent < settings.adaptiveTrailingMinPercent) {
    errors.push('Adaptive trailing maximum must be at least the minimum.');
  }
  if (settings.entrySlippageSeverePercent <= settings.entrySlippageWarningPercent) {
    errors.push('Severe entry slippage must be greater than warning slippage.');
  }
  if (settings.coordinatedFastScalpProfitStage2Percent <= settings.coordinatedFastScalpProfitStage1Percent) {
    errors.push('Fast-scalp second target must be greater than the first target.');
  }
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(settings.zeroDteLiquidationTime)) {
    errors.push('0DTE liquidation time must use 24-hour HH:MM format.');
  }

  return errors;
}

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
          <Text style={styles.coverageLabel}>live</Text>
        </View>
      </View>

      <View style={styles.briefingStats}>
        <RiskStat label="Live Guards" value={`${digest.enabledGuards}/6`} color={toneColor} />
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
            <Text style={styles.clearText}>Verified live automation guardrails are active.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

export default function RiskSettingsScreen() {
  const [activeTab, setActiveTab] = useState<TabType>('position');
  const [settings, setSettings] = useState<RiskSettings>(DEFAULT_RISK_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const updateSetting = <K extends keyof RiskSettings>(key: K, value: RiskSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const updateLossLadderStep = (index: number, patch: Partial<LossLadderStep>) => {
    updateSetting('coordinatedLossLadder', settings.coordinatedLossLadder.map((step, stepIndex) =>
      stepIndex === index ? { ...step, ...patch } : step
    ));
  };

  const fetchSettings = useCallback(async () => {
    try {
      const [settingsRes, riskRes, trailingRes, shutdownRes, correlationRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/settings`),
        api.get(`${BACKEND_URL}/api/risk-management-settings`),
        api.get(`${BACKEND_URL}/api/trailing-stop-settings`),
        api.get(`${BACKEND_URL}/api/auto-shutdown-settings`),
        api.get(`${BACKEND_URL}/api/correlation-settings`),
      ]);
      const base = settingsRes.data || {};
      const risk = riskRes.data || {};
      const trailing = trailingRes.data || {};
      const shutdown = shutdownRes.data || {};
      const correlation = correlationRes.data || {};

      setSettings(normalizeRiskSettingsState({
        defaults: DEFAULT_RISK_SETTINGS,
        base,
        risk,
        trailing,
        shutdown,
        correlation,
      }));
      setSettingsLoaded(true);
      setLoadError(null);
    } catch (error) {
      console.error('Risk settings load failed:', error);
      setLoadError('Risk settings could not load. Check the backend connection and retry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchSettings();
  }, [fetchSettings]);

  const retryFetchSettings = useCallback(() => {
    if (!settingsLoaded) setLoading(true);
    else setRefreshing(true);
    fetchSettings();
  }, [fetchSettings, settingsLoaded]);

  const validationErrors = getRiskSettingsValidationErrors(settings);
  const hasInvalidSettings = validationErrors.length > 0;

  const saveSettings = async () => {
    if (!settingsLoaded) {
      Alert.alert('Settings Not Loaded', 'Risk settings must load successfully before they can be saved.');
      return;
    }
    if (hasInvalidSettings) {
      Alert.alert('Invalid Settings', validationErrors[0]);
      return;
    }
    setSaving(true);
    try {
      await Promise.all([
        api.put(`${BACKEND_URL}/api/settings`, {
          max_position_size: settings.maxPositionSize,
          default_quantity: settings.defaultQuantity,
          risk_per_trade: settings.riskPerTrade,
          smart_sizing_enabled: settings.smartSizingEnabled,
          smart_sizing_agreement_percent: settings.smartSizingAgreementPercent,
          smart_sizing_mixed_percent: settings.smartSizingMixedPercent,
          smart_sizing_conflict_percent: settings.smartSizingConflictPercent,
          entry_slippage_sizing_enabled: settings.entrySlippageSizingEnabled,
          entry_slippage_mode: settings.entrySlippageMode,
          entry_slippage_warning_percent: settings.entrySlippageWarningPercent,
          entry_slippage_severe_percent: settings.entrySlippageSeverePercent,
          entry_slippage_warning_size_percent: settings.entrySlippageWarningSizePercent,
          entry_slippage_severe_size_percent: settings.entrySlippageSevereSizePercent,
          marketable_entry_enabled: settings.marketableEntryEnabled,
          risk_budget_sizing_enabled: settings.riskBudgetSizingEnabled,
          max_loss_per_trade: settings.maxLossPerTrade,
          coordinated_exit_enabled: settings.coordinatedExitEnabled,
          coordinated_exit_quote_max_age_seconds: settings.coordinatedExitQuoteMaxAgeSeconds,
          coordinated_normal_stop_loss_percent: settings.coordinatedNormalStopLossPercent,
          coordinated_high_risk_stop_loss_percent: settings.coordinatedHighRiskStopLossPercent,
          coordinated_high_risk_size_percent: settings.coordinatedHighRiskSizePercent,
          coordinated_emergency_stop_loss_percent: settings.coordinatedEmergencyStopLossPercent,
          coordinated_stop_required_confirmations: settings.coordinatedStopRequiredConfirmations,
          coordinated_stop_confirmation_interval_seconds: settings.coordinatedStopConfirmationIntervalSeconds,
          coordinated_runner_reserve_quantity: settings.coordinatedRunnerReserveQuantity,
          coordinated_profit_stage_1_percent: settings.coordinatedProfitStage1Percent,
          coordinated_profit_stage_1_sell_percent: settings.coordinatedProfitStage1SellPercent,
          coordinated_profit_stage_2_percent: settings.coordinatedProfitStage2Percent,
          coordinated_profit_stage_2_sell_percent: settings.coordinatedProfitStage2SellPercent,
          coordinated_fast_scalp_profit_stage_1_percent: settings.coordinatedFastScalpProfitStage1Percent,
          coordinated_fast_scalp_profit_stage_2_percent: settings.coordinatedFastScalpProfitStage2Percent,
          coordinated_low_activation_percent: settings.coordinatedLowActivationPercent,
          coordinated_low_trailing_percent: settings.coordinatedLowTrailingPercent,
          coordinated_medium_activation_percent: settings.coordinatedMediumActivationPercent,
          coordinated_medium_trailing_percent: settings.coordinatedMediumTrailingPercent,
          coordinated_high_activation_percent: settings.coordinatedHighActivationPercent,
          coordinated_high_trailing_percent: settings.coordinatedHighTrailingPercent,
          coordinated_progressive_trailing_enabled: settings.coordinatedProgressiveTrailingEnabled,
          coordinated_trailing_mode: settings.coordinatedTrailingMode,
          coordinated_trailing_step_gain_percent: settings.coordinatedTrailingStepGainPercent,
          coordinated_trailing_step_tighten_percent: settings.coordinatedTrailingStepTightenPercent,
          coordinated_trailing_min_percent: settings.coordinatedTrailingMinPercent,
          coordinated_trailing_volatility_gate_percent: settings.coordinatedTrailingVolatilityGatePercent,
          coordinated_elastic_activation_percent: settings.coordinatedElasticActivationPercent,
          coordinated_elastic_min_activation_cents: settings.coordinatedElasticMinActivationCents,
          coordinated_elastic_trailing_start_percent: settings.coordinatedElasticTrailingStartPercent,
          coordinated_elastic_trailing_step_gain_percent: settings.coordinatedElasticTrailingStepGainPercent,
          coordinated_elastic_trailing_step_widen_percent: settings.coordinatedElasticTrailingStepWidenPercent,
          coordinated_elastic_trailing_max_percent: settings.coordinatedElasticTrailingMaxPercent,
          coordinated_trailing_spread_multiplier: settings.coordinatedTrailingSpreadMultiplier,
          coordinated_loss_ladder_enabled: settings.coordinatedLossLadderEnabled,
          coordinated_loss_ladder: settings.coordinatedLossLadder,
          fill_confirmation_timeout_seconds: settings.fillConfirmationTimeoutSeconds,
          exit_reprice_interval_seconds: settings.exitRepriceIntervalSeconds,
          profit_exit_reprice_interval_seconds: settings.profitExitRepriceIntervalSeconds,
          reversal_exit_enabled: settings.reversalExitEnabled,
          reversal_warning_confirmations: settings.reversalWarningConfirmations,
          reversal_confirmed_confirmations: settings.reversalConfirmedConfirmations,
          reversal_warning_sell_percent: settings.reversalWarningSellPercent,
          reversal_premium_drawdown_percent: settings.reversalPremiumDrawdownPercent,
          reversal_reduce_min_return_percent: settings.reversalReduceMinReturnPercent,
          reversal_reduce_min_mfe_percent: settings.reversalReduceMinMfePercent,
          adaptive_trailing_enabled: settings.adaptiveTrailingEnabled,
          adaptive_trailing_min_percent: settings.adaptiveTrailingMinPercent,
          adaptive_trailing_max_percent: settings.adaptiveTrailingMaxPercent,
          zero_dte_liquidation_enabled: settings.zeroDteLiquidationEnabled,
          zero_dte_liquidation_time: settings.zeroDteLiquidationTime,
          trailing_hours: settings.trailingHours,
          max_drawdown_percent: settings.maxDrawdownPercent,
          max_positions_per_sector: settings.maxPositionsPerSector,
        }),
        api.put(`${BACKEND_URL}/api/risk-management-settings`, {
          take_profit_enabled: settings.takeProfitEnabled,
          take_profit_percentage: settings.takeProfitPercentage,
          take_profit_sell_percentage: settings.takeProfitSellPercentage,
          bracket_order_enabled: settings.multiLevelTakeProfit,
          break_even_enabled: settings.breakEvenEnabled,
          break_even_activation_type: settings.breakEvenActivationType,
          break_even_activation_percentage: settings.breakEvenActivationPercentage,
          break_even_activation_cents: settings.breakEvenActivationCents,
          stop_loss_enabled: settings.stopLossEnabled,
          stop_loss_percentage: settings.stopLossPercentage,
          stop_loss_order_type: settings.stopLossOrderType,
        }),
        api.put(`${BACKEND_URL}/api/trailing-stop-settings`, {
          trailing_stop_enabled: settings.trailingStopEnabled,
          trailing_stop_type: settings.trailingStopType,
          trailing_stop_percent: settings.trailingStopPercent,
          trailing_stop_activation_percent: settings.trailingStopActivationPercent,
          trailing_stop_cents: settings.trailingStopCents,
        }),
        api.put(`${BACKEND_URL}/api/auto-shutdown-settings`, {
          auto_shutdown_enabled: settings.autoShutdownEnabled,
          max_consecutive_losses: settings.maxConsecutiveLosses,
          max_daily_losses: settings.maxDailyLosses,
          max_daily_loss_amount: settings.maxDailyLossAmount,
        }),
        api.put(`${BACKEND_URL}/api/correlation-settings?max_positions_per_ticker=${settings.maxPositionsPerTicker}`),
      ]);
      setLoadError(null);
      Alert.alert('Saved', 'Risk settings saved successfully');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to save risk settings');
    } finally {
      setSaving(false);
    }
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

            <View style={styles.divider} />

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.fieldTitleBlock}>
                  <Text style={styles.label}>Smart Entry Sizing</Text>
                  <Text style={styles.fieldHint}>Market agreement adjusts alert quantity; valid alerts keep a one-contract floor.</Text>
                </View>
                <Switch
                  value={settings.smartSizingEnabled}
                  onValueChange={v => updateSetting('smartSizingEnabled', v)}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Entry Slippage Mode</Text>
              <View style={styles.presetRow}>
                {(['disabled', 'binary', 'tiered'] as const).map(mode => (
                  <TouchableOpacity
                    key={mode}
                    style={[styles.presetButton, settings.entrySlippageMode === mode && styles.presetButtonActive]}
                    onPress={() => updateSetting('entrySlippageMode', mode)}
                  >
                    <Text style={[styles.presetText, settings.entrySlippageMode === mode && styles.presetTextActive]}>
                      {mode === 'disabled' ? 'Full Size' : mode === 'binary' ? 'Full or Skip' : 'Tiered'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={styles.sizingTierRow}>
              {([
                ['Agreement', 'smartSizingAgreementPercent'],
                ['Mixed', 'smartSizingMixedPercent'],
                ['Conflict', 'smartSizingConflictPercent'],
              ] as const).map(([label, key]) => (
                <View key={key} style={styles.sizingTierField}>
                  <Text style={styles.label}>{label} (%)</Text>
                  <TextInput
                    style={[styles.input, !settings.smartSizingEnabled && styles.inputDisabled]}
                    value={String(settings[key])}
                    onChangeText={v => updateSetting(key, Number(v))}
                    keyboardType="numeric"
                    editable={settings.smartSizingEnabled}
                  />
                </View>
              ))}
            </View>

            <View style={styles.divider} />

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.fieldTitleBlock}>
                  <Text style={styles.label}>Entry Slippage Sizing</Text>
                  <Text style={styles.fieldHint}>Keep the entry, but reduce contracts when the live ask has moved above the alert.</Text>
                </View>
                <Switch value={settings.entrySlippageSizingEnabled} onValueChange={v => updateSetting('entrySlippageSizingEnabled', v)} />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Warning / Severe Slippage (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.entrySlippageWarningPercent)} onChangeText={v => updateSetting('entrySlippageWarningPercent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.entrySlippageSeverePercent)} onChangeText={v => updateSetting('entrySlippageSeverePercent', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Warning / Severe Position Size (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.entrySlippageWarningSizePercent)} onChangeText={v => updateSetting('entrySlippageWarningSizePercent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.entrySlippageSevereSizePercent)} onChangeText={v => updateSetting('entrySlippageSevereSizePercent', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.fieldTitleBlock}>
                  <Text style={styles.label}>Marketable Entry Limit</Text>
                  <Text style={styles.fieldHint}>Use the current option ask as the limit while slippage sizing controls exposure.</Text>
                </View>
                <Switch value={settings.marketableEntryEnabled} onValueChange={v => updateSetting('marketableEntryEnabled', v)} />
              </View>
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

            <View style={styles.field}>
              <Text style={styles.label}>Take Profit Sell Size (%)</Text>
              <TextInput
                style={[styles.input, !settings.takeProfitEnabled && styles.inputDisabled]}
                value={String(settings.takeProfitSellPercentage)}
                onChangeText={v => updateSetting('takeProfitSellPercentage', Number(v))}
                keyboardType="numeric"
                editable={settings.takeProfitEnabled}
              />
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <Text style={styles.label}>Enable Break Even</Text>
                <Switch
                  value={settings.breakEvenEnabled}
                  onValueChange={v => updateSetting('breakEvenEnabled', v)}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Break-Even Activation Type</Text>
              <View style={styles.presetRow}>
                {[{ value: 'percent', label: '% Percent' }, { value: 'cents', label: '¢ Cents' }].map(option => (
                  <TouchableOpacity
                    key={option.value}
                    style={[
                      styles.presetButton,
                      settings.breakEvenActivationType === option.value && styles.presetButtonActive,
                    ]}
                    onPress={() => updateSetting('breakEvenActivationType', option.value)}
                    disabled={!settings.breakEvenEnabled}
                  >
                    <Text
                      style={[
                        styles.presetText,
                        settings.breakEvenActivationType === option.value && styles.presetTextActive,
                      ]}
                    >
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>
                {settings.breakEvenActivationType === 'cents' ? 'Break-Even Activation (¢)' : 'Break-Even Activation (%)'}
              </Text>
              <View style={styles.presetRow}>
                {[5, 10, 15, 20].map(value => (
                  <TouchableOpacity
                    key={value}
                    style={[
                      styles.presetButton,
                      (settings.breakEvenActivationType === 'cents'
                        ? settings.breakEvenActivationCents
                        : settings.breakEvenActivationPercentage) === value && styles.presetButtonActive,
                    ]}
                    onPress={() => updateSetting(
                      settings.breakEvenActivationType === 'cents'
                        ? 'breakEvenActivationCents'
                        : 'breakEvenActivationPercentage',
                      value,
                    )}
                    disabled={!settings.breakEvenEnabled}
                  >
                    <Text
                      style={[
                        styles.presetText,
                        (settings.breakEvenActivationType === 'cents'
                          ? settings.breakEvenActivationCents
                          : settings.breakEvenActivationPercentage) === value && styles.presetTextActive,
                      ]}
                    >
                      {value}{settings.breakEvenActivationType === 'cents' ? '¢' : '%'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TextInput
                style={[styles.input, !settings.breakEvenEnabled && styles.inputDisabled]}
                value={String(settings.breakEvenActivationType === 'cents'
                  ? settings.breakEvenActivationCents
                  : settings.breakEvenActivationPercentage)}
                onChangeText={v => updateSetting(
                  settings.breakEvenActivationType === 'cents'
                    ? 'breakEvenActivationCents'
                    : 'breakEvenActivationPercentage',
                  Number(v),
                )}
                keyboardType="numeric"
                editable={settings.breakEvenEnabled}
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

      case 'intelligence':
        return (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Options Exit Intelligence</Text>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Coordinated Exit Lifecycle</Text>
                  <Text style={styles.helperText}>Uses one premium-aware state machine for loss protection, staged profits, the profit floor, and the final runner.</Text>
                </View>
                <Switch
                  value={settings.coordinatedExitEnabled}
                  onValueChange={v => updateSetting('coordinatedExitEnabled', v)}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Trailing Algorithm</Text>
              <View style={styles.presetRow}>
                {(['fixed', 'tightening', 'elastic'] as const).map(mode => (
                  <TouchableOpacity
                    key={mode}
                    style={[styles.presetButton, settings.coordinatedTrailingMode === mode && styles.presetButtonActive]}
                    onPress={() => updateSetting('coordinatedTrailingMode', mode)}
                  >
                    <Text style={[styles.presetText, settings.coordinatedTrailingMode === mode && styles.presetTextActive]}>
                      {mode === 'fixed' ? 'Fixed' : mode === 'tightening' ? 'Tightening' : 'Elastic'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Loss-Budget Sizing</Text>
                  <Text style={styles.helperText}>Caps entry contracts by the estimated loss at the applicable hard stop.</Text>
                </View>
                <Switch
                  value={settings.riskBudgetSizingEnabled}
                  onValueChange={v => updateSetting('riskBudgetSizingEnabled', v)}
                />
              </View>
              <TextInput
                style={[styles.input, !settings.riskBudgetSizingEnabled && styles.inputDisabled]}
                value={String(settings.maxLossPerTrade)}
                onChangeText={v => updateSetting('maxLossPerTrade', Number(v))}
                keyboardType="numeric"
                editable={settings.riskBudgetSizingEnabled}
                placeholder="Maximum loss per trade ($)"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Normal Stop / High-Risk Stop / High-Risk Size (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedNormalStopLossPercent)} onChangeText={v => updateSetting('coordinatedNormalStopLossPercent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedHighRiskStopLossPercent)} onChangeText={v => updateSetting('coordinatedHighRiskStopLossPercent', Number(v))} keyboardType="numeric" />
              </View>
              <TextInput style={styles.input} value={String(settings.coordinatedHighRiskSizePercent)} onChangeText={v => updateSetting('coordinatedHighRiskSizePercent', Number(v))} keyboardType="numeric" />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Emergency Stop (%)</Text>
              <Text style={styles.helperText}>Exits immediately at this loss; the normal stop waits for confirmed quotes.</Text>
              <TextInput style={styles.input} value={String(settings.coordinatedEmergencyStopLossPercent)} onChangeText={v => updateSetting('coordinatedEmergencyStopLossPercent', Number(v))} keyboardType="numeric" />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Stop Confirmations / Interval (seconds)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedStopRequiredConfirmations)} onChangeText={v => updateSetting('coordinatedStopRequiredConfirmations', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedStopConfirmationIntervalSeconds)} onChangeText={v => updateSetting('coordinatedStopConfirmationIntervalSeconds', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Protected Runner Contracts</Text>
              <Text style={styles.helperText}>Profit stages cannot consume this many final contracts after trailing protection is earned.</Text>
              <TextInput style={styles.input} value={String(settings.coordinatedRunnerReserveQuantity)} onChangeText={v => updateSetting('coordinatedRunnerReserveQuantity', Number(v))} keyboardType="numeric" />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Profit Target / Original Position Sold (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedProfitStage1Percent)} onChangeText={v => updateSetting('coordinatedProfitStage1Percent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedProfitStage1SellPercent)} onChangeText={v => updateSetting('coordinatedProfitStage1SellPercent', Number(v))} keyboardType="numeric" />
              </View>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedProfitStage2Percent)} onChangeText={v => updateSetting('coordinatedProfitStage2Percent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedProfitStage2SellPercent)} onChangeText={v => updateSetting('coordinatedProfitStage2SellPercent', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Fast-Scalp Profit Targets (%)</Text>
              <Text style={styles.helperText}>Used when Mike explicitly says he is looking for a sudden profit or a quick scalp.</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedFastScalpProfitStage1Percent)} onChangeText={v => updateSetting('coordinatedFastScalpProfitStage1Percent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedFastScalpProfitStage2Percent)} onChangeText={v => updateSetting('coordinatedFastScalpProfitStage2Percent', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Low / Medium / High Premium: Activation and Trail (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedLowActivationPercent)} onChangeText={v => updateSetting('coordinatedLowActivationPercent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedLowTrailingPercent)} onChangeText={v => updateSetting('coordinatedLowTrailingPercent', Number(v))} keyboardType="numeric" />
              </View>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedMediumActivationPercent)} onChangeText={v => updateSetting('coordinatedMediumActivationPercent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedMediumTrailingPercent)} onChangeText={v => updateSetting('coordinatedMediumTrailingPercent', Number(v))} keyboardType="numeric" />
              </View>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedHighActivationPercent)} onChangeText={v => updateSetting('coordinatedHighActivationPercent', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedHighTrailingPercent)} onChangeText={v => updateSetting('coordinatedHighTrailingPercent', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Volatility-Gated Staircase</Text>
                  <Text style={styles.helperText}>Tightens the trail as profit advances, but pauses new steps while premium movement is noisy.</Text>
                </View>
                <Switch
                  value={settings.coordinatedProgressiveTrailingEnabled}
                  onValueChange={v => updateSetting('coordinatedProgressiveTrailingEnabled', v)}
                />
              </View>
              <Text style={styles.label}>Gain Step / Tighten By / Minimum Trail / Volatility Gate (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedTrailingStepGainPercent)} onChangeText={v => updateSetting('coordinatedTrailingStepGainPercent', Number(v))} keyboardType="numeric" editable={settings.coordinatedProgressiveTrailingEnabled} />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedTrailingStepTightenPercent)} onChangeText={v => updateSetting('coordinatedTrailingStepTightenPercent', Number(v))} keyboardType="numeric" editable={settings.coordinatedProgressiveTrailingEnabled} />
              </View>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedTrailingMinPercent)} onChangeText={v => updateSetting('coordinatedTrailingMinPercent', Number(v))} keyboardType="numeric" editable={settings.coordinatedProgressiveTrailingEnabled} />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedTrailingVolatilityGatePercent)} onChangeText={v => updateSetting('coordinatedTrailingVolatilityGatePercent', Number(v))} keyboardType="numeric" editable={settings.coordinatedProgressiveTrailingEnabled} />
              </View>
            </View>

            {settings.coordinatedTrailingMode === 'elastic' && (
              <View style={styles.field}>
                <Text style={styles.label}>Elastic Activation % / Minimum Cents / Start Trail %</Text>
                <View style={styles.inlineInputs}>
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedElasticActivationPercent)} onChangeText={v => updateSetting('coordinatedElasticActivationPercent', Number(v))} keyboardType="numeric" />
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedElasticMinActivationCents)} onChangeText={v => updateSetting('coordinatedElasticMinActivationCents', Number(v))} keyboardType="numeric" />
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedElasticTrailingStartPercent)} onChangeText={v => updateSetting('coordinatedElasticTrailingStartPercent', Number(v))} keyboardType="numeric" />
                </View>
                <Text style={styles.label}>Gain Step % / Widen By % / Maximum Trail % / Spread Multiple</Text>
                <View style={styles.inlineInputs}>
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedElasticTrailingStepGainPercent)} onChangeText={v => updateSetting('coordinatedElasticTrailingStepGainPercent', Number(v))} keyboardType="numeric" />
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedElasticTrailingStepWidenPercent)} onChangeText={v => updateSetting('coordinatedElasticTrailingStepWidenPercent', Number(v))} keyboardType="numeric" />
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedElasticTrailingMaxPercent)} onChangeText={v => updateSetting('coordinatedElasticTrailingMaxPercent', Number(v))} keyboardType="numeric" />
                  <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.coordinatedTrailingSpreadMultiplier)} onChangeText={v => updateSetting('coordinatedTrailingSpreadMultiplier', Number(v))} keyboardType="numeric" />
                </View>
              </View>
            )}

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Descending Loss Ladder</Text>
                  <Text style={styles.helperText}>Reduces contracts in stages as premium loss deepens.</Text>
                </View>
                <View style={styles.ladderActions}>
                  <TouchableOpacity
                    style={styles.iconButton}
                    onPress={() => updateSetting('coordinatedLossLadder', [
                      ...settings.coordinatedLossLadder,
                      { loss_percent: 40, quantity_mode: 'percent_remaining', quantity: 100, confirmations: 1 },
                    ])}
                    accessibilityLabel="Add loss ladder step"
                  >
                    <Ionicons name="add" size={18} color="#edf3ff" />
                  </TouchableOpacity>
                  <Switch value={settings.coordinatedLossLadderEnabled} onValueChange={v => updateSetting('coordinatedLossLadderEnabled', v)} />
                </View>
              </View>
              {settings.coordinatedLossLadder.map((step, index) => (
                <View key={`loss-step-${index}`} style={styles.lossStep}>
                  <View style={styles.row}>
                    <Text style={styles.label}>Step {index + 1}: Loss % / Quantity / Confirmations</Text>
                    <TouchableOpacity
                      style={styles.iconButton}
                      onPress={() => updateSetting('coordinatedLossLadder', settings.coordinatedLossLadder.filter((_, stepIndex) => stepIndex !== index))}
                      disabled={settings.coordinatedLossLadder.length === 1}
                      accessibilityLabel={`Remove loss ladder step ${index + 1}`}
                    >
                      <Ionicons name="trash-outline" size={16} color={settings.coordinatedLossLadder.length === 1 ? '#68779b' : '#fb7185'} />
                    </TouchableOpacity>
                  </View>
                  <View style={styles.inlineInputs}>
                    <TextInput style={[styles.input, styles.inlineInput]} value={String(step.loss_percent)} onChangeText={v => updateLossLadderStep(index, { loss_percent: Number(v) })} keyboardType="numeric" />
                    <TextInput style={[styles.input, styles.inlineInput]} value={String(step.quantity)} onChangeText={v => updateLossLadderStep(index, { quantity: Number(v) })} keyboardType="numeric" />
                    <TextInput style={[styles.input, styles.inlineInput]} value={String(step.confirmations)} onChangeText={v => updateLossLadderStep(index, { confirmations: Number(v) })} keyboardType="numeric" />
                  </View>
                  <View style={styles.presetRow}>
                    {(['percent_original', 'percent_remaining', 'fixed'] as const).map(mode => (
                      <TouchableOpacity key={mode} style={[styles.presetButton, step.quantity_mode === mode && styles.presetButtonActive]} onPress={() => updateLossLadderStep(index, { quantity_mode: mode })}>
                        <Text style={[styles.presetText, step.quantity_mode === mode && styles.presetTextActive]}>{mode === 'percent_original' ? '% Original' : mode === 'percent_remaining' ? '% Remaining' : 'Contracts'}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ))}
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Entry Confirmation / Risk Exit Reprice / Profit Exit Reprice (seconds)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.fillConfirmationTimeoutSeconds)} onChangeText={v => updateSetting('fillConfirmationTimeoutSeconds', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.exitRepriceIntervalSeconds)} onChangeText={v => updateSetting('exitRepriceIntervalSeconds', Number(v))} keyboardType="numeric" />
                <TextInput style={[styles.input, styles.inlineInput]} value={String(settings.profitExitRepriceIntervalSeconds)} onChangeText={v => updateSetting('profitExitRepriceIntervalSeconds', Number(v))} keyboardType="numeric" />
              </View>
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Reversal-Aware Exits</Text>
                  <Text style={styles.helperText}>Trim after a persistent warning and close after a confirmed reversal.</Text>
                </View>
                <Switch
                  value={settings.reversalExitEnabled}
                  onValueChange={v => updateSetting('reversalExitEnabled', v)}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Warning / Confirmed Observations</Text>
              <View style={styles.inlineInputs}>
                <TextInput
                  style={[styles.input, styles.inlineInput, !settings.reversalExitEnabled && styles.inputDisabled]}
                  value={String(settings.reversalWarningConfirmations)}
                  onChangeText={v => updateSetting('reversalWarningConfirmations', Number(v))}
                  keyboardType="numeric"
                  editable={settings.reversalExitEnabled}
                />
                <TextInput
                  style={[styles.input, styles.inlineInput, !settings.reversalExitEnabled && styles.inputDisabled]}
                  value={String(settings.reversalConfirmedConfirmations)}
                  onChangeText={v => updateSetting('reversalConfirmedConfirmations', Number(v))}
                  keyboardType="numeric"
                  editable={settings.reversalExitEnabled}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Warning Trim / Premium Drawdown (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput
                  style={[styles.input, styles.inlineInput, !settings.reversalExitEnabled && styles.inputDisabled]}
                  value={String(settings.reversalWarningSellPercent)}
                  onChangeText={v => updateSetting('reversalWarningSellPercent', Number(v))}
                  keyboardType="numeric"
                  editable={settings.reversalExitEnabled}
                />
                <TextInput
                  style={[styles.input, styles.inlineInput, !settings.reversalExitEnabled && styles.inputDisabled]}
                  value={String(settings.reversalPremiumDrawdownPercent)}
                  onChangeText={v => updateSetting('reversalPremiumDrawdownPercent', Number(v))}
                  keyboardType="numeric"
                  editable={settings.reversalExitEnabled}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Reduce Only After Current Profit / Earlier Maximum Profit (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput style={[styles.input, styles.inlineInput, !settings.reversalExitEnabled && styles.inputDisabled]} value={String(settings.reversalReduceMinReturnPercent)} onChangeText={v => updateSetting('reversalReduceMinReturnPercent', Number(v))} keyboardType="numeric" editable={settings.reversalExitEnabled} />
                <TextInput style={[styles.input, styles.inlineInput, !settings.reversalExitEnabled && styles.inputDisabled]} value={String(settings.reversalReduceMinMfePercent)} onChangeText={v => updateSetting('reversalReduceMinMfePercent', Number(v))} keyboardType="numeric" editable={settings.reversalExitEnabled} />
              </View>
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Adaptive Trailing Distance</Text>
                  <Text style={styles.helperText}>Uses spread, premium movement, expiry, and market alignment when trailing is enabled.</Text>
                </View>
                <Switch
                  value={settings.adaptiveTrailingEnabled}
                  onValueChange={v => updateSetting('adaptiveTrailingEnabled', v)}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Adaptive Minimum / Maximum (%)</Text>
              <View style={styles.inlineInputs}>
                <TextInput
                  style={[styles.input, styles.inlineInput, !settings.adaptiveTrailingEnabled && styles.inputDisabled]}
                  value={String(settings.adaptiveTrailingMinPercent)}
                  onChangeText={v => updateSetting('adaptiveTrailingMinPercent', Number(v))}
                  keyboardType="numeric"
                  editable={settings.adaptiveTrailingEnabled}
                />
                <TextInput
                  style={[styles.input, styles.inlineInput, !settings.adaptiveTrailingEnabled && styles.inputDisabled]}
                  value={String(settings.adaptiveTrailingMaxPercent)}
                  onChangeText={v => updateSetting('adaptiveTrailingMaxPercent', Number(v))}
                  keyboardType="numeric"
                  editable={settings.adaptiveTrailingEnabled}
                />
              </View>
            </View>

            <View style={styles.field}>
              <View style={styles.row}>
                <View style={styles.labelBlock}>
                  <Text style={styles.label}>Mandatory 0DTE Liquidation</Text>
                  <Text style={styles.helperText}>Closes same-day option positions and cancels unfilled same-day entries at the cutoff.</Text>
                </View>
                <Switch
                  value={settings.zeroDteLiquidationEnabled}
                  onValueChange={v => updateSetting('zeroDteLiquidationEnabled', v)}
                />
              </View>
              <TextInput
                style={[styles.input, !settings.zeroDteLiquidationEnabled && styles.inputDisabled]}
                value={settings.zeroDteLiquidationTime}
                onChangeText={v => updateSetting('zeroDteLiquidationTime', v)}
                placeholder="15:40"
                editable={settings.zeroDteLiquidationEnabled}
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Activate After Profit (%)</Text>
              <Text style={styles.helperText}>
                The trailing stop remains inactive until the option reaches this gain from its entry price.
              </Text>
              <TextInput
                style={[styles.input, !settings.trailingStopEnabled && styles.inputDisabled]}
                value={String(settings.trailingStopActivationPercent)}
                onChangeText={v => updateSetting('trailingStopActivationPercent', Number(v))}
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

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#f43f5e" />
        </View>
      </SafeAreaView>
    );
  }

  const digest = summarizeRiskSettings(settings);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#f43f5e" />}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>RISK CONTROLS</Text>
            <Text style={styles.title}>Risk Management</Text>
          </View>
          <View style={styles.headerBadge}>
            <Ionicons name="shield-outline" size={14} color="#f43f5e" />
            <Text style={styles.headerBadgeText}>{digest.enabledGuards}/6 guards</Text>
          </View>
        </View>

        <RiskBriefing digest={digest} />

        {loadError && (
          <View style={styles.errorBanner}>
            <Ionicons name="warning-outline" size={16} color="#f59e0b" />
            <Text style={styles.errorBannerText}>{loadError}</Text>
            <TouchableOpacity
              style={styles.errorBannerRetry}
              onPress={retryFetchSettings}
              accessibilityRole="button"
            >
              <Ionicons name="refresh" size={13} color="#070812" />
              <Text style={styles.errorBannerRetryText}>Retry</Text>
            </TouchableOpacity>
          </View>
        )}

        {hasInvalidSettings && (
          <View style={styles.errorBanner}>
            <Ionicons name="alert-circle-outline" size={16} color="#f59e0b" />
            <Text style={styles.errorBannerText}>{validationErrors[0]}</Text>
          </View>
        )}
        
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
          <TouchableOpacity
            style={[styles.saveButton, (saving || !settingsLoaded || hasInvalidSettings) && styles.saveButtonDisabled]}
            onPress={saveSettings}
            disabled={saving || !settingsLoaded || hasInvalidSettings}
            accessibilityRole="button"
          >
            {saving ? (
              <ActivityIndicator size="small" color="#070812" />
            ) : (
              <Ionicons name="save-outline" size={18} color="#070812" />
            )}
            <Text style={styles.saveButtonText}>
              {saving ? 'Saving...' : !settingsLoaded ? 'Load Required' : hasInvalidSettings ? 'Fix Settings' : 'Save Settings'}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050416' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  content: { padding: 16, paddingBottom: 32 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 },
  eyebrow: { color: '#f43f5e', fontSize: 10, fontWeight: '800', letterSpacing: 1.8, marginBottom: 2 },
  title: { fontSize: 26, fontWeight: '800', color: '#edf3ff' },
  headerBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    borderWidth: 1,
    borderColor: '#164766',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  headerBadgeText: { color: '#fb7185', fontSize: 11, fontWeight: '800' },
  briefingCard: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginBottom: 12,
  },
  briefingTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  briefingTitleBlock: { flex: 1 },
  briefingEyebrow: { color: '#68779b', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, marginBottom: 5 },
  briefingTitle: { color: '#edf3ff', fontSize: 18, fontWeight: '900' },
  briefingDetail: { color: '#aec0e5', fontSize: 12, lineHeight: 17, marginTop: 3 },
  coverageBadge: { minWidth: 84, height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  coverageValue: { fontSize: 18, fontWeight: '900' },
  coverageLabel: { color: '#68779b', fontSize: 10, fontWeight: '800', marginTop: 1 },
  briefingStats: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(41, 33, 58, 0.82)',
  },
  briefingStat: { flex: 1, alignItems: 'center' },
  briefingStatValue: { color: '#edf3ff', fontSize: 14, fontWeight: '900' },
  briefingStatLabel: { color: '#68779b', fontSize: 9, fontWeight: '800', marginTop: 3 },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#18283c',
    padding: 10,
  },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#68779b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#aec0e5', fontSize: 12, fontWeight: '700', flex: 1 },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
    padding: 10,
    borderRadius: 8,
    backgroundColor: '#1c1500',
    borderWidth: 1,
    borderColor: '#92400e',
  },
  errorBannerText: { flex: 1, color: '#f59e0b', fontSize: 12, fontWeight: '700' },
  errorBannerRetry: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#f59e0b',
    borderRadius: 6,
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  errorBannerRetryText: { color: '#070812', fontSize: 11, fontWeight: '900' },
  tabBar: { marginBottom: 12 },
  tabRow: { flexDirection: 'row', gap: 8, paddingRight: 16 },
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 8,
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderWidth: 1,
    borderColor: '#29213a',
  },
  tabActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  tabText: { color: '#68779b', fontSize: 13, fontWeight: '700' },
  tabTextActive: { color: '#fb7185' },
  section: {
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#29213a',
  },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: '#edf3ff', marginBottom: 16 },
  field: { marginBottom: 16 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  labelBlock: { flex: 1 },
  helperText: { color: '#68779b', fontSize: 11, lineHeight: 15 },
  inlineInputs: { flexDirection: 'row', gap: 10 },
  lossStep: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#302b45' },
  ladderActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  iconButton: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  inlineInput: { flex: 1, minWidth: 0 },
  fieldTitleBlock: { flex: 1 },
  fieldHint: { color: '#68779b', fontSize: 11, lineHeight: 15 },
  divider: { height: 1, backgroundColor: '#29213a', marginBottom: 16 },
  sizingTierRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  sizingTierField: { flexGrow: 1, flexBasis: 92, minWidth: 92 },
  label: { color: '#aec0e5', fontSize: 13, fontWeight: '700', marginBottom: 6 },
  input: {
    backgroundColor: 'rgba(21, 16, 33, 0.72)',
    color: '#edf3ff',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#29213a',
    fontSize: 16,
    fontWeight: '700',
  },
  inputDisabled: { opacity: 0.45 },
  presetRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  presetButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#29213a',
    borderWidth: 1,
    borderColor: '#29213a',
  },
  presetButtonActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)', borderColor: '#f43f5e' },
  presetText: { color: '#68779b', fontSize: 12, fontWeight: '800' },
  presetTextActive: { color: '#fb7185' },
  buttonContainer: { marginTop: 4, marginBottom: 32 },
  saveButton: {
    minHeight: 48,
    borderRadius: 10,
    backgroundColor: '#f43f5e',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  saveButtonDisabled: { opacity: 0.7 },
  saveButtonText: { color: '#070812', fontSize: 15, fontWeight: '900' },
});
