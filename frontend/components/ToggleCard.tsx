import React from 'react';
import { View, Text, StyleSheet, Switch, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface ToggleCardProps {
  title: string;
  subtitle: string;
  enabled: boolean;
  onToggle: () => void;
  isLoading?: boolean;
  icon: keyof typeof Ionicons.glyphMap;
  iconColor: string;
  borderColor?: string;
  children?: React.ReactNode;
  testID?: string;
}

export const ToggleCard: React.FC<ToggleCardProps> = ({
  title,
  subtitle,
  enabled,
  onToggle,
  isLoading = false,
  icon,
  iconColor,
  borderColor,
  children,
  testID,
}) => {
  return (
    <View 
      style={[
        styles.card, 
        borderColor ? { borderLeftWidth: 3, borderLeftColor: enabled ? borderColor : '#374151' } : {}
      ]}
      testID={testID}
    >
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Ionicons name={icon} size={24} color={iconColor} />
          <View style={styles.titleContainer}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.subtitle}>{subtitle}</Text>
          </View>
        </View>
        {isLoading ? (
          <ActivityIndicator size="small" color={iconColor} />
        ) : (
          <Switch
            value={enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#374151', true: iconColor }}
            thumbColor="#fff"
          />
        )}
      </View>
      {children}
    </View>
  );
};

interface NestedToggleProps {
  title: string;
  subtitle: string;
  enabled: boolean;
  onToggle: () => void;
  icon: keyof typeof Ionicons.glyphMap;
  iconColor: string;
}

export const NestedToggle: React.FC<NestedToggleProps> = ({
  title,
  subtitle,
  enabled,
  onToggle,
  icon,
  iconColor,
}) => {
  return (
    <View style={styles.nestedContainer}>
      <View style={styles.nestedRow}>
        <Ionicons name={icon} size={18} color={enabled ? iconColor : '#68779b'} />
        <View style={styles.nestedTextContainer}>
          <Text style={styles.nestedTitle}>{title}</Text>
          <Text style={styles.nestedSubtitle}>{subtitle}</Text>
        </View>
      </View>
      <Switch
        value={enabled}
        onValueChange={onToggle}
        trackColor={{ false: '#374151', true: iconColor }}
        thumbColor="#fff"
      />
    </View>
  );
};

interface ButtonGroupProps {
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (value: string) => void;
  activeColor?: string;
}

export const ButtonGroup: React.FC<ButtonGroupProps> = ({
  options,
  selected,
  onSelect,
  activeColor = '#3b82f6',
}) => {
  return (
    <View style={styles.buttonGroup}>
      {options.map((option) => (
        <TouchableOpacity
          key={option.value}
          style={[
            styles.button,
            { backgroundColor: selected === option.value ? activeColor : '#374151' }
          ]}
          onPress={() => onSelect(option.value)}
        >
          <Text style={styles.buttonText}>{option.label}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 20,
    marginTop: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  titleContainer: {},
  title: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
  },
  subtitle: {
    fontSize: 14,
    color: '#aec0e5',
    marginTop: 4,
  },
  nestedContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    padding: 10,
    borderRadius: 6,
    marginTop: 10,
  },
  nestedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  nestedTextContainer: {},
  nestedTitle: {
    color: '#edf3ff',
    fontSize: 13,
    fontWeight: '500',
  },
  nestedSubtitle: {
    color: '#68779b',
    fontSize: 11,
  },
  buttonGroup: {
    flexDirection: 'row',
    gap: 6,
  },
  button: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 4,
  },
  buttonText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
});
