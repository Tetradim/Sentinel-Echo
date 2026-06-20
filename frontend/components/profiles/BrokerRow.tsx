import React from 'react';
import { View, Text, StyleSheet, Switch, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BrokerSettingsPanel } from './BrokerSettings';
import type { BrokerSettingsData, Broker } from '../../types/profiles';

interface BrokerRowProps {
  broker: Broker;
  settings: BrokerSettingsData | undefined;
  profileId: string;
  isExpanded: boolean;
  onExpandToggle: () => void;
  onToggle: (profileId: string, brokerId: string, settingName: string) => void;
  onUpdate: (profileId: string, brokerId: string, settingName: string, value: number) => void;
}

const getBrokerSummary = (settings: BrokerSettingsData | undefined): string | null => {
  if (!settings || !settings.enabled) return null;
  const features = [];
  if (settings.alerts_only) features.push('Alerts Only');
  else if (settings.auto_trading_enabled) features.push('Auto');
  if (settings.bracket_order_enabled) features.push('Bracket');
  if (settings.trailing_stop_enabled) features.push('Trail');
  if (settings.take_profit_enabled) features.push('TP');
  if (settings.stop_loss_enabled) features.push('SL');
  return features.length > 0 ? features.join(' • ') : 'Enabled';
};

export const BrokerRow: React.FC<BrokerRowProps> = ({
  broker,
  settings,
  profileId,
  isExpanded,
  onExpandToggle,
  onToggle,
  onUpdate,
}) => {
  const summary = getBrokerSummary(settings);

  return (
    <View style={styles.brokerCard} testID={`broker-row-${broker.id}`}>
      <View style={styles.brokerHeader}>
        {/* M22 fix: Switch sits outside the expand TouchableOpacity so Android
            doesn't fire both the Switch onValueChange and the row onPress */}
        <Switch
          value={settings?.enabled || false}
          onValueChange={() => onToggle(profileId, broker.id, 'enabled')}
          trackColor={{ false: '#374151', true: '#22c55e' }}
          thumbColor="#fff"
        />
        <TouchableOpacity
          style={styles.brokerLabelArea}
          onPress={onExpandToggle}
          testID={`broker-header-${broker.id}`}
        >
          <View>
            <Text style={[styles.brokerName, !settings?.enabled && styles.disabledText]}>
              {broker.name}
            </Text>
            {summary && <Text style={styles.brokerSummary}>{summary}</Text>}
          </View>
          {settings?.enabled && (
            <Ionicons
              name={isExpanded ? 'chevron-up' : 'settings-outline'}
              size={18}
              color="#68779b"
            />
          )}
        </TouchableOpacity>
      </View>

      {isExpanded && settings?.enabled && (
        <BrokerSettingsPanel
          settings={settings}
          profileId={profileId}
          brokerId={broker.id}
          onToggle={onToggle}
          onUpdate={onUpdate}
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  brokerCard: {
    backgroundColor: '#050416',
    borderRadius: 8,
    marginBottom: 8,
    overflow: 'hidden',
  },
  brokerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 12,
  },
  brokerLabelArea: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brokerName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
  brokerSummary: {
    fontSize: 11,
    color: '#3b82f6',
    marginTop: 2,
  },
  disabledText: {
    color: '#68779b',
  },
});
