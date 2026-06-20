import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

interface SliderProps {
  value?: number[];
  min?: number;
  max?: number;
  step?: number;
  minimumValue?: number;
  maximumValue?: number;
  disabled?: boolean;
  onValueChange?: (value: number[]) => void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function Slider({
  value = [0],
  min,
  max,
  step = 1,
  minimumValue,
  maximumValue,
  disabled = false,
  onValueChange,
}: SliderProps) {
  const lowerBound = min ?? minimumValue ?? 0;
  const upperBound = max ?? maximumValue ?? 100;
  const currentValue = clamp(Number(value[0] ?? lowerBound), lowerBound, upperBound);
  const range = Math.max(upperBound - lowerBound, 1);
  const fillPercent = ((currentValue - lowerBound) / range) * 100;

  const updateValue = (direction: -1 | 1) => {
    if (disabled) return;
    const nextValue = clamp(currentValue + (step * direction), lowerBound, upperBound);
    onValueChange?.([nextValue]);
  };

  return (
    <View style={styles.root}>
      <View style={styles.row}>
        <TouchableOpacity
          style={[styles.stepButton, (disabled || currentValue <= lowerBound) && styles.stepButtonDisabled]}
          onPress={() => updateValue(-1)}
          disabled={disabled || currentValue <= lowerBound}
          accessibilityRole="button"
        >
          <Text style={styles.stepButtonText}>-</Text>
        </TouchableOpacity>
        <View style={styles.track}>
          <View style={[styles.trackFill, { width: `${fillPercent}%` }]} />
        </View>
        <TouchableOpacity
          style={[styles.stepButton, (disabled || currentValue >= upperBound) && styles.stepButtonDisabled]}
          onPress={() => updateValue(1)}
          disabled={disabled || currentValue >= upperBound}
          accessibilityRole="button"
        >
          <Text style={styles.stepButtonText}>+</Text>
        </TouchableOpacity>
      </View>
      <View style={styles.metaRow}>
        <Text style={styles.metaText}>{lowerBound}</Text>
        <Text style={styles.valueText}>{currentValue}</Text>
        <Text style={styles.metaText}>{upperBound}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  stepButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    borderWidth: 1,
    borderColor: '#f43f5e',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepButtonDisabled: {
    backgroundColor: '#111827',
    borderColor: '#29213a',
    opacity: 0.55,
  },
  stepButtonText: { color: '#fb7185', fontSize: 18, fontWeight: '900' },
  track: {
    flex: 1,
    height: 10,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: '#29213a',
  },
  trackFill: { height: '100%', borderRadius: 999, backgroundColor: '#f43f5e' },
  metaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  metaText: { color: '#68779b', fontSize: 11, fontWeight: '700' },
  valueText: { color: '#edf3ff', fontSize: 12, fontWeight: '900' },
});
