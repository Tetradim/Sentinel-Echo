import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Stack, useRouter, usePathname } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';

const TABS = [
  { name: 'index',            label: 'Dashboard', icon: 'pulse',            iconActive: 'pulse'            },
  { name: 'alerts',       label: 'Alerts',    icon: 'notifications-outline', iconActive: 'notifications' },
  { name: 'trades',       label: 'Trades',    icon: 'receipt-outline',   iconActive: 'receipt'          },
  { name: 'positions',    label: 'Positions', icon: 'briefcase-outline', iconActive: 'briefcase'        },
  { name: 'risk-settings',  label: 'Risk',    icon: 'shield-outline', iconActive: 'shield'            },
  { name: 'trading-settings', label: 'Trading', icon: 'options-outline', iconActive: 'options'        },
  { name: 'strike-selection', label: 'Strikes', icon: 'trending-up-outline', iconActive: 'trending-up'  },
  { name: 'discord-settings', label: 'Discord', icon: 'chatbubbles-outline', iconActive: 'chatbubbles'  },
  { name: 'settings',    label: 'Settings',  icon: 'settings-outline',  iconActive: 'settings'         },
] as const;

function BottomTabBar() {
  const router = useRouter();
  const pathname = usePathname();

  const currentTab = pathname === '/' ? 'index' : pathname.replace('/', '');

  return (
    <View style={styles.tabBar}>
      {TABS.map((tab) => {
        const isActive = currentTab === tab.name;
        return (
          <TouchableOpacity
            key={tab.name}
            style={styles.tabItem}
            onPress={() => router.push(tab.name === 'index' ? '/' : `/${tab.name}`)}
            activeOpacity={0.7}
          >
            <View style={[styles.tabIconWrap, isActive && styles.tabIconWrapActive]}>
              <Ionicons
                name={(isActive ? tab.iconActive : tab.icon) as any}
                size={20}
                color={isActive ? '#0ea5e9' : '#475569'}
              />
            </View>
            <Text style={[styles.tabLabel, isActive && styles.tabLabelActive]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export default function RootLayout() {
  const pathname = usePathname();
  // Only show tab bar on main screens
  const showTabs = [
    '/',
    '/positions',
    '/trades',
    '/alerts',
    '/settings',
    '/risk-settings',
    '/trading-settings',
    '/strike-selection',
    '/discord-settings',
  ].includes(pathname);

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <View style={styles.root}>
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: '#080f1a' },
            animation: 'fade',
          }}
        >
          <Stack.Screen name="index" />
          <Stack.Screen name="alerts" />
          <Stack.Screen name="trades" />
          <Stack.Screen name="positions" />
          <Stack.Screen name="risk-settings" />
          <Stack.Screen name="trading-settings" />
          <Stack.Screen name="strike-selection" />
          <Stack.Screen name="discord-settings" />
          <Stack.Screen name="settings" />
          <Stack.Screen name="broker-config" />
          <Stack.Screen name="profiles" />
        </Stack>
        {showTabs && <BottomTabBar />}
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#080f1a',
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#0d1826',
    borderTopWidth: 1,
    borderTopColor: '#1e2d3d',
    paddingBottom: 8,
    paddingTop: 6,
    paddingHorizontal: 4,
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    gap: 3,
  },
  tabIconWrap: {
    width: 36,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabIconWrapActive: {
    backgroundColor: 'rgba(14, 165, 233, 0.12)',
  },
  tabLabel: {
    fontSize: 10,
    color: '#475569',
    fontWeight: '500',
  },
  tabLabelActive: {
    color: '#0ea5e9',
  },
});
