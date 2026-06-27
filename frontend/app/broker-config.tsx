import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useNavigation } from 'expo-router';
import { api } from '../utils/api';

import { BACKEND_URL } from '../constants/config';
import { BROKER_COLORS } from '../constants/brokers';
import {
  BrokerConfigDigest,
  getBrokerConnectionResult,
  summarizeBrokerConfig,
} from '../utils/brokerConfigDigest';

interface BrokerInfo {
  id: string;
  name: string;
  description: string;
  supports_options: boolean;
  requires_gateway: boolean;
  config_fields: ConfigField[];
}

interface ConfigField {
  key: string;
  label: string;
  type: string;
  placeholder?: string;
  options?: { value: string; label: string }[];
}

type ConfiguredFieldsMap = Record<string, boolean | string | number | null | undefined>;

interface BrokerConfig {
  [key: string]: string | ConfiguredFieldsMap | null | undefined;
  configured_fields?: ConfiguredFieldsMap | null;
}

const MASKED_SECRET = '********';
const SENSITIVE_CONFIG_KEYS = new Set([
  'api_key',
  'api_secret',
  'secret_key',
  'access_token',
  'refresh_token',
  'password',
  'trade_token',
  'client_secret',
  'ts_client_secret',
  'tos_refresh_token',
  'ws_password',
]);

function isSensitiveConfigField(field: ConfigField): boolean {
  return field.type === 'password' || SENSITIVE_CONFIG_KEYS.has(field.key);
}

function hasConfiguredFieldFlag(config: BrokerConfig | undefined, key: string): boolean {
  const value = config?.configured_fields?.[key];
  return value === true || value === 'true' || value === 1 || value === '1';
}

function brokerFieldValue(config: BrokerConfig | undefined, field: ConfigField): string {
  const value = config?.[field.key];
  if (typeof value === 'string' && value.length > 0) return value;
  if (isSensitiveConfigField(field) && hasConfiguredFieldFlag(config, field.key)) return MASKED_SECRET;
  return '';
}

function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.digestStat}>
      <Text style={[styles.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.digestStatLabel}>{label}</Text>
    </View>
  );
}

function BrokerBriefing({ digest }: { digest: BrokerConfigDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#68779b';
  const warnings = digest.warningItems.slice(0, 3);

  return (
    <View style={[styles.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={styles.digestTop}>
        <View style={styles.digestTitleBlock}>
          <Text style={styles.digestEyebrow}>BROKER READINESS</Text>
          <Text style={styles.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={styles.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[styles.readinessBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[styles.readinessValue, { color: toneColor }]}>{digest.readinessPercent}%</Text>
          <Text style={styles.readinessLabel}>ready</Text>
        </View>
      </View>

      <View style={styles.digestStats}>
        <DigestStat label="Broker" value={digest.selectedBrokerName} />
        <DigestStat label="Fields" value={`${digest.configuredFields}/${digest.totalFields}`} color={toneColor} />
        <DigestStat label="Configured" value={String(digest.configuredBrokerCount)} />
        <DigestStat label="Unsaved" value={String(digest.unsavedBrokerCount)} color={digest.unsavedBrokerCount ? '#f59e0b' : undefined} />
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
            <Text style={styles.clearText}>Selected broker keys are saved and ready for execution routing.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

export default function BrokerConfigScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const [brokers, setBrokers] = useState<BrokerInfo[]>([]);
  const [activeBroker, setActiveBroker] = useState<string>('ibkr');
  const [brokerConfigs, setBrokerConfigs] = useState<{ [key: string]: BrokerConfig }>({});
  const [savedConfigs, setSavedConfigs] = useState<{ [key: string]: BrokerConfig }>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checkingConnection, setCheckingConnection] = useState<string | null>(null);
  const [selectedBroker, setSelectedBroker] = useState<string | null>(null);

  // M15: track whether any config field has been edited since last save
  const hasUnsavedChanges = JSON.stringify(brokerConfigs) !== JSON.stringify(savedConfigs);

  const fetchData = useCallback(async () => {
    try {
      const [brokersRes, settingsRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/brokers`),
        api.get(`${BACKEND_URL}/api/settings`),
      ]);
      setBrokers(brokersRes.data);
      setActiveBroker(settingsRes.data.active_broker);
      const configs = settingsRes.data.broker_configs || {};
      setBrokerConfigs(configs);
      setSavedConfigs(configs);  // snapshot for dirty-check
      setSelectedBroker(settingsRes.data.active_broker);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // M15: warn user if they navigate away with unsaved changes
  useEffect(() => {
    const unsubscribe = navigation.addListener('beforeRemove', (e: any) => {
      if (!hasUnsavedChanges) return;
      e.preventDefault();
      Alert.alert(
        'Unsaved Changes',
        'You have unsaved API key changes. Leave without saving?',
        [
          { text: 'Stay', style: 'cancel' },
          {
            text: 'Leave',
            style: 'destructive',
            onPress: () => navigation.dispatch(e.data.action),
          },
        ]
      );
    });
    return unsubscribe;
  }, [navigation, hasUnsavedChanges]);

  const updateBrokerConfig = (brokerId: string, key: string, value: string) => {
    setBrokerConfigs(prev => ({
      ...prev,
      [brokerId]: {
        ...(prev[brokerId] || {}),
        [key]: value,
      },
    }));
  };

  const saveBrokerConfig = async (brokerId: string) => {
    setSaving(true);
    try {
      await api.put(`${BACKEND_URL}/api/settings`, {
        broker_configs: {
          [brokerId]: brokerConfigs[brokerId] || {},
        },
      });
      // M15: update savedConfigs snapshot so dirty flag clears
      setSavedConfigs(prev => ({
        ...prev,
        [brokerId]: brokerConfigs[brokerId] || {},
      }));
      Alert.alert('Success', `${brokers.find(b => b.id === brokerId)?.name || brokerId} configuration saved!`);
    } catch (error) {
      console.error('Error saving config:', error);
      Alert.alert('Error', 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const switchActiveBroker = async (brokerId: string) => {
    try {
      await api.post(`${BACKEND_URL}/api/broker/switch/${brokerId}`);
      setActiveBroker(brokerId);
      Alert.alert('Success', `Switched to ${brokers.find(b => b.id === brokerId)?.name || brokerId}`);
    } catch {
      Alert.alert('Error', 'Failed to switch broker');
    }
  };

  const checkConnection = async (brokerId: string) => {
    setCheckingConnection(brokerId);
    try {
      const response = await api.post(`${BACKEND_URL}/api/broker/check/${brokerId}`);
      const result = getBrokerConnectionResult(response.data);
      Alert.alert(result.title, result.message);
    } catch (error) {
      console.error('Error checking connection:', error);
      Alert.alert('Error', 'Failed to check connection');
    } finally {
      setCheckingConnection(null);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#3b82f6" />
        </View>
      </SafeAreaView>
    );
  }

  const selectedBrokerInfo = brokers.find(b => b.id === selectedBroker);
  const digest = summarizeBrokerConfig(brokers, activeBroker, selectedBroker, brokerConfigs, savedConfigs);

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={24} color="#fff" />
          </TouchableOpacity>
          <Text style={styles.title}>
            Broker APIs{hasUnsavedChanges ? ' •' : ''}
          </Text>
          <View style={styles.placeholder} />
        </View>
        
        <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
          {/* Broker Selector Tabs */}
          <ScrollView 
            horizontal 
            showsHorizontalScrollIndicator={false}
            style={styles.tabsContainer}
            contentContainerStyle={styles.tabsContent}
          >
            {brokers.map((broker) => (
              <TouchableOpacity
                key={broker.id}
                style={[
                  styles.brokerTab,
                  selectedBroker === broker.id && styles.brokerTabActive,
                  { borderColor: BROKER_COLORS[broker.id] || '#6b7280' }
                ]}
                onPress={() => setSelectedBroker(broker.id)}
              >
                <View style={[styles.tabDot, { backgroundColor: BROKER_COLORS[broker.id] || '#6b7280' }]} />
                <Text style={[
                  styles.tabText,
                  selectedBroker === broker.id && styles.tabTextActive
                ]}>
                  {broker.name}
                </Text>
                {activeBroker === broker.id && (
                  <View style={styles.activeIndicator}>
                    <Ionicons name="checkmark-circle" size={14} color="#22c55e" />
                  </View>
                )}
              </TouchableOpacity>
            ))}
          </ScrollView>

          <BrokerBriefing digest={digest} />

          {/* Selected Broker Configuration */}
          {selectedBrokerInfo && (
            <View style={styles.configSection}>
              <View style={styles.brokerHeader}>
                <View style={[styles.brokerIcon, { backgroundColor: BROKER_COLORS[selectedBrokerInfo.id] }]}>
                  <Ionicons name="key-outline" size={24} color="#fff" />
                </View>
                <View style={styles.brokerHeaderInfo}>
                  <Text style={styles.brokerName}>{selectedBrokerInfo.name}</Text>
                  <Text style={styles.brokerDesc}>{selectedBrokerInfo.description}</Text>
                </View>
              </View>

              {/* Status indicators */}
              <View style={styles.statusRow}>
                <View style={styles.statusBadge}>
                  <Ionicons 
                    name={selectedBrokerInfo.supports_options ? "checkmark-circle" : "close-circle"} 
                    size={16} 
                    color={selectedBrokerInfo.supports_options ? '#22c55e' : '#ef4444'} 
                  />
                  <Text style={styles.statusText}>Options Trading</Text>
                </View>
                {selectedBrokerInfo.requires_gateway && (
                  <View style={styles.statusBadge}>
                    <Ionicons name="desktop-outline" size={16} color="#f59e0b" />
                    <Text style={styles.statusText}>Requires Gateway</Text>
                  </View>
                )}
              </View>

              {/* Configuration Fields */}
              <View style={styles.fieldsContainer}>
                <Text style={styles.fieldsTitle}>API Configuration</Text>
                
                {selectedBrokerInfo.config_fields.map((field) => (
                  <View key={field.key} style={styles.inputGroup}>
                    <Text style={styles.inputLabel}>{field.label}</Text>
                    {field.type === 'select' && field.options ? (
                      <View style={styles.selectContainer}>
                        {field.options.map((option) => (
                          <TouchableOpacity
                            key={option.value}
                            style={[
                              styles.selectOption,
                              brokerConfigs[selectedBrokerInfo.id]?.[field.key] === option.value && styles.selectOptionActive
                            ]}
                            onPress={() => updateBrokerConfig(selectedBrokerInfo.id, field.key, option.value)}
                          >
                            <View style={[
                              styles.radioButton,
                              brokerConfigs[selectedBrokerInfo.id]?.[field.key] === option.value && styles.radioButtonActive
                            ]} />
                            <Text style={[
                              styles.selectOptionText,
                              brokerConfigs[selectedBrokerInfo.id]?.[field.key] === option.value && styles.selectOptionTextActive
                            ]}>
                              {option.label}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    ) : (
                      <TextInput
                        style={styles.textInput}
                        value={brokerFieldValue(brokerConfigs[selectedBrokerInfo.id], field)}
                        onChangeText={(text) => updateBrokerConfig(selectedBrokerInfo.id, field.key, text)}
                        placeholder={field.placeholder}
                        placeholderTextColor="#68779b"
                        secureTextEntry={isSensitiveConfigField(field)}
                        autoCapitalize="none"
                      />
                    )}
                  </View>
                ))}
              </View>

              {/* Action Buttons */}
              <View style={styles.actionsContainer}>
                <TouchableOpacity
                  style={[styles.saveBtn, { backgroundColor: BROKER_COLORS[selectedBrokerInfo.id] }]}
                  onPress={() => saveBrokerConfig(selectedBrokerInfo.id)}
                  disabled={saving}
                >
                  {saving ? (
                    <ActivityIndicator size="small" color="#fff" />
                  ) : (
                    <>
                      <Ionicons name="save-outline" size={20} color="#fff" />
                      <Text style={styles.saveBtnText}>Save Configuration</Text>
                    </>
                  )}
                </TouchableOpacity>

                <View style={styles.secondaryActions}>
                  <TouchableOpacity
                    style={styles.secondaryBtn}
                    onPress={() => checkConnection(selectedBrokerInfo.id)}
                    disabled={checkingConnection === selectedBrokerInfo.id}
                  >
                    {checkingConnection === selectedBrokerInfo.id ? (
                      <ActivityIndicator size="small" color="#3b82f6" />
                    ) : (
                      <>
                        <Ionicons name="wifi-outline" size={18} color="#3b82f6" />
                        <Text style={styles.secondaryBtnText}>Test Connection</Text>
                      </>
                    )}
                  </TouchableOpacity>

                  {activeBroker !== selectedBrokerInfo.id && (
                    <TouchableOpacity
                      style={[styles.secondaryBtn, styles.activateBtn]}
                      onPress={() => switchActiveBroker(selectedBrokerInfo.id)}
                    >
                      <Ionicons name="swap-horizontal-outline" size={18} color="#22c55e" />
                      <Text style={[styles.secondaryBtnText, { color: '#22c55e' }]}>Set as Active</Text>
                    </TouchableOpacity>
                  )}
                </View>

                {activeBroker === selectedBrokerInfo.id && (
                  <View style={styles.activeBadge}>
                    <Ionicons name="checkmark-circle" size={18} color="#22c55e" />
                    <Text style={styles.activeBadgeText}>Currently Active Broker</Text>
                  </View>
                )}
              </View>
            </View>
          )}

          {/* Help Section */}
          <View style={styles.helpSection}>
            <Ionicons name="help-circle-outline" size={24} color="#68779b" />
            <View style={styles.helpContent}>
              <Text style={styles.helpTitle}>Need Help?</Text>
              <Text style={styles.helpText}>
                Each broker has different API requirements. Make sure to:
                {"\n"}• Create API keys from your broker's developer portal
                {"\n"}• Enable options trading permissions if needed
                {"\n"}• For IBKR, run the Client Portal Gateway locally
              </Text>
            </View>
          </View>

          <View style={styles.bottomPadding} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#050416',
  },
  keyboardView: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(16, 9, 28, 0.88)',
  },
  backButton: {
    padding: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
  },
  placeholder: {
    width: 40,
  },
  scrollView: {
    flex: 1,
  },
  digestCard: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginHorizontal: 16,
    marginTop: 12,
  },
  digestTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  digestTitleBlock: {
    flex: 1,
  },
  digestEyebrow: {
    color: '#68779b',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.4,
    marginBottom: 5,
  },
  digestTitle: {
    color: '#edf3ff',
    fontSize: 18,
    fontWeight: '900',
  },
  digestDetail: {
    color: '#aec0e5',
    fontSize: 12,
    lineHeight: 17,
    marginTop: 3,
  },
  readinessBadge: {
    minWidth: 78,
    height: 48,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  readinessValue: {
    fontSize: 18,
    fontWeight: '900',
  },
  readinessLabel: {
    color: '#68779b',
    fontSize: 10,
    fontWeight: '800',
    marginTop: 1,
  },
  digestStats: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(41, 33, 58, 0.82)',
  },
  digestStat: {
    flex: 1,
    alignItems: 'center',
  },
  digestStatValue: {
    color: '#edf3ff',
    fontSize: 12,
    fontWeight: '900',
  },
  digestStatLabel: {
    color: '#68779b',
    fontSize: 9,
    fontWeight: '800',
    marginTop: 3,
  },
  warningList: {
    marginTop: 12,
    gap: 8,
  },
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
  warningCopy: {
    flex: 1,
  },
  warningTitle: {
    color: '#fbbf24',
    fontSize: 12,
    fontWeight: '800',
  },
  warningDetail: {
    color: '#68779b',
    fontSize: 11,
    lineHeight: 15,
    marginTop: 2,
  },
  clearText: {
    color: '#aec0e5',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
  },
  tabsContainer: {
    marginTop: 16,
  },
  tabsContent: {
    paddingHorizontal: 16,
    gap: 8,
  },
  brokerTab: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 10,
    marginRight: 8,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  brokerTabActive: {
    backgroundColor: '#68779b',
  },
  tabDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  tabText: {
    fontSize: 14,
    color: '#aec0e5',
    fontWeight: '500',
  },
  tabTextActive: {
    color: '#fff',
    fontWeight: '600',
  },
  activeIndicator: {
    marginLeft: 6,
  },
  configSection: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
  },
  brokerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  brokerIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  brokerHeaderInfo: {
    flex: 1,
  },
  brokerName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
  },
  brokerDesc: {
    fontSize: 13,
    color: '#aec0e5',
    marginTop: 2,
  },
  statusRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 20,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#050416',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  statusText: {
    fontSize: 12,
    color: '#aec0e5',
  },
  fieldsContainer: {
    borderTopWidth: 1,
    borderTopColor: '#68779b',
    paddingTop: 16,
  },
  fieldsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#68779b',
    marginBottom: 16,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#edf3ff',
    marginBottom: 8,
  },
  textInput: {
    backgroundColor: '#050416',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    color: '#fff',
    borderWidth: 1,
    borderColor: '#68779b',
  },
  selectContainer: {
    gap: 8,
  },
  selectOption: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#050416',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#68779b',
  },
  selectOptionActive: {
    borderColor: '#3b82f6',
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
  },
  radioButton: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: '#68779b',
    marginRight: 10,
  },
  radioButtonActive: {
    borderColor: '#3b82f6',
    backgroundColor: '#3b82f6',
  },
  selectOptionText: {
    fontSize: 14,
    color: '#aec0e5',
  },
  selectOptionTextActive: {
    color: '#fff',
  },
  actionsContainer: {
    marginTop: 20,
  },
  saveBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
  },
  saveBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  secondaryActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  secondaryBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#050416',
    paddingVertical: 12,
    borderRadius: 8,
    gap: 6,
    borderWidth: 1,
    borderColor: '#68779b',
  },
  activateBtn: {
    borderColor: '#22c55e',
  },
  secondaryBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3b82f6',
  },
  activeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(34, 197, 94, 0.1)',
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
    marginTop: 12,
  },
  activeBadgeText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#22c55e',
  },
  helpSection: {
    flexDirection: 'row',
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    marginHorizontal: 16,
    marginTop: 16,
    padding: 16,
    borderRadius: 12,
  },
  helpContent: {
    flex: 1,
    marginLeft: 12,
  },
  helpTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 8,
  },
  helpText: {
    fontSize: 13,
    color: '#aec0e5',
    lineHeight: 20,
  },
  bottomPadding: {
    height: 40,
  },
});
