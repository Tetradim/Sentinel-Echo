import React from 'react';
import { View, Text, Switch, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface AutoTradingCardProps {
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
  lastAlertTime: string | null;
  premiumBufferEnabled: boolean;
  premiumBufferAmount: number;
  onTogglePremiumBuffer: () => void;
  onUpdatePremiumBufferAmount: (amount: number) => void;
  formatDate: (date: string | null) => string;
}

export const AutoTradingCard: React.FC<AutoTradingCardProps> = ({
  enabled,
  onToggle,
  isLoading,
  lastAlertTime,
  premiumBufferEnabled,
  premiumBufferAmount,
  onTogglePremiumBuffer,
  onUpdatePremiumBufferAmount,
  formatDate,
}) => {
  return (
    <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 12, padding: 16, marginHorizontal: 20, marginTop: 12 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '600', color: '#fff' }}>Auto Trading</Text>
          <Text style={{ fontSize: 14, color: '#aec0e5', marginTop: 4 }}>
            {enabled ? 'Trades execute automatically' : 'Trading paused'}
          </Text>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color="#3b82f6" />
        ) : (
          <Switch
            value={enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#374151', true: '#22c55e' }}
            thumbColor="#fff"
          />
        )}
      </View>
      <Text style={{ fontSize: 12, color: '#68779b', marginTop: 12 }}>
        Last Alert: {formatDate(lastAlertTime)}
      </Text>
      
      {enabled && (
        <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', padding: 10, borderRadius: 6, marginTop: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="shield-half" size={18} color={premiumBufferEnabled ? '#3b82f6' : '#68779b'} />
              <View>
                <Text style={{ color: '#edf3ff', fontSize: 13, fontWeight: '500' }}>Premium Buffer</Text>
                <Text style={{ color: '#68779b', fontSize: 11 }}>Skip if price too high</Text>
              </View>
            </View>
            <Switch
              value={premiumBufferEnabled}
              onValueChange={onTogglePremiumBuffer}
              trackColor={{ false: '#374151', true: '#3b82f6' }}
              thumbColor="#fff"
            />
          </View>
          {premiumBufferEnabled && (
            <View style={{ marginTop: 4 }}>
              <Text style={{ color: '#aec0e5', fontSize: 12, marginBottom: 6 }}>Max difference (cents):</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                {[5, 10, 15, 25, 50].map((amount) => (
                  <TouchableOpacity
                    key={amount}
                    style={{
                      paddingHorizontal: 10,
                      paddingVertical: 6,
                      borderRadius: 4,
                      backgroundColor: premiumBufferAmount === amount ? '#3b82f6' : '#374151'
                    }}
                    onPress={() => onUpdatePremiumBufferAmount(amount)}
                  >
                    <Text style={{ color: '#fff', fontSize: 11, fontWeight: '500' }}>{amount}¢</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Text style={{ color: '#aec0e5', fontSize: 12 }}>Custom:</Text>
                <TextInput
                  style={{
                    backgroundColor: '#050416',
                    color: '#fff',
                    borderRadius: 4,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                    fontSize: 12,
                    width: 70,
                    textAlign: 'center',
                    borderWidth: 1,
                    borderColor: ![5, 10, 15, 25, 50].includes(premiumBufferAmount) ? '#3b82f6' : '#374151'
                  }}
                  keyboardType="numeric"
                  placeholder="e.g. 75"
                  placeholderTextColor="#68779b"
                  value={![5, 10, 15, 25, 50].includes(premiumBufferAmount) ? String(premiumBufferAmount) : ''}
                  onChangeText={(text) => {
                    const num = parseInt(text, 10);
                    if (!isNaN(num) && num > 0) {
                      onUpdatePremiumBufferAmount(num);
                    }
                  }}
                  onBlur={() => {
                    if (premiumBufferAmount <= 0) {
                      onUpdatePremiumBufferAmount(10);
                    }
                  }}
                />
                <Text style={{ color: '#68779b', fontSize: 11 }}>cents</Text>
              </View>
              <Text style={{ color: '#68779b', fontSize: 10 }}>
                Trade skipped if live premium exceeds alert by {premiumBufferAmount}¢ (${(premiumBufferAmount / 100).toFixed(2)})
              </Text>
            </View>
          )}
        </View>
      )}
    </View>
  );
};
