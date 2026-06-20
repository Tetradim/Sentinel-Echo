import React from 'react';
import { View, Text, Switch, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export const TakeProfitCard: React.FC<{
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
  percentage: number;
  bracketOrderEnabled: boolean;
  onToggleBracketOrder: () => void;
}> = ({
  enabled,
  onToggle,
  isLoading,
  percentage,
  bracketOrderEnabled,
  onToggleBracketOrder,
}) => {
  return (
    <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 12, padding: 16, marginHorizontal: 20, marginTop: 12, borderLeftWidth: 3, borderLeftColor: enabled ? '#22c55e' : '#374151' }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="arrow-up-circle" size={24} color="#22c55e" />
          <View>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#fff' }}>Take Profit</Text>
            <Text style={{ fontSize: 14, color: '#aec0e5', marginTop: 4 }}>
              {enabled ? `Auto-sell at +${percentage}%` : 'Disabled'}
            </Text>
          </View>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color="#22c55e" />
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
        Overrides Discord sell commands when profit target hit
      </Text>
      {enabled && (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'rgba(16, 9, 28, 0.88)', padding: 10, borderRadius: 6, marginTop: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="layers" size={18} color={bracketOrderEnabled ? '#3b82f6' : '#68779b'} />
            <View>
              <Text style={{ color: '#edf3ff', fontSize: 13, fontWeight: '500' }}>Bracket Order</Text>
              <Text style={{ color: '#68779b', fontSize: 11 }}>Submit TP + SL together</Text>
            </View>
          </View>
          <Switch
            value={bracketOrderEnabled}
            onValueChange={onToggleBracketOrder}
            trackColor={{ false: '#374151', true: '#3b82f6' }}
            thumbColor="#fff"
          />
        </View>
      )}
    </View>
  );
};

export const StopLossCard: React.FC<{
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
  percentage: number;
  orderType: string;
  onSetOrderType: (type: string) => void;
}> = ({
  enabled,
  onToggle,
  isLoading,
  percentage,
  orderType,
  onSetOrderType,
}) => {
  return (
    <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 12, padding: 16, marginHorizontal: 20, marginTop: 12, borderLeftWidth: 3, borderLeftColor: enabled ? '#ef4444' : '#374151' }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="arrow-down-circle" size={24} color="#ef4444" />
          <View>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#fff' }}>Stop Loss</Text>
            <Text style={{ fontSize: 14, color: '#aec0e5', marginTop: 4 }}>
              {enabled ? `Auto-sell at -${percentage}% (${orderType})` : 'Disabled'}
            </Text>
          </View>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color="#ef4444" />
        ) : (
          <Switch
            value={enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#374151', true: '#ef4444' }}
            thumbColor="#fff"
          />
        )}
      </View>
      <Text style={{ fontSize: 12, color: '#68779b', marginTop: 12 }}>
        Overrides Discord commands - protects against large losses
      </Text>
      {enabled && (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'rgba(16, 9, 28, 0.88)', padding: 10, borderRadius: 6, marginTop: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="flash" size={18} color={orderType === 'market' ? '#ef4444' : '#68779b'} />
            <Text style={{ color: '#edf3ff', fontSize: 13, fontWeight: '500' }}>Order Type</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <TouchableOpacity
              style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4, backgroundColor: orderType === 'market' ? '#ef4444' : '#374151' }}
              onPress={() => onSetOrderType('market')}
            >
              <Text style={{ color: '#fff', fontSize: 12, fontWeight: '600' }}>Market</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4, backgroundColor: orderType === 'limit' ? '#3b82f6' : '#374151' }}
              onPress={() => onSetOrderType('limit')}
            >
              <Text style={{ color: '#fff', fontSize: 12, fontWeight: '600' }}>Limit</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
};

export const AveragingDownCard: React.FC<{
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
}> = ({ enabled, onToggle, isLoading }) => {
  return (
    <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 12, padding: 16, marginHorizontal: 20, marginTop: 12, borderLeftWidth: 3, borderLeftColor: enabled ? '#f59e0b' : '#374151' }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="trending-down" size={24} color="#f59e0b" />
          <View>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#fff' }}>Averaging Down</Text>
            <Text style={{ fontSize: 14, color: '#aec0e5', marginTop: 4 }}>
              {enabled ? 'Buy more when price drops' : 'Disabled'}
            </Text>
          </View>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color="#f59e0b" />
        ) : (
          <Switch
            value={enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#374151', true: '#f59e0b' }}
            thumbColor="#fff"
          />
        )}
      </View>
      <Text style={{ fontSize: 12, color: '#68779b', marginTop: 12 }}>
        Discord: "AVERAGE DOWN $TICKER" or "AVG DOWN $TICKER"
      </Text>
    </View>
  );
};

export const TrailingStopCard: React.FC<{
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
  type: string;
  percent: number;
  cents: number;
}> = ({ enabled, onToggle, isLoading, type, percent, cents }) => {
  return (
    <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 12, padding: 16, marginHorizontal: 20, marginTop: 12, borderLeftWidth: 3, borderLeftColor: enabled ? '#8b5cf6' : '#374151' }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="git-branch" size={24} color="#8b5cf6" />
          <View>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#fff' }}>Trailing Stop</Text>
            <Text style={{ fontSize: 14, color: '#aec0e5', marginTop: 4 }}>
              {enabled 
                ? type === 'percent'
                  ? `Trail -${percent}% from high`
                  : `Trail -${cents}¢ from high`
                : 'Disabled'}
            </Text>
          </View>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color="#8b5cf6" />
        ) : (
          <Switch
            value={enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#374151', true: '#8b5cf6' }}
            thumbColor="#fff"
          />
        )}
      </View>
      <Text style={{ fontSize: 12, color: '#68779b', marginTop: 12 }}>
        {type === 'percent' ? 'Percent trailing' : 'Premium (cents) trailing'} - locks in profits as price rises
      </Text>
    </View>
  );
};

export const AutoShutdownCard: React.FC<{
  enabled: boolean;
  onToggle: () => void;
  isLoading: boolean;
  maxConsecutiveLosses: number;
  consecutiveLosses: number;
  dailyLosses: number;
  maxDailyLosses: number;
  shutdownTriggered: boolean;
  shutdownReason: string;
  onResetCounters: () => void;
  onUpdateMaxConsecutive: (value: number) => void;
  onUpdateMaxDaily: (value: number) => void;
}> = ({ 
  enabled, 
  onToggle, 
  isLoading, 
  maxConsecutiveLosses, 
  consecutiveLosses, 
  dailyLosses, 
  maxDailyLosses,
  shutdownTriggered,
  shutdownReason,
  onResetCounters,
  onUpdateMaxConsecutive,
  onUpdateMaxDaily,
}) => {
  return (
    <View style={{ backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 12, padding: 16, marginHorizontal: 20, marginTop: 12, borderLeftWidth: 3, borderLeftColor: shutdownTriggered ? '#dc2626' : enabled ? '#f97316' : '#374151' }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="power" size={24} color={shutdownTriggered ? '#dc2626' : '#f97316'} />
          <View>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#fff' }}>Auto Shutdown</Text>
            <Text style={{ fontSize: 14, color: '#aec0e5', marginTop: 4 }}>
              {shutdownTriggered 
                ? 'SHUTDOWN TRIGGERED'
                : enabled 
                  ? `After ${maxConsecutiveLosses} consecutive losses`
                  : 'Disabled'}
            </Text>
          </View>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color="#f97316" />
        ) : (
          <Switch
            value={enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#374151', true: '#f97316' }}
            thumbColor="#fff"
            disabled={shutdownTriggered}
          />
        )}
      </View>
      {shutdownTriggered ? (
        <View>
          <Text style={{ fontSize: 12, color: '#dc2626', marginTop: 12 }}>
            {shutdownReason}
          </Text>
          <TouchableOpacity 
            style={{ backgroundColor: '#22c55e', padding: 8, borderRadius: 6, marginTop: 8, alignItems: 'center' }}
            onPress={onResetCounters}
          >
            <Text style={{ color: '#fff', fontWeight: '600' }}>Reset & Resume Trading</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View>
          <Text style={{ fontSize: 12, color: '#68779b', marginTop: 12 }}>
            Losses: {consecutiveLosses}/{maxConsecutiveLosses} consecutive, {dailyLosses}/{maxDailyLosses} daily
          </Text>
          {enabled && (
            <View style={{ marginTop: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <Text style={{ color: '#aec0e5', fontSize: 12 }}>Max consecutive losses:</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  {[2, 3, 5, 7, 10].map((num) => (
                    <TouchableOpacity
                      key={num}
                      style={{
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                        borderRadius: 4,
                        backgroundColor: maxConsecutiveLosses === num ? '#f97316' : '#374151'
                      }}
                      onPress={() => onUpdateMaxConsecutive(num)}
                    >
                      <Text style={{ color: '#fff', fontSize: 11, fontWeight: '500' }}>{num}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ color: '#aec0e5', fontSize: 12 }}>Max daily losses:</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  {[3, 5, 7, 10, 15].map((num) => (
                    <TouchableOpacity
                      key={num}
                      style={{
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                        borderRadius: 4,
                        backgroundColor: maxDailyLosses === num ? '#f97316' : '#374151'
                      }}
                      onPress={() => onUpdateMaxDaily(num)}
                    >
                      <Text style={{ color: '#fff', fontSize: 11, fontWeight: '500' }}>{num}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>
          )}
        </View>
      )}
    </View>
  );
};
