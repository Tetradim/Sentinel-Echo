import React from 'react';
import { ScrollView, View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Stack, useRouter, usePathname } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import {
  getActiveOperatorTab,
  getOperatorRoutePath,
  OPERATOR_TABS,
  shouldShowOperatorTabs,
} from '../utils/operatorNavigation';

function BottomTabBar() {
  const router = useRouter();
  const pathname = usePathname();
  const currentTab = getActiveOperatorTab(pathname);

  return (
    <View style={styles.tabBar}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tabRail}
      >
        {OPERATOR_TABS.map((tab) => {
          const isActive = currentTab === tab.name;
          return (
            <TouchableOpacity
              key={tab.name}
              style={[styles.tabItem, isActive && styles.tabItemActive]}
              onPress={() => router.push(getOperatorRoutePath(tab.name) as any)}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityState={{ selected: isActive }}
            >
              <View style={[styles.tabIconWrap, isActive && styles.tabIconWrapActive]}>
                <Ionicons
                  name={(isActive ? tab.iconActive : tab.icon) as any}
                  size={19}
                  color={isActive ? '#7dd3fc' : '#64748b'}
                />
              </View>
              <Text style={[styles.tabLabel, isActive && styles.tabLabelActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

export default function RootLayout() {
  const pathname = usePathname();
  const showTabs = shouldShowOperatorTabs(pathname);

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
          <Stack.Screen name="operator-lab" />
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
    backgroundColor: '#0d1826',
    borderTopWidth: 1,
    borderTopColor: '#1e2d3d',
    paddingBottom: 8,
    paddingTop: 6,
  },
  tabRail: {
    paddingHorizontal: 8,
    gap: 6,
  },
  tabItem: {
    minWidth: 72,
    alignItems: 'center',
    gap: 3,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  tabItemActive: {
    backgroundColor: '#08111f',
  },
  tabIconWrap: {
    width: 38,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabIconWrapActive: {
    backgroundColor: 'rgba(14, 165, 233, 0.16)',
  },
  tabLabel: {
    fontSize: 10,
    color: '#64748b',
    fontWeight: '700',
  },
  tabLabelActive: {
    color: '#7dd3fc',
  },
});
