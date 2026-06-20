import React, { useRef } from 'react';
import { View, Text, StyleSheet, Switch, TextInput } from 'react-native';

interface SettingRowProps {
  title: string;
  description?: string;
  enabled: boolean;
  onToggle: () => void;
  trackColor?: string;
  testID?: string;
}

export const SettingRow: React.FC<SettingRowProps> = ({
  title,
  description,
  enabled,
  onToggle,
  trackColor = '#22c55e',
  testID,
}) => {
  return (
    <View style={styles.settingRow} testID={testID}>
      <View>
        <Text style={styles.settingName}>{title}</Text>
        {description && <Text style={styles.settingDesc}>{description}</Text>}
      </View>
      <Switch
        value={enabled}
        onValueChange={onToggle}
        trackColor={{ false: '#374151', true: trackColor }}
        thumbColor="#fff"
      />
    </View>
  );
};

interface SettingRowWithInputProps {
  title: string;
  value: number;
  onValueChange: (value: number) => void;
  enabled: boolean;
  onToggle: () => void;
  trackColor?: string;
  inputLabel?: string;
  min?: number;
  max?: number;
  testID?: string;
}

export const SettingRowWithInput: React.FC<SettingRowWithInputProps> = ({
  title,
  value,
  onValueChange,
  enabled,
  onToggle,
  trackColor = '#22c55e',
  inputLabel = '%',
  min = 0.1,
  max = 100,
  testID,
}) => {
  // Debounce API calls — only fire after 600ms of no typing (fixes M20)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleChange = (text: string) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      const num = parseFloat(text);
      // Range validation — reject 0, NaN, and out-of-range values (fixes M21)
      if (!isNaN(num) && num >= min && num <= max) {
        onValueChange(num);
      }
    }, 600);
  };

  return (
    <View style={styles.settingRow} testID={testID}>
      <View style={{ flex: 1 }}>
        <Text style={styles.settingName}>{title}</Text>
        <View style={styles.inputRow}>
          <TextInput
            style={[styles.percentInput, !enabled && styles.disabledInput]}
            keyboardType="numeric"
            defaultValue={String(value)}
            onChangeText={handleChange}
            editable={enabled}
            maxLength={6}
            selectTextOnFocus
          />
          <Text style={styles.percentLabel}>{inputLabel}</Text>
        </View>
      </View>
      <Switch
        value={enabled}
        onValueChange={onToggle}
        trackColor={{ false: '#374151', true: trackColor }}
        thumbColor="#fff"
      />
    </View>
  );
};

const styles = StyleSheet.create({
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
  },
  settingName: {
    fontSize: 13,
    fontWeight: '500',
    color: '#edf3ff',
  },
  settingDesc: {
    fontSize: 11,
    color: '#68779b',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  percentInput: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    color: '#fff',
    borderRadius: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    fontSize: 14,
    width: 60,
    textAlign: 'center',
    borderWidth: 1,
    borderColor: '#374151',
  },
  disabledInput: {
    opacity: 0.4,
  },
  percentLabel: {
    color: '#68779b',
    fontSize: 12,
  },
});
