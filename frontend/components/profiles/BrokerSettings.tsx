import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SettingRow, SettingRowWithInput } from './SettingRow';
import type { BrokerSettingsData } from '../../types/profiles';

interface BrokerSettingsProps {
  settings: BrokerSettingsData;
  profileId: string;
  brokerId: string;
  onToggle: (profileId: string, brokerId: string, settingName: string) => void;
  onUpdate: (profileId: string, brokerId: string, settingName: string, value: number) => void;
}

export const BrokerSettingsPanel: React.FC<BrokerSettingsProps> = ({
  settings,
  profileId,
  brokerId,
  onToggle,
  onUpdate,
}) => {
  return (
    <View style={styles.brokerSettings}>
      {/* Trading Mode */}
      <Text style={styles.settingSectionTitle}>Trading Mode</Text>
      
      <SettingRow
        title="Alerts Only"
        enabled={settings.alerts_only}
        onToggle={() => onToggle(profileId, brokerId, 'alerts_only')}
        trackColor="#f59e0b"
        testID={`setting-alerts-only-${brokerId}`}
      />

      {!settings.alerts_only && (
        <>
          <SettingRow
            title="Auto Trading"
            enabled={settings.auto_trading_enabled}
            onToggle={() => onToggle(profileId, brokerId, 'auto_trading_enabled')}
            trackColor="#22c55e"
            testID={`setting-auto-trading-${brokerId}`}
          />

          {/* Risk Management */}
          <Text style={[styles.settingSectionTitle, { marginTop: 12 }]}>Risk Management</Text>

          <SettingRowWithInput
            title="Take Profit"
            value={settings.take_profit_percentage}
            onValueChange={(num) => onUpdate(profileId, brokerId, 'take_profit_percentage', num)}
            enabled={settings.take_profit_enabled}
            onToggle={() => onToggle(profileId, brokerId, 'take_profit_enabled')}
            trackColor="#22c55e"
            inputLabel="%"
            testID={`setting-take-profit-${brokerId}`}
          />

          {settings.take_profit_enabled && (
            <SettingRow
              title="Bracket Order"
              description="TP + SL together"
              enabled={settings.bracket_order_enabled}
              onToggle={() => onToggle(profileId, brokerId, 'bracket_order_enabled')}
              trackColor="#3b82f6"
              testID={`setting-bracket-order-${brokerId}`}
            />
          )}

          <SettingRowWithInput
            title="Stop Loss"
            value={settings.stop_loss_percentage}
            onValueChange={(num) => onUpdate(profileId, brokerId, 'stop_loss_percentage', num)}
            enabled={settings.stop_loss_enabled}
            onToggle={() => onToggle(profileId, brokerId, 'stop_loss_enabled')}
            trackColor="#ef4444"
            inputLabel="%"
            testID={`setting-stop-loss-${brokerId}`}
          />

          <SettingRowWithInput
            title="Trailing Stop"
            value={settings.trailing_stop_percent}
            onValueChange={(num) => onUpdate(profileId, brokerId, 'trailing_stop_percent', num)}
            enabled={settings.trailing_stop_enabled}
            onToggle={() => onToggle(profileId, brokerId, 'trailing_stop_enabled')}
            trackColor="#8b5cf6"
            inputLabel="% from high"
            testID={`setting-trailing-stop-${brokerId}`}
          />

          <SettingRow
            title="Averaging Down"
            description="Buy more on drops"
            enabled={settings.averaging_down_enabled}
            onToggle={() => onToggle(profileId, brokerId, 'averaging_down_enabled')}
            trackColor="#f59e0b"
            testID={`setting-averaging-down-${brokerId}`}
          />

          <SettingRow
            title="Auto Shutdown"
            description={`After ${settings.max_consecutive_losses} losses`}
            enabled={settings.auto_shutdown_enabled}
            onToggle={() => onToggle(profileId, brokerId, 'auto_shutdown_enabled')}
            trackColor="#f97316"
            testID={`setting-auto-shutdown-${brokerId}`}
          />
        </>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  brokerSettings: {
    padding: 12,
    paddingTop: 0,
    borderTopWidth: 1,
    borderTopColor: 'rgba(16, 9, 28, 0.88)',
  },
  settingSectionTitle: {
    fontSize: 11,
    fontWeight: '600',
    color: '#68779b',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
});
