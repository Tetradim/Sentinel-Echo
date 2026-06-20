import React, { createContext, useContext, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, StyleProp, ViewStyle } from 'react-native';

interface SelectContextValue {
  value?: string;
  open: boolean;
  setOpen: (open: boolean) => void;
  onValueChange?: (value: string) => void;
}

interface SelectProps {
  children: React.ReactNode;
  onValueChange?: (value: string) => void;
  value?: string;
}

interface SelectTriggerProps {
  children?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}

interface SelectItemProps {
  children: React.ReactNode;
  value: string;
  onPress?: () => void;
}

const SelectContext = createContext<SelectContextValue | null>(null);

function useSelectContext() {
  return useContext(SelectContext);
}

function formatValue(value: string): string {
  const normalized = value.replace(/[-_]/g, ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export function Select({ children, onValueChange, value }: SelectProps) {
  const [open, setOpen] = useState(false);
  const contextValue = useMemo(
    () => ({ value, onValueChange, open, setOpen }),
    [onValueChange, open, value]
  );

  return (
    <SelectContext.Provider value={contextValue}>
      <View style={styles.root}>{children}</View>
    </SelectContext.Provider>
  );
}

export function SelectTrigger({ children, style }: SelectTriggerProps) {
  const select = useSelectContext();

  return (
    <TouchableOpacity
      style={[styles.trigger, style]}
      onPress={() => select?.setOpen(!select.open)}
      accessibilityRole="button"
      activeOpacity={0.78}
    >
      <View style={styles.triggerRow}>
        {children || <SelectValue placeholder="Select..." />}
        <Text style={styles.chevron}>{select?.open ? '^' : 'v'}</Text>
      </View>
    </TouchableOpacity>
  );
}

export function SelectContent({ children }: { children: React.ReactNode }) {
  const select = useSelectContext();
  if (select && !select.open) return null;

  return <View style={styles.content}>{children}</View>;
}

export function SelectItem({ children, value, onPress }: SelectItemProps) {
  const select = useSelectContext();
  const active = select?.value === value;

  return (
    <TouchableOpacity
      style={[styles.item, active && styles.itemActive]}
      onPress={() => {
        select?.onValueChange?.(value);
        onPress?.();
        select?.setOpen(false);
      }}
      accessibilityRole="button"
      activeOpacity={0.78}
    >
      <Text style={[styles.itemText, active && styles.itemTextActive]}>{children}</Text>
      {active && <Text style={styles.checkmark}>OK</Text>}
    </TouchableOpacity>
  );
}

export function SelectValue({ placeholder = 'Select...' }: { placeholder?: string }) {
  const select = useSelectContext();
  const label = select?.value ? formatValue(select.value) : placeholder;

  return <Text style={styles.text}>{label}</Text>;
}

const styles = StyleSheet.create({
  root: { width: '100%' },
  trigger: {
    backgroundColor: 'rgba(16, 9, 28, 0.82)',
    borderWidth: 1,
    borderColor: '#29213a',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
  },
  triggerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  text: { color: '#edf3ff', fontSize: 13, fontWeight: '700' },
  chevron: { color: '#68779b', fontSize: 12, fontWeight: '900' },
  content: {
    backgroundColor: '#050416',
    borderRadius: 8,
    marginTop: 6,
    borderWidth: 1,
    borderColor: '#29213a',
    overflow: 'hidden',
  },
  item: {
    minHeight: 42,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(41, 33, 58, 0.82)',
  },
  itemActive: { backgroundColor: 'rgba(244, 63, 94, 0.18)' },
  itemText: { color: '#aec0e5', fontSize: 13, fontWeight: '700' },
  itemTextActive: { color: '#fb7185' },
  checkmark: { color: '#fb7185', fontSize: 10, fontWeight: '900' },
});
