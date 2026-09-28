import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
import { BACKEND_URL } from '../constants/config';
import {
  DEFAULT_RUNNER_SETTINGS,
  normalizeRunnerSettings,
  toRunnerSettingsPayload,
  validateRunnerSettings,
  type RunnerAllocationMode,
  type RunnerSettingsState,
  type RunnerTrailingMode,
} from '../utils/runnerSettingsState';
import {
  TRADING_TEST_PRESETS,
  applyTradingTestPreset,
  diffTradingTestPreset,
  getTradingTestPreset,
  matchesTradingTestPreset,
  type TradingTestPresetChange,
  type TradingTestPresetId,
} from '../utils/tradingTestPresets';

const ACCENT = '#22c55e';

function matchingPresetId(settings: Record<string, unknown>): TradingTestPresetId | null {
  return TRADING_TEST_PRESETS.find((preset) => matchesTradingTestPreset(settings, preset.id))?.id || null;
}

function formatPresetValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'On' : 'Off';
  if (value === undefined) return 'Not set';
  if (Array.isArray(value)) return `${value.length} configured row${value.length === 1 ? '' : 's'}`;
  return String(value);
}

function Section({ icon, title, detail, children, disabled = false }: {
  icon: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  detail: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <View style={[styles.section, disabled && styles.disabled]}>
      <View style={styles.sectionHeader}>
        <View style={styles.sectionIcon}><Ionicons name={icon} size={18} color={ACCENT} /></View>
        <View style={styles.sectionCopy}>
          <Text style={styles.sectionTitle}>{title}</Text>
          <Text style={styles.sectionDetail}>{detail}</Text>
        </View>
      </View>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function ToggleRow({ label, detail, value, onChange, disabled = false }: {
  label: string;
  detail: string;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <View style={styles.toggleRow}>
      <View style={styles.toggleCopy}>
        <Text style={styles.controlLabel}>{label}</Text>
        <Text style={styles.controlDetail}>{detail}</Text>
      </View>
      <Switch value={value} onValueChange={onChange} disabled={disabled} trackColor={{ false: '#26324a', true: '#15803d' }} thumbColor={value ? '#dcfce7' : '#94a3b8'} />
    </View>
  );
}

function NumericField({ label, value, onChange, suffix, detail, disabled = false }: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
  detail?: string;
  disabled?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.controlLabel}>{label}</Text>
      <View style={[styles.inputWrap, disabled && styles.inputDisabled]}>
        <TextInput
          value={Number.isFinite(value) ? String(value) : ''}
          onChangeText={(text) => onChange(text.trim() === '' ? 0 : Number(text))}
          keyboardType="decimal-pad"
          editable={!disabled}
          style={styles.input}
          selectTextOnFocus
        />
        {suffix ? <Text style={styles.inputSuffix}>{suffix}</Text> : null}
      </View>
      {detail ? <Text style={styles.fieldDetail}>{detail}</Text> : null}
    </View>
  );
}

function Segmented<T extends string>({ value, options, onChange, disabled = false }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <View style={[styles.segment, disabled && styles.disabled]}>
      {options.map((option) => {
        const selected = value === option.value;
        return (
          <TouchableOpacity key={option.value} style={[styles.segmentButton, selected && styles.segmentButtonActive]} onPress={() => onChange(option.value)} disabled={disabled}>
            <Text style={[styles.segmentText, selected && styles.segmentTextActive]}>{option.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export default function RunnerSettingsScreen() {
  const [settings, setSettings] = useState<RunnerSettingsState>(DEFAULT_RUNNER_SETTINGS);
  const [serverSettings, setServerSettings] = useState<Record<string, unknown>>({});
  const [selectedPresetId, setSelectedPresetId] = useState<TradingTestPresetId | null>(null);
  const [activePresetId, setActivePresetId] = useState<TradingTestPresetId | null>(null);
  const [presetChanges, setPresetChanges] = useState<TradingTestPresetChange[]>([]);
  const [presetCustomized, setPresetCustomized] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const update = useCallback(<K extends keyof RunnerSettingsState>(key: K, value: RunnerSettingsState[K]) => {
    setSettings((current) => ({ ...current, [key]: value }));
    if (selectedPresetId) setPresetCustomized(true);
  }, [selectedPresetId]);

  const load = useCallback(async () => {
    try {
      const response = await api.get(`${BACKEND_URL}/api/settings`);
      const loadedSettings = (response.data || {}) as Record<string, unknown>;
      setServerSettings(loadedSettings);
      setSettings(normalizeRunnerSettings(loadedSettings));
      setActivePresetId(matchingPresetId(loadedSettings));
      setSelectedPresetId(null);
      setPresetChanges([]);
      setPresetCustomized(false);
      setLoaded(true);
    } catch (error: any) {
      Alert.alert('Unable to load runners', error?.response?.data?.detail || error?.message || 'Settings request failed.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const selectPreset = useCallback((id: TradingTestPresetId) => {
    const draft = applyTradingTestPreset(serverSettings, id);
    setSelectedPresetId(id);
    setPresetChanges(diffTradingTestPreset(serverSettings, id));
    setPresetCustomized(false);
    setSettings(normalizeRunnerSettings(draft));
  }, [serverSettings]);

  const errors = useMemo(() => validateRunnerSettings(settings), [settings]);
  const example = useMemo(() => {
    const original = 10;
    const percent = Math.floor(original * settings.allocationPercent / 100);
    const raw = settings.allocationMode === 'fixed'
      ? settings.fixedContracts
      : settings.allocationMode === 'percent'
        ? Math.max(percent, percent > 0 ? settings.minContracts : 0)
        : Math.max(percent, settings.fixedContracts, settings.minContracts);
    const runner = Math.min(original, settings.maxContracts > 0 ? Math.min(raw, settings.maxContracts) : raw);
    return { runner, core: original - runner };
  }, [settings.allocationMode, settings.allocationPercent, settings.fixedContracts, settings.minContracts, settings.maxContracts]);

  const save = useCallback(async () => {
    if (!loaded || errors.length) {
      Alert.alert('Check runner settings', errors[0] || 'Settings must finish loading before they can be saved.');
      return;
    }
    setSaving(true);
    try {
      const presetPayload = selectedPresetId ? getTradingTestPreset(selectedPresetId).payload : {};
      const payload = { ...presetPayload, ...toRunnerSettingsPayload(settings) };
      await api.put(`${BACKEND_URL}/api/settings`, payload);
      const savedSettings = { ...serverSettings, ...payload };
      setServerSettings(savedSettings);
      setActivePresetId(matchingPresetId(savedSettings));
      setSelectedPresetId(null);
      setPresetChanges([]);
      setPresetCustomized(false);
      const presetName = selectedPresetId ? getTradingTestPreset(selectedPresetId).name : null;
      Alert.alert(
        presetName ? 'Trading preset saved' : 'Runners saved',
        presetName
          ? `${presetName}${presetCustomized ? ' with manual changes' : ''} is active for new exit evaluations.`
          : 'Core and runner settings are active for new exit evaluations.',
      );
    } catch (error: any) {
      Alert.alert('Unable to save runners', error?.response?.data?.detail || error?.message || 'Settings update failed.');
    } finally {
      setSaving(false);
    }
  }, [errors, loaded, presetCustomized, selectedPresetId, serverSettings, settings]);

  const setTier = (index: number, key: 'mfe_percent' | 'trail_percent', value: number) => {
    update('trailingTiers', settings.trailingTiers.map((tier, tierIndex) => tierIndex === index ? { ...tier, [key]: value } : tier));
  };

  if (loading) {
    return <SafeAreaView style={styles.root}><View style={styles.loading}><ActivityIndicator color={ACCENT} /><Text style={styles.loadingText}>Loading runner policy</Text></View></SafeAreaView>;
  }

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={ACCENT} />}>
        <View style={styles.pageHeader}>
          <View style={styles.headerCopy}>
            <Text style={styles.eyebrow}>OPTIONS EXIT POLICY</Text>
            <Text style={styles.title}>Core / Runners</Text>
            <Text style={styles.subtitle}>Separate profit-taking contracts from contracts reserved for exceptional moves.</Text>
          </View>
          <View style={[styles.statusPill, settings.enabled && styles.statusPillOn]}>
            <View style={[styles.statusDot, settings.enabled && styles.statusDotOn]} />
            <Text style={[styles.statusText, settings.enabled && styles.statusTextOn]}>{settings.enabled ? 'Active' : 'Disabled'}</Text>
          </View>
        </View>

        <Section icon="flask-outline" title="Trading test presets" detail="Load a complete exit policy for review. Echo does not change until Save is pressed.">
          <View style={styles.activePresetBand}>
            <View style={styles.activePresetCopy}>
              <Text style={styles.groupLabel}>ACTIVE CONFIGURATION</Text>
              <Text style={styles.activePresetName}>{activePresetId ? getTradingTestPreset(activePresetId).name : 'Custom settings'}</Text>
            </View>
            <View style={[styles.activeTag, activePresetId && styles.activeTagOn]}>
              <Text style={[styles.activeTagText, activePresetId && styles.activeTagTextOn]}>{activePresetId ? 'MATCHED' : 'CUSTOM'}</Text>
            </View>
          </View>

          <View style={styles.presetList}>
            {TRADING_TEST_PRESETS.map((preset) => {
              const selected = selectedPresetId === preset.id;
              const active = activePresetId === preset.id && !selectedPresetId;
              return (
                <TouchableOpacity
                  key={preset.id}
                  style={[styles.presetRow, selected && styles.presetRowSelected]}
                  onPress={() => selectPreset(preset.id)}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                >
                  <View style={[styles.presetIndicator, (selected || active) && styles.presetIndicatorOn]}>
                    <Ionicons name={selected ? 'create-outline' : active ? 'checkmark' : 'ellipse-outline'} size={16} color={selected || active ? '#86efac' : '#64748b'} />
                  </View>
                  <View style={styles.presetCopy}>
                    <View style={styles.presetTitleRow}>
                      <Text style={styles.presetName}>{preset.name}</Text>
                      <Text style={[styles.riskTag, preset.risk === 'full-premium' && styles.riskTagExtreme]}>
                        {preset.risk === 'full-premium' ? 'FULL PREMIUM RISK' : preset.risk.toUpperCase()}
                      </Text>
                    </View>
                    <Text style={styles.presetSummary}>{preset.summary}</Text>
                    <Text style={styles.presetExitText}>{preset.automaticExits}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={17} color={selected ? '#86efac' : '#526078'} />
                </TouchableOpacity>
              );
            })}
          </View>

          {selectedPresetId ? (
            <View style={styles.draftPanel}>
              <View style={styles.draftHeader}>
                <View style={styles.draftIcon}><Ionicons name="document-text-outline" size={18} color="#fbbf24" /></View>
                <View style={styles.draftCopy}>
                  <Text style={styles.draftTitle}>Draft only</Text>
                  <Text style={styles.draftText}>
                    {getTradingTestPreset(selectedPresetId).name}{presetCustomized ? ' has manual runner changes.' : ' is loaded for review.'} Save Settings to activate it.
                  </Text>
                </View>
              </View>
              <View style={styles.reviewHeader}>
                <Text style={styles.groupLabel}>Review changes</Text>
                <Text style={styles.changeCount}>{presetChanges.length} field{presetChanges.length === 1 ? '' : 's'}</Text>
              </View>
              <View style={styles.reviewList}>
                {presetChanges.length ? presetChanges.map((change) => (
                  <View key={change.key} style={styles.reviewRow}>
                    <Text style={styles.reviewLabel}>{change.label}</Text>
                    <View style={styles.reviewValues}>
                      <Text style={styles.reviewBefore}>{formatPresetValue(change.before)}</Text>
                      <Ionicons name="arrow-forward" size={13} color="#64748b" />
                      <Text style={styles.reviewAfter}>{formatPresetValue(change.after)}</Text>
                    </View>
                  </View>
                )) : <Text style={styles.noChanges}>This preset already matches the saved configuration.</Text>}
              </View>
            </View>
          ) : null}
        </Section>

        <Section icon="git-branch-outline" title="Runner allocation" detail="Choose how many contracts are separated from the core position.">
          <ToggleRow label="Enable Core / Runners" detail="When off, Echo uses the existing exit policy without runner ownership." value={settings.enabled} onChange={(value) => update('enabled', value)} />
          <Text style={styles.groupLabel}>ALLOCATION METHOD</Text>
          <Segmented<RunnerAllocationMode> value={settings.allocationMode} onChange={(value) => update('allocationMode', value)} disabled={!settings.enabled} options={[{ value: 'percent', label: 'Percent' }, { value: 'fixed', label: 'Fixed' }, { value: 'greater_of', label: 'Greater of' }]} />
          <View style={styles.fieldGrid}>
            <NumericField label="Position share" value={settings.allocationPercent} onChange={(value) => update('allocationPercent', value)} suffix="%" disabled={!settings.enabled} />
            <NumericField label="Fixed contracts" value={settings.fixedContracts} onChange={(value) => update('fixedContracts', value)} disabled={!settings.enabled} />
            <NumericField label="Minimum" value={settings.minContracts} onChange={(value) => update('minContracts', value)} disabled={!settings.enabled} />
            <NumericField label="Maximum" value={settings.maxContracts} onChange={(value) => update('maxContracts', value)} detail="0 removes the cap" disabled={!settings.enabled} />
            <NumericField label="Activation MFE" value={settings.activationMfePercent} onChange={(value) => update('activationMfePercent', value)} suffix="%" detail="0 dedicates runners immediately" disabled={!settings.enabled} />
            <NumericField label="Minimum age" value={settings.minimumActivationSeconds} onChange={(value) => update('minimumActivationSeconds', value)} suffix="sec" disabled={!settings.enabled} />
          </View>
          <ToggleRow label="Allow one-contract runners" detail="Permits the only contract in a position to become a runner." value={settings.allowSingleContract} onChange={(value) => update('allowSingleContract', value)} disabled={!settings.enabled} />
          <View style={styles.exampleBand}>
            <Ionicons name="calculator-outline" size={18} color="#60a5fa" />
            <Text style={styles.exampleText}>Example with 10 contracts:</Text>
            <Text style={styles.exampleCore}>{example.core} core</Text>
            <Text style={styles.exampleRunner}>{example.runner} runner{example.runner === 1 ? '' : 's'}</Text>
          </View>
        </Section>

        <Section icon="shield-checkmark-outline" title="Ownership and protection" detail="Select which ordinary exits may consume runner contracts." disabled={!settings.enabled}>
          <ToggleRow label="Reserve candidates from profit exits" detail="Hold planned runners out of profit stages before dedication." value={settings.reserveCandidatesFromProfit} onChange={(value) => update('reserveCandidatesFromProfit', value)} disabled={!settings.enabled} />
          <ToggleRow label="Loss ladder may consume candidates" detail="Before activation, defensive ladder exits can use runner candidates." value={settings.lossLadderConsumesCandidates} onChange={(value) => update('lossLadderConsumesCandidates', value)} disabled={!settings.enabled} />
          <ToggleRow label="Protect from loss ladder" detail="After activation, ladder orders sell core contracts only." value={settings.protectLossLadder} onChange={(value) => update('protectLossLadder', value)} disabled={!settings.enabled} />
          <ToggleRow label="Protect from normal hard stop" detail="Dedicated runners use their catastrophic stop instead." value={settings.protectHardStop} onChange={(value) => update('protectHardStop', value)} disabled={!settings.enabled} />
          <ToggleRow label="Protect from break-even and profit floor" detail="Core can exit at the floor while runners remain." value={settings.protectBreakEven} onChange={(value) => update('protectBreakEven', value)} disabled={!settings.enabled} />
          <ToggleRow label="Protect from profit stages" detail="Take-profit stages cannot cross the runner target." value={settings.protectProfitStages} onChange={(value) => update('protectProfitStages', value)} disabled={!settings.enabled} />
          <ToggleRow label="Protect from ordinary trailing" detail="Only the runner-specific trail can exit dedicated runners." value={settings.protectOrdinaryTrailing} onChange={(value) => update('protectOrdinaryTrailing', value)} disabled={!settings.enabled} />
          <ToggleRow label="Protect from reversal warnings" detail="Warnings reduce the core; confirmed reversals follow the control below." value={settings.protectReversalWarning} onChange={(value) => update('protectReversalWarning', value)} disabled={!settings.enabled} />
          <ToggleRow label="Confirmed reversal exits runners" detail="A confirmed market reversal may close dedicated runners." value={settings.confirmedReversalExits} onChange={(value) => update('confirmedReversalExits', value)} disabled={!settings.enabled} />
        </Section>

        <Section icon="warning-outline" title="Catastrophic protection" detail="An independent last-resort loss limit for dedicated runners." disabled={!settings.enabled}>
          <View style={styles.fieldGrid}>
            <NumericField label="Catastrophic stop" value={settings.catastrophicStopPercent} onChange={(value) => update('catastrophicStopPercent', value)} suffix="%" detail={settings.catastrophicStopPercent === 0 ? 'Full premium at risk' : 'Loss from entry premium'} disabled={!settings.enabled} />
            <NumericField label="Confirmations" value={settings.catastrophicConfirmations} onChange={(value) => update('catastrophicConfirmations', value)} disabled={!settings.enabled} />
            <NumericField label="Confirmation interval" value={settings.catastrophicConfirmationIntervalSeconds} onChange={(value) => update('catastrophicConfirmationIntervalSeconds', value)} suffix="sec" disabled={!settings.enabled} />
          </View>
          {settings.catastrophicStopPercent === 0 ? <View style={styles.riskBand}><Ionicons name="alert-circle" size={18} color="#f59e0b" /><Text style={styles.riskText}>Full premium at risk. Price-based catastrophic exits are disabled; the runner trail and explicit overrides remain available.</Text></View> : null}
        </Section>

        <Section icon="trending-up-outline" title="Runner trailing" detail="Trail dedicated contracts independently after activation." disabled={!settings.enabled}>
          <ToggleRow label="Enable runner trail" detail="Echo watches executable option bids and submits its own SELL order." value={settings.trailingEnabled} onChange={(value) => update('trailingEnabled', value)} disabled={!settings.enabled} />
          <Text style={styles.groupLabel}>TRAIL MODE</Text>
          <Segmented<RunnerTrailingMode> value={settings.trailingMode} onChange={(value) => update('trailingMode', value)} disabled={!settings.enabled || !settings.trailingEnabled} options={[{ value: 'fixed', label: 'Fixed' }, { value: 'tiered', label: 'Tiered' }, { value: 'underlying_confirmed', label: 'Confirmed' }]} />
          <View style={styles.fieldGrid}>
            <NumericField label="Fixed trail" value={settings.fixedTrailingPercent} onChange={(value) => update('fixedTrailingPercent', value)} suffix="%" disabled={!settings.enabled || !settings.trailingEnabled || settings.trailingMode !== 'fixed'} />
            <NumericField label="Minimum distance" value={settings.minTrailingCents} onChange={(value) => update('minTrailingCents', value)} suffix="cents" disabled={!settings.enabled || !settings.trailingEnabled} />
            <NumericField label="Spread multiplier" value={settings.spreadMultiplier} onChange={(value) => update('spreadMultiplier', value)} suffix="x" disabled={!settings.enabled || !settings.trailingEnabled} />
            <NumericField label="Confirmations" value={settings.trailingConfirmations} onChange={(value) => update('trailingConfirmations', value)} disabled={!settings.enabled || !settings.trailingEnabled} />
            <NumericField label="Confirmation interval" value={settings.trailingConfirmationIntervalSeconds} onChange={(value) => update('trailingConfirmationIntervalSeconds', value)} suffix="sec" disabled={!settings.enabled || !settings.trailingEnabled} />
          </View>
          <View style={styles.tierHeader}><Text style={styles.groupLabel}>TIERED WIDTHS</Text><TouchableOpacity style={styles.iconButton} onPress={() => update('trailingTiers', [...settings.trailingTiers, { mfe_percent: (settings.trailingTiers.at(-1)?.mfe_percent || 0) + 100, trail_percent: 20 }])} disabled={!settings.enabled || !settings.trailingEnabled || settings.trailingTiers.length >= 10}><Ionicons name="add" size={18} color={ACCENT} /></TouchableOpacity></View>
          {settings.trailingTiers.map((tier, index) => (
            <View key={index} style={styles.tierRow}>
              <Text style={styles.tierIndex}>{index + 1}</Text>
              <NumericField label="MFE" value={tier.mfe_percent} onChange={(value) => setTier(index, 'mfe_percent', value)} suffix="%" disabled={!settings.enabled || !settings.trailingEnabled || settings.trailingMode === 'fixed'} />
              <NumericField label="Trail" value={tier.trail_percent} onChange={(value) => setTier(index, 'trail_percent', value)} suffix="%" disabled={!settings.enabled || !settings.trailingEnabled || settings.trailingMode === 'fixed'} />
              <TouchableOpacity style={styles.removeButton} onPress={() => update('trailingTiers', settings.trailingTiers.filter((_, tierIndex) => tierIndex !== index))} disabled={settings.trailingTiers.length <= 1}><Ionicons name="trash-outline" size={17} color={settings.trailingTiers.length <= 1 ? '#475569' : '#fb7185'} /></TouchableOpacity>
            </View>
          ))}
          <ToggleRow label="Require a fresh high" detail="Runner activation must coincide with a new executable premium high." value={settings.requireFreshHigh} onChange={(value) => update('requireFreshHigh', value)} disabled={!settings.enabled || !settings.trailingEnabled} />
          <ToggleRow label="Allow trail floor to move down" detail="Usually off so a recorded runner floor can only tighten." value={settings.allowFloorToMoveDown} onChange={(value) => update('allowFloorToMoveDown', value)} disabled={!settings.enabled || !settings.trailingEnabled} />
        </Section>

        <Section icon="chatbubble-ellipses-outline" title="Analyst exits and expiration" detail="Control when Discord exits can override runner ownership." disabled={!settings.enabled}>
          <ToggleRow label="Protect contextual trims" detail="Broad trims and inferred exits leave dedicated runners intact." value={settings.protectContextualTrims} onChange={(value) => update('protectContextualTrims', value)} disabled={!settings.enabled} />
          <View style={styles.fieldGrid}>
            <NumericField label="Explicit override threshold" value={settings.analystOverridePercent} onChange={(value) => update('analystOverridePercent', value)} suffix="%" detail="Requires an exact contract alert" disabled={!settings.enabled} />
          </View>
          <ToggleRow label="Allow exact-contract overrides" detail="An explicit exit at or above the threshold may sell runners." value={settings.explicitFullExitOverrides} onChange={(value) => update('explicitFullExitOverrides', value)} disabled={!settings.enabled} />
          <ToggleRow label="Allow contextual full-exit overrides" detail="Broad or inferred 100% exits may sell runners." value={settings.contextualFullExitOverrides} onChange={(value) => update('contextualFullExitOverrides', value)} disabled={!settings.enabled} />
          <ToggleRow label="Runner 0DTE liquidation" detail="Close remaining runners at the configured market time." value={settings.zeroDteLiquidationEnabled} onChange={(value) => update('zeroDteLiquidationEnabled', value)} disabled={!settings.enabled} />
          <View style={styles.field}>
            <Text style={styles.controlLabel}>Runner 0DTE time</Text>
            <View style={styles.inputWrap}><TextInput value={settings.zeroDteLiquidationTime} onChangeText={(value) => update('zeroDteLiquidationTime', value)} editable={settings.enabled && settings.zeroDteLiquidationEnabled} style={styles.input} placeholder="15:40" placeholderTextColor="#64748b" /></View>
          </View>
        </Section>

        {errors.length ? <View style={styles.errorBand}>{errors.map((error) => <Text key={error} style={styles.errorText}>• {error}</Text>)}</View> : null}
        <TouchableOpacity style={[styles.saveButton, (saving || !loaded || errors.length > 0) && styles.saveButtonDisabled]} onPress={save} disabled={saving || !loaded || errors.length > 0}>
          {saving ? <ActivityIndicator color="#04110a" /> : <Ionicons name="save-outline" size={18} color="#04110a" />}
          <Text style={styles.saveText}>{saving ? 'Saving' : selectedPresetId ? 'Save settings' : 'Save runner policy'}</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#050416' },
  content: { width: '100%', maxWidth: 1120, alignSelf: 'center', padding: 18, paddingBottom: 80, gap: 14 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText: { color: '#94a3b8', fontSize: 13 },
  pageHeader: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 2 },
  headerCopy: { flex: 1, minWidth: 220 },
  eyebrow: { color: ACCENT, fontSize: 11, fontWeight: '800', letterSpacing: 0 },
  title: { color: '#f8fafc', fontSize: 28, lineHeight: 34, fontWeight: '800', letterSpacing: 0 },
  subtitle: { color: '#94a3b8', fontSize: 13, lineHeight: 19, maxWidth: 620 },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 7, borderWidth: 1, borderColor: '#334155', backgroundColor: '#111827', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 7 },
  statusPillOn: { borderColor: '#166534', backgroundColor: '#052e16' },
  statusDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#64748b' },
  statusDotOn: { backgroundColor: ACCENT },
  statusText: { color: '#94a3b8', fontSize: 11, fontWeight: '800' },
  statusTextOn: { color: '#86efac' },
  section: { borderWidth: 1, borderColor: '#26324a', borderRadius: 6, backgroundColor: 'rgba(8, 13, 28, 0.88)', overflow: 'hidden' },
  disabled: { opacity: 0.58 },
  sectionHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 11, padding: 14, borderBottomWidth: 1, borderBottomColor: '#1d2940' },
  sectionIcon: { width: 34, height: 34, borderRadius: 6, borderWidth: 1, borderColor: '#166534', backgroundColor: '#052e16', alignItems: 'center', justifyContent: 'center' },
  sectionCopy: { flex: 1 },
  sectionTitle: { color: '#e2e8f0', fontSize: 16, fontWeight: '800', letterSpacing: 0 },
  sectionDetail: { color: '#7f8ca5', fontSize: 12, lineHeight: 17, marginTop: 2 },
  sectionBody: { padding: 14, gap: 12 },
  toggleRow: { minHeight: 56, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 16, borderBottomWidth: 1, borderBottomColor: '#162035', paddingVertical: 7 },
  toggleCopy: { flex: 1 },
  controlLabel: { color: '#cbd5e1', fontSize: 12, fontWeight: '700', letterSpacing: 0 },
  controlDetail: { color: '#72809a', fontSize: 11, lineHeight: 16, marginTop: 2 },
  groupLabel: { color: '#72809a', fontSize: 10, fontWeight: '800', marginTop: 3, letterSpacing: 0 },
  segment: { width: '100%', maxWidth: 310, flexDirection: 'row', alignSelf: 'flex-start', borderWidth: 1, borderColor: '#26324a', borderRadius: 6, overflow: 'hidden' },
  segmentButton: { flex: 1, minWidth: 0, minHeight: 36, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 7, backgroundColor: '#0a1020' },
  segmentButtonActive: { backgroundColor: '#14532d' },
  segmentText: { color: '#8090aa', fontSize: 11, fontWeight: '700' },
  segmentTextActive: { color: '#dcfce7' },
  fieldGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  field: { minWidth: 150, flexGrow: 1, flexBasis: 150, gap: 6 },
  inputWrap: { minHeight: 38, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: '#334155', borderRadius: 6, backgroundColor: '#070c18', paddingHorizontal: 10 },
  inputDisabled: { backgroundColor: '#0d1321', borderColor: '#1e293b' },
  input: { flex: 1, minWidth: 50, color: '#f8fafc', fontSize: 13, fontWeight: '700', paddingVertical: 8 },
  inputSuffix: { color: '#64748b', fontSize: 11, fontWeight: '700' },
  fieldDetail: { color: '#66758f', fontSize: 10, lineHeight: 14 },
  exampleBand: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 9, borderWidth: 1, borderColor: '#1e3a5f', borderRadius: 6, backgroundColor: '#071426', padding: 11 },
  exampleText: { color: '#94a3b8', fontSize: 12 },
  exampleCore: { color: '#93c5fd', fontSize: 12, fontWeight: '800' },
  exampleRunner: { color: '#86efac', fontSize: 12, fontWeight: '800' },
  activePresetBand: { minHeight: 54, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: 1, borderBottomColor: '#1d2940', paddingBottom: 12 },
  activePresetCopy: { flex: 1, gap: 3 },
  activePresetName: { color: '#e2e8f0', fontSize: 14, fontWeight: '800' },
  activeTag: { borderWidth: 1, borderColor: '#334155', borderRadius: 5, backgroundColor: '#111827', paddingHorizontal: 8, paddingVertical: 5 },
  activeTagOn: { borderColor: '#166534', backgroundColor: '#052e16' },
  activeTagText: { color: '#94a3b8', fontSize: 9, fontWeight: '900' },
  activeTagTextOn: { color: '#86efac' },
  presetList: { borderWidth: 1, borderColor: '#26324a', borderRadius: 6, overflow: 'hidden' },
  presetRow: { minHeight: 88, flexDirection: 'row', alignItems: 'center', gap: 11, padding: 12, borderBottomWidth: 1, borderBottomColor: '#1d2940', backgroundColor: '#080e1c' },
  presetRowSelected: { backgroundColor: '#0b2118', borderLeftWidth: 3, borderLeftColor: ACCENT, paddingLeft: 9 },
  presetIndicator: { width: 30, height: 30, flexShrink: 0, borderWidth: 1, borderColor: '#334155', borderRadius: 5, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0a1020' },
  presetIndicatorOn: { borderColor: '#166534', backgroundColor: '#052e16' },
  presetCopy: { flex: 1, minWidth: 0, gap: 3 },
  presetTitleRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7 },
  presetName: { color: '#e2e8f0', fontSize: 13, fontWeight: '800' },
  riskTag: { color: '#fcd34d', fontSize: 8, fontWeight: '900', borderWidth: 1, borderColor: '#713f12', borderRadius: 4, backgroundColor: '#241405', paddingHorizontal: 6, paddingVertical: 3 },
  riskTagExtreme: { color: '#fda4af', borderColor: '#7f1d1d', backgroundColor: '#25090d' },
  presetSummary: { color: '#94a3b8', fontSize: 11, lineHeight: 16 },
  presetExitText: { color: '#66758f', fontSize: 10, lineHeight: 15 },
  draftPanel: { borderWidth: 1, borderColor: '#713f12', borderRadius: 6, backgroundColor: '#130e07', overflow: 'hidden' },
  draftHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, padding: 12, borderBottomWidth: 1, borderBottomColor: '#51300f' },
  draftIcon: { width: 32, height: 32, borderRadius: 5, borderWidth: 1, borderColor: '#713f12', alignItems: 'center', justifyContent: 'center' },
  draftCopy: { flex: 1, minWidth: 0 },
  draftTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '900' },
  draftText: { color: '#d6b873', fontSize: 11, lineHeight: 16, marginTop: 2 },
  reviewHeader: { minHeight: 38, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12 },
  changeCount: { color: '#94a3b8', fontSize: 10, fontWeight: '800' },
  reviewList: { borderTopWidth: 1, borderTopColor: '#33240f' },
  reviewRow: { minHeight: 42, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8, paddingHorizontal: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#2c200f' },
  reviewLabel: { flexGrow: 1, flexBasis: 170, color: '#cbd5e1', fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  reviewValues: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 7, minWidth: 150, maxWidth: '100%' },
  reviewBefore: { color: '#94a3b8', fontSize: 10, textDecorationLine: 'line-through', maxWidth: 120 },
  reviewAfter: { color: '#86efac', fontSize: 10, fontWeight: '800', maxWidth: 160 },
  noChanges: { color: '#94a3b8', fontSize: 11, padding: 12 },
  riskBand: { flexDirection: 'row', alignItems: 'flex-start', gap: 9, borderWidth: 1, borderColor: '#78350f', borderRadius: 6, backgroundColor: '#241405', padding: 11 },
  riskText: { flex: 1, color: '#fcd34d', fontSize: 11, lineHeight: 17 },
  tierHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconButton: { width: 32, height: 32, borderRadius: 6, borderWidth: 1, borderColor: '#166534', alignItems: 'center', justifyContent: 'center' },
  tierRow: { flexDirection: 'row', alignItems: 'center', gap: 9, borderBottomWidth: 1, borderBottomColor: '#162035', paddingBottom: 10 },
  tierIndex: { width: 24, height: 24, borderRadius: 4, textAlign: 'center', textAlignVertical: 'center', color: '#86efac', backgroundColor: '#052e16', fontSize: 11, fontWeight: '800' },
  removeButton: { width: 34, height: 36, alignItems: 'center', justifyContent: 'center' },
  errorBand: { borderWidth: 1, borderColor: '#7f1d1d', borderRadius: 6, backgroundColor: '#25090d', padding: 12, gap: 4 },
  errorText: { color: '#fda4af', fontSize: 11, lineHeight: 16 },
  saveButton: { minHeight: 46, borderRadius: 6, backgroundColor: ACCENT, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9 },
  saveButtonDisabled: { opacity: 0.42 },
  saveText: { color: '#04110a', fontSize: 13, fontWeight: '900' },
});
