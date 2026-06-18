import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { api } from '../utils/api';
import { ProfileCard, CreateProfileModal } from '../components/profiles';
import {
  ProfilesDigest,
  summarizeProfiles,
} from '../utils/profilesDigest';

import { BACKEND_URL } from '../constants/config';
import type { BrokerSettingsData, Broker, Profile } from '../types/profiles';

function DigestStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.digestStat}>
      <Text style={[styles.digestStatValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.digestStatLabel}>{label}</Text>
    </View>
  );
}

function ProfileBriefing({ digest }: { digest: ProfilesDigest }) {
  const toneColor =
    digest.primaryStatus.tone === 'live' ? '#22c55e' :
    digest.primaryStatus.tone === 'attention' ? '#f59e0b' :
    '#64748b';
  const warnings = digest.warningItems.slice(0, 3);

  return (
    <View style={[styles.digestCard, { borderColor: toneColor + '55' }]}>
      <View style={styles.digestTop}>
        <View style={styles.digestTitleBlock}>
          <Text style={styles.digestEyebrow}>PROFILE READINESS</Text>
          <Text style={styles.digestTitle}>{digest.primaryStatus.title}</Text>
          <Text style={styles.digestDetail}>{digest.primaryStatus.detail}</Text>
        </View>
        <View style={[styles.coverageBadge, { backgroundColor: toneColor + '18' }]}>
          <Text style={[styles.coverageValue, { color: toneColor }]}>{digest.profileCoveragePercent}%</Text>
          <Text style={styles.coverageLabel}>guarded</Text>
        </View>
      </View>

      <View style={styles.digestStats}>
        <DigestStat label="Active" value={digest.activeProfileName} />
        <DigestStat label="Brokers" value={String(digest.enabledBrokers)} color={digest.enabledBrokers ? undefined : '#f59e0b'} />
        <DigestStat label="Auto" value={String(digest.autoTradingBrokers)} color={digest.autoTradingBrokers ? '#f59e0b' : undefined} />
        <DigestStat label="Guarded" value={String(digest.guardedBrokers)} color={toneColor} />
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
            <Text style={styles.clearText}>Active profile broker routes have exits and shutdown controls.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

export default function ProfilesScreen() {
  const router = useRouter();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [allBrokerSettings, setAllBrokerSettings] = useState<Record<string, Record<string, BrokerSettingsData>>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');
  const [newProfileDescription, setNewProfileDescription] = useState('');
  const [expandedProfile, setExpandedProfile] = useState<string | null>(null);
  const [expandedBroker, setExpandedBroker] = useState<string | null>(null);
  // Loading guards to prevent double-tap race conditions (C12)
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [profilesRes, brokersRes] = await Promise.all([
        api.get(`${BACKEND_URL}/api/profiles`),
        api.get(`${BACKEND_URL}/api/brokers`),
      ]);
      setProfiles(profilesRes.data);
      setBrokers(brokersRes.data);

      // Fetch all profile broker-settings in parallel (fixes N+1, C11)
      const profileList: Profile[] = profilesRes.data;
      const settingsResults = await Promise.all(
        profileList.map((p) =>
          api
            .get(`${BACKEND_URL}/api/profiles/${p.id}/all-broker-settings`)
            .then((r) => ({ id: p.id, data: r.data }))
            .catch(() => ({ id: p.id, data: {} }))
        )
      );
      const settingsMap: Record<string, Record<string, BrokerSettingsData>> = {};
      for (const { id, data } of settingsResults) {
        settingsMap[id] = data;
      }
      setAllBrokerSettings(settingsMap);
    } catch (error) {
      console.error('Error fetching data:', error);
      Alert.alert('Error', 'Failed to load profiles. Pull to refresh.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const createProfile = async () => {
    if (!newProfileName.trim()) return;
    try {
      await api.post(`${BACKEND_URL}/api/profiles`, {
        name: newProfileName.trim(),
        description: newProfileDescription.trim(),
      });
      setNewProfileName('');
      setNewProfileDescription('');
      setShowCreateModal(false);
      fetchData();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to create profile');
    }
  };

  const activateProfile = async (profileId: string) => {
    if (activatingId) return; // guard double-tap
    setActivatingId(profileId);
    try {
      await api.post(`${BACKEND_URL}/api/profiles/${profileId}/activate`);
      fetchData();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to activate profile');
    } finally {
      setActivatingId(null);
    }
  };

  const deleteProfile = async (profileId: string) => {
    if (deletingId) return; // guard double-tap
    setDeletingId(profileId);
    try {
      await api.delete(`${BACKEND_URL}/api/profiles/${profileId}`);
      fetchData();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to delete profile');
    } finally {
      setDeletingId(null);
    }
  };

  const toggleBrokerSetting = async (profileId: string, brokerId: string, settingName: string) => {
    try {
      const res = await api.post(
        `${BACKEND_URL}/api/profiles/${profileId}/brokers/${brokerId}/settings/toggle/${settingName}`
      );
      setAllBrokerSettings(prev => ({
        ...prev,
        [profileId]: {
          ...prev[profileId],
          [brokerId]: res.data.broker_settings
        }
      }));
    } catch {
      Alert.alert('Error', 'Failed to update broker setting.');
    }
  };

  const updateBrokerSetting = async (profileId: string, brokerId: string, settingName: string, value: number) => {
    try {
      const res = await api.put(
        `${BACKEND_URL}/api/profiles/${profileId}/brokers/${brokerId}/settings`,
        { [settingName]: value }
      );
      setAllBrokerSettings(prev => ({
        ...prev,
        [profileId]: {
          ...prev[profileId],
          [brokerId]: res.data
        }
      }));
    } catch {
      Alert.alert('Error', 'Failed to update broker setting value.');
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

  const digest = summarizeProfiles(profiles, allBrokerSettings);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton} testID="back-button">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Profiles</Text>
        <TouchableOpacity onPress={() => setShowCreateModal(true)} style={styles.addButton} testID="add-profile-button">
          <Ionicons name="add" size={24} color="#fff" />
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3b82f6" />}
      >
        <ProfileBriefing digest={digest} />

        <View style={styles.infoCard}>
          <Ionicons name="information-circle" size={20} color="#3b82f6" />
          <Text style={styles.infoText}>
            Each broker has its own settings. Enable a broker and configure bracket orders, trailing stops, etc. independently.
          </Text>
        </View>

        {profiles.map((profile) => (
          <ProfileCard
            key={profile.id}
            profile={profile}
            brokers={brokers}
            brokerSettings={allBrokerSettings[profile.id] || {}}
            isExpanded={expandedProfile === profile.id}
            expandedBrokerId={expandedBroker}
            onProfileExpand={() => {
              setExpandedProfile(expandedProfile === profile.id ? null : profile.id);
              setExpandedBroker(null);
            }}
            onBrokerExpand={setExpandedBroker}
            onToggleBrokerSetting={toggleBrokerSetting}
            onUpdateBrokerSetting={updateBrokerSetting}
            onActivateProfile={activateProfile}
            onDeleteProfile={deleteProfile}
          />
        ))}
      </ScrollView>

      <CreateProfileModal
        visible={showCreateModal}
        profileName={newProfileName}
        profileDescription={newProfileDescription}
        onNameChange={setNewProfileName}
        onDescriptionChange={setNewProfileDescription}
        onCreate={createProfile}
        onCancel={() => setShowCreateModal(false)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between', 
    paddingHorizontal: 20, 
    paddingVertical: 16, 
    borderBottomWidth: 1, 
    borderBottomColor: '#1e293b' 
  },
  backButton: { padding: 4 },
  headerTitle: { fontSize: 20, fontWeight: '700', color: '#fff' },
  addButton: { padding: 4 },
  content: { flex: 1, padding: 16 },
  digestCard: {
    backgroundColor: '#0b1420',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginBottom: 12,
  },
  digestTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  digestTitleBlock: { flex: 1 },
  digestEyebrow: {
    color: '#64748b',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.4,
    marginBottom: 5,
  },
  digestTitle: { color: '#e2e8f0', fontSize: 18, fontWeight: '900' },
  digestDetail: { color: '#94a3b8', fontSize: 12, lineHeight: 17, marginTop: 3 },
  coverageBadge: {
    minWidth: 84,
    height: 48,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  coverageValue: { fontSize: 18, fontWeight: '900' },
  coverageLabel: { color: '#64748b', fontSize: 10, fontWeight: '800', marginTop: 1 },
  digestStats: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#132235',
  },
  digestStat: { flex: 1, alignItems: 'center' },
  digestStatValue: { color: '#e2e8f0', fontSize: 12, fontWeight: '900' },
  digestStatLabel: { color: '#64748b', fontSize: 9, fontWeight: '800', marginTop: 3 },
  warningList: { marginTop: 12, gap: 8 },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#0d1826',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#18283c',
    padding: 10,
  },
  warningCopy: { flex: 1 },
  warningTitle: { color: '#fbbf24', fontSize: 12, fontWeight: '800' },
  warningDetail: { color: '#64748b', fontSize: 11, lineHeight: 15, marginTop: 2 },
  clearText: { color: '#94a3b8', flex: 1, fontSize: 12, fontWeight: '700' },
  infoCard: { 
    flexDirection: 'row', 
    backgroundColor: '#1e3a5f', 
    padding: 12, 
    borderRadius: 8, 
    marginBottom: 16, 
    gap: 10 
  },
  infoText: { flex: 1, color: '#93c5fd', fontSize: 13, lineHeight: 18 },
});
