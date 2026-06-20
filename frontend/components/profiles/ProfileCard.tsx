import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BrokerRow } from './BrokerRow';
import type { BrokerSettingsData, Broker, Profile } from '../../types/profiles';

interface ProfileCardProps {
  profile: Profile;
  brokers: Broker[];
  brokerSettings: Record<string, BrokerSettingsData>;
  isExpanded: boolean;
  expandedBrokerId: string | null;
  onProfileExpand: () => void;
  onBrokerExpand: (brokerId: string | null) => void;
  onToggleBrokerSetting: (profileId: string, brokerId: string, settingName: string) => void;
  onUpdateBrokerSetting: (profileId: string, brokerId: string, settingName: string, value: number) => void;
  onActivateProfile: (profileId: string) => void;
  onDeleteProfile: (profileId: string) => void;
}

export const ProfileCard: React.FC<ProfileCardProps> = ({
  profile,
  brokers,
  brokerSettings,
  isExpanded,
  expandedBrokerId,
  onProfileExpand,
  onBrokerExpand,
  onToggleBrokerSetting,
  onUpdateBrokerSetting,
  onActivateProfile,
  onDeleteProfile,
}) => {
  const getEnabledBrokersCount = (): number => {
    return Object.values(brokerSettings).filter(s => s.enabled).length;
  };

  const handleDelete = () => {
    Alert.alert('Delete Profile', `Delete "${profile.name}"? This cannot be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => onDeleteProfile(profile.id),
      },
    ]);
  };

  return (
    <View
      style={[styles.profileCard, profile.is_active && styles.activeProfileCard]}
      testID={`profile-card-${profile.id}`}
    >
      <TouchableOpacity
        style={styles.profileHeader}
        onPress={onProfileExpand}
        testID={`profile-header-${profile.id}`}
      >
        <View style={styles.profileInfo}>
          <View style={styles.profileTitleRow}>
            {profile.is_active && (
              <View style={styles.activeBadge}>
                <Text style={styles.activeBadgeText}>ACTIVE</Text>
              </View>
            )}
            <Text style={styles.profileName}>{profile.name}</Text>
          </View>
          {/* Show description field (fixes M29) */}
          {profile.description ? (
            <Text style={styles.profileDescription}>{profile.description}</Text>
          ) : null}
          <Text style={styles.brokerCount}>
            {getEnabledBrokersCount()} broker{getEnabledBrokersCount() !== 1 ? 's' : ''} enabled
          </Text>
        </View>
        <Ionicons 
          name={isExpanded ? "chevron-up" : "chevron-down"} 
          size={20} 
          color="#68779b"
        />
      </TouchableOpacity>

      {isExpanded && (
        <View style={styles.profileExpanded}>
          {brokers.map((broker) => (
            <BrokerRow
              key={broker.id}
              broker={broker}
              settings={brokerSettings[broker.id]}
              profileId={profile.id}
              isExpanded={expandedBrokerId === broker.id}
              onExpandToggle={() => onBrokerExpand(expandedBrokerId === broker.id ? null : broker.id)}
              onToggle={onToggleBrokerSetting}
              onUpdate={onUpdateBrokerSetting}
            />
          ))}

          {/* Profile Actions */}
          <View style={styles.profileActions}>
            {!profile.is_active && (
              <>
                <TouchableOpacity 
                  style={styles.activateButton} 
                  onPress={() => onActivateProfile(profile.id)}
                  testID={`activate-profile-${profile.id}`}
                >
                  <Ionicons name="checkmark-circle" size={18} color="#fff" />
                  <Text style={styles.activateButtonText}>Set Active</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                  style={styles.deleteButton} 
                  onPress={handleDelete}
                  testID={`delete-profile-${profile.id}`}
                >
                  <Ionicons name="trash" size={18} color="#ef4444" />
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  profileCard: {
    backgroundColor: 'rgba(16, 9, 28, 0.88)',
    borderRadius: 12,
    marginBottom: 12,
    overflow: 'hidden',
  },
  activeProfileCard: {
    borderWidth: 2,
    borderColor: '#22c55e',
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
  },
  profileInfo: {
    flex: 1,
  },
  profileTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  activeBadge: {
    backgroundColor: '#22c55e',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  activeBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
  },
  profileName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  profileDescription: {
    fontSize: 12,
    color: '#68779b',
    marginTop: 2,
    marginBottom: 2,
  },
  brokerCount: {
    fontSize: 12,
    color: '#68779b',
    marginTop: 4,
  },
  profileExpanded: {
    borderTopWidth: 1,
    borderTopColor: '#374151',
    padding: 12,
  },
  profileActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  activateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#22c55e',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
  },
  activateButtonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 13,
  },
  deleteButton: {
    padding: 8,
    borderRadius: 6,
    backgroundColor: '#2d1f1f',
  },
});
