import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
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

const SHELL_ACCENTS = ['#6366f1', '#25d0a4', '#f59e0b', '#f43f5e', '#38bdf8', '#a78bfa', '#d8ad1f', '#fb7185'];
const OPERATOR_LABELS: Record<string, string> = {
  index: 'Dashboard',
  alerts: 'Alerts',
  trades: 'Trades',
  positions: 'Positions',
  'operator-lab': 'Operator Lab',
  'strike-selection': 'Strike Selection',
  'trading-settings': 'Trading',
  'risk-settings': 'Risk',
  'discord-settings': 'Discord',
  'broker-config': 'Broker',
  profiles: 'Profiles',
  settings: 'Settings',
};
const SHELL_THEMES = {
  midnight: {
    label: 'Midnight',
    bg: '#020617',
    header: '#07111f',
    card: '#0b1220',
    border: '#1e2d44',
    text: '#e5edf8',
    muted: '#9db0cc',
  },
  space: {
    label: 'Space',
    bg: '#050416',
    header: '#08061d',
    card: '#10091c',
    border: '#29213a',
    text: '#edf3ff',
    muted: '#aec0e5',
  },
  forest: {
    label: 'Forest',
    bg: '#02120b',
    header: '#062018',
    card: '#081a12',
    border: '#183927',
    text: '#e8fff3',
    muted: '#a7cdb6',
  },
} as const;
const SHELL_DENSITY_PADDING = {
  compact: 12,
  standard: 16,
  spacious: 22,
} as const;

type ShellThemeKey = keyof typeof SHELL_THEMES;
type ShellDensityKey = keyof typeof SHELL_DENSITY_PADDING;

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const bigint = parseInt(clean.length === 3 ? clean.split('').map((char) => char + char).join('') : clean, 16);
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `rgba(${r}, ${g}, ${b}, ${Math.min(1, Math.max(0, alpha))})`;
}

function BottomTabBar() {
  const router = useRouter();
  const pathname = usePathname();
  const currentTab = getActiveOperatorTab(pathname);

  return (
    <View style={styles.tabBar} testID="operator-bottom-tab">
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
                  color={isActive ? '#fb7185' : '#68779b'}
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

function RangeInput({
  value,
  min,
  max,
  step,
  onChange,
  accent,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  accent: string;
}) {
  if (Platform.OS !== 'web') return null;

  return React.createElement('input' as any, {
    type: 'range',
    min,
    max,
    step,
    value,
    onChange: (event: any) => onChange(Number(event.target.value)),
    style: {
      width: '100%',
      height: 18,
      accentColor: accent,
      cursor: 'pointer',
      background: 'transparent',
      border: 0,
      margin: 0,
      padding: 0,
    },
  });
}

function WebShellBackground({
  accent,
  pattern,
  backgroundColor,
}: {
  accent: string;
  pattern: 'triangle' | 'hex' | 'circuit';
  backgroundColor: string;
}) {
  const patternColor = hexToRgba(accent, pattern === 'circuit' ? 0.18 : 0.11);

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <View style={[StyleSheet.absoluteFill, styles.webBgCanvas, { backgroundColor }]} />
      {pattern === 'triangle' && (
        <View style={styles.patternLayer}>
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <View key={item} style={[styles.triangleMark, { borderBottomColor: patternColor, left: `${item * 18 + 4}%`, top: `${item * 12 + 8}%` }]} />
          ))}
        </View>
      )}
      {pattern === 'hex' && (
        <View style={styles.patternLayer}>
          {[0, 1, 2, 3, 4, 5, 6].map((item) => (
            <View key={item} style={[styles.hexMark, { borderColor: patternColor, left: `${item * 14 + 4}%`, top: `${(item % 4) * 22 + 9}%` }]} />
          ))}
        </View>
      )}
      {pattern === 'circuit' && (
        <View style={styles.patternLayer}>
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <View key={`h-${item}`} style={[styles.circuitLineH, { backgroundColor: patternColor, top: `${item * 16 + 7}%`, left: `${item % 2 === 0 ? 4 : 22}%` }]} />
          ))}
          {[0, 1, 2, 3, 4].map((item) => (
            <View key={`v-${item}`} style={[styles.circuitLineV, { backgroundColor: patternColor, left: `${item * 18 + 10}%`, top: `${item % 2 === 0 ? 10 : 32}%` }]} />
          ))}
          {[0, 1, 2, 3, 4, 5, 6].map((item) => (
            <View key={`n-${item}`} style={[styles.circuitNode, { borderColor: patternColor, left: `${item * 13 + 8}%`, top: `${(item % 4) * 19 + 10}%` }]} />
          ))}
        </View>
      )}
    </View>
  );
}

function WebOperatorShell({
  children,
  pathname,
}: {
  children: React.ReactNode;
  pathname: string;
}) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const [showCustomizer, setShowCustomizer] = useState(false);
  const [accent, setAccent] = useState('#f43f5e');
  const [pattern, setPattern] = useState<'triangle' | 'hex' | 'circuit'>('circuit');
  const [glassOpacity, setGlassOpacity] = useState(88);
  const [blur, setBlur] = useState(15);
  const [themeKey, setThemeKey] = useState<ShellThemeKey>('space');
  const [density, setDensity] = useState<ShellDensityKey>('compact');
  const [cardGlow, setCardGlow] = useState(false);
  const [pipelineTrack, setPipelineTrack] = useState(true);
  const [animatedDots, setAnimatedDots] = useState(false);
  const activeTab = getActiveOperatorTab(pathname);
  const theme = SHELL_THEMES[themeKey];

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const body = (globalThis as any).document?.body;
    if (!body) return;

    if (showCustomizer) body.setAttribute('data-sentinel-echo-customizer', 'open');
    else body.removeAttribute('data-sentinel-echo-customizer');
    globalThis.dispatchEvent?.(new Event('sentinel-echo-customizer-change'));

    return () => {
      body.removeAttribute('data-sentinel-echo-customizer');
      globalThis.dispatchEvent?.(new Event('sentinel-echo-customizer-change'));
    };
  }, [showCustomizer]);

  return (
    <View style={[styles.webShellRoot, { backgroundColor: theme.bg }]}>
      <WebShellBackground accent={accent} pattern={pattern} backgroundColor={theme.bg} />

      <View style={[styles.webHeader, { borderBottomColor: hexToRgba(theme.border, 0.84), backgroundColor: hexToRgba(theme.header, 0.86) }]}>
        <View style={[styles.webHeaderBrand, { borderRightColor: hexToRgba(theme.border, 0.84) }]}>
          <View style={[styles.webLogo, { backgroundColor: hexToRgba(accent, 0.18), borderColor: hexToRgba(accent, 0.46) }]}>
            <Ionicons name="pulse" size={16} color={accent} />
          </View>
        </View>

        {pipelineTrack ? (
          <View style={styles.webPipeline}>
            {['Discord', 'Parse', 'Risk', 'Execute'].map((label, index) => (
              <React.Fragment key={label}>
                <View style={styles.webPipelineStage}>
                  <View style={[styles.webPipelineIcon, { backgroundColor: hexToRgba(index === 0 ? accent : '#68779b', index === 0 ? 0.18 : 0.1) }]}>
                    <Ionicons
                      name={(index === 0 ? 'logo-discord' : index === 1 ? 'filter-outline' : index === 2 ? 'shield-checkmark-outline' : 'flash-outline') as any}
                      size={13}
                      color={index === 0 ? accent : '#68779b'}
                    />
                  </View>
                  <Text numberOfLines={1} style={[styles.webPipelineLabel, { color: index === 0 ? theme.text : theme.muted }]}>{label}</Text>
                </View>
                {index < 3 ? <Ionicons name="chevron-forward" size={13} color="#68779b" /> : null}
              </React.Fragment>
            ))}
          </View>
        ) : (
          <View style={styles.webHeaderSpacer} />
        )}

        <View style={styles.webHeaderActions}>
          <View style={[styles.discordPill, { borderColor: hexToRgba(accent, 0.36), backgroundColor: hexToRgba(accent, 0.15) }]}>
            <View style={[styles.statusDot, animatedDots && styles.statusDotAnimated, { backgroundColor: '#68779b', borderColor: hexToRgba(accent, 0.34) }]} />
            <Text style={[styles.discordPillText, { color: accent }]}>Discord</Text>
          </View>
          <View style={styles.autoTradePill}>
            <Text style={styles.autoTradeText}>Auto trading</Text>
            <View style={styles.miniSwitchTrack}>
              <View style={styles.miniSwitchThumb} />
            </View>
          </View>
          <TouchableOpacity style={styles.headerIconButton} onPress={() => Alert.alert('Notifications', 'No new notifications.')} accessibilityRole="button" accessibilityLabel="Notifications">
            <Ionicons name="notifications-outline" size={16} color="#aec0e5" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerIconButton} onPress={() => setShowCustomizer(true)} accessibilityRole="button" accessibilityLabel="Customize dashboard">
            <Ionicons name="color-palette-outline" size={17} color={accent} />
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.webBodyRow}>
        <View
          style={[styles.sidebarRail, { borderRightColor: hexToRgba(theme.border, 0.84), backgroundColor: hexToRgba(theme.bg, 0.9) }, expanded && styles.sidebarRailOpen]}
          {...(Platform.OS === 'web'
            ? ({
                onMouseEnter: () => setExpanded(true),
                onMouseLeave: () => setExpanded(false),
              } as any)
            : {})}
        >
          <ScrollView style={styles.sidebarTopRail} showsVerticalScrollIndicator={false}>
            {OPERATOR_TABS.map((tab) => {
              const isActive = activeTab === tab.name;
              const route = getOperatorRoutePath(tab.name);
              return (
                <TouchableOpacity
                  key={tab.name}
                  style={[styles.navRailItem, isActive && { backgroundColor: hexToRgba(accent, 0.16) }]}
                  onPress={() => router.push(route as any)}
                  accessibilityRole="button"
                  accessibilityLabel={OPERATOR_LABELS[tab.name] || tab.label}
                  activeOpacity={0.74}
                >
                  {isActive ? <View style={[styles.navRailActiveBar, { backgroundColor: accent }]} /> : null}
                  <Ionicons name={(isActive ? tab.iconActive : tab.icon) as any} size={17} color={isActive ? accent : '#aec0e5'} style={styles.navRailIcon} />
                  <Text numberOfLines={1} style={[styles.navRailLabel, { color: isActive ? accent : '#aec0e5', opacity: expanded ? 1 : 0 }]}>
                    {OPERATOR_LABELS[tab.name] || tab.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
          <View style={[styles.sidebarFootRail, { borderTopColor: hexToRgba(theme.border, 0.84) }]}>
            <View style={styles.brokerRailStatus}>
              <View style={[styles.statusDot, animatedDots && styles.statusDotAnimated, { backgroundColor: '#f59e0b', borderColor: 'rgba(245, 158, 11, 0.34)' }]} />
              <Text numberOfLines={1} style={[styles.brokerRailLabel, { color: theme.muted, opacity: expanded ? 1 : 0 }]}>
                Discord Setup
              </Text>
            </View>
          </View>
        </View>

        <View
          style={[
            styles.webContentHost,
            {
              backgroundColor: hexToRgba(theme.card, glassOpacity / 100),
              padding: SHELL_DENSITY_PADDING[density],
              borderColor: cardGlow ? hexToRgba(accent, 0.68) : 'transparent',
              shadowColor: cardGlow ? accent : '#000000',
              shadowOpacity: cardGlow ? 0.22 : 0,
              ...(Platform.OS === 'web'
                ? ({ backdropFilter: `blur(${blur}px)`, WebkitBackdropFilter: `blur(${blur}px)` } as any)
                : null),
            },
          ]}
        >
          {children}
        </View>
      </View>

      {showCustomizer ? (
        <Pressable
          style={[styles.customizerScrim, Platform.OS === 'web' ? ({ position: 'fixed' } as any) : null]}
          onPress={() => setShowCustomizer(false)}
          accessibilityRole="button"
          accessibilityLabel="Close customization panel"
        >
          <Pressable
            style={[styles.customizerDrawer, { backgroundColor: theme.bg, borderLeftColor: hexToRgba(theme.border, 0.92) }]}
            onPress={(event: any) => event.stopPropagation?.()}
          >
            <View style={styles.customizerHeader}>
              <View>
                <Text style={[styles.customizerTitle, { color: theme.text }]}>Make it yours</Text>
                <Text style={[styles.customizerSub, { color: theme.muted }]}>All changes are instant and session-scoped.</Text>
                <Text style={[styles.customizerSub, { color: theme.muted }]}>Mix and match to find your setup.</Text>
              </View>
              <TouchableOpacity style={[styles.closeButton, { borderColor: hexToRgba(theme.border, 0.92) }]} onPress={() => setShowCustomizer(false)} accessibilityRole="button">
                <Ionicons name="close" size={20} color={theme.muted} />
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.prefEyebrow}>ACCENT COLOR</Text>
              <View style={styles.swatchGrid}>
                {SHELL_ACCENTS.map((color) => (
                  <TouchableOpacity key={color} style={[styles.swatch, { backgroundColor: color }, accent === color && styles.swatchSelected]} onPress={() => setAccent(color)} accessibilityRole="button" />
                ))}
              </View>

              <Text style={styles.prefEyebrow}>BACKGROUND PATTERN</Text>
              <View style={styles.segmentWrap}>
                {(['triangle', 'hex', 'circuit'] as const).map((key) => (
                  <TouchableOpacity key={key} style={[styles.segmentChoice, pattern === key && { borderColor: accent, backgroundColor: hexToRgba(accent, 0.18) }]} onPress={() => setPattern(key)} accessibilityRole="button">
                    <Text style={[styles.segmentChoiceText, pattern === key && { color: accent }]}>{key === 'triangle' ? 'Triangle' : key === 'hex' ? 'Hex' : 'Circuit'}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.prefSlider}>
                <View style={styles.prefSliderHeader}>
                  <Text style={[styles.prefLabel, { color: theme.muted }]}>Opacity</Text>
                  <Text style={[styles.prefValue, { color: theme.muted }]}>{glassOpacity}%</Text>
                </View>
                <RangeInput value={glassOpacity} min={45} max={95} step={1} onChange={setGlassOpacity} accent={accent} />
              </View>

              <View style={styles.prefSlider}>
                <View style={styles.prefSliderHeader}>
                  <Text style={[styles.prefLabel, { color: theme.muted }]}>Blur</Text>
                  <Text style={[styles.prefValue, { color: theme.muted }]}>{blur}px</Text>
                </View>
                <RangeInput value={blur} min={0} max={30} step={1} onChange={setBlur} accent={accent} />
              </View>

              <Text style={styles.prefEyebrow}>BASE THEME</Text>
              <View style={styles.segmentWrap}>
                {(Object.keys(SHELL_THEMES) as ShellThemeKey[]).map((key) => (
                  <TouchableOpacity key={key} style={[styles.segmentChoice, themeKey === key && { borderColor: accent, backgroundColor: hexToRgba(accent, 0.18) }]} onPress={() => setThemeKey(key)} accessibilityRole="button">
                    <Text style={[styles.segmentChoiceText, { color: themeKey === key ? accent : theme.muted }]}>{SHELL_THEMES[key].label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.prefEyebrow}>DENSITY</Text>
              <View style={styles.segmentWrap}>
                {(['compact', 'standard', 'spacious'] as ShellDensityKey[]).map((key) => (
                  <TouchableOpacity key={key} style={[styles.segmentChoice, density === key && { borderColor: accent, backgroundColor: hexToRgba(accent, 0.18) }]} onPress={() => setDensity(key)} accessibilityRole="button">
                    <Text style={[styles.segmentChoiceText, { color: density === key ? accent : theme.muted }]}>{key.charAt(0).toUpperCase() + key.slice(1)}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.prefEyebrow}>OPTIONS</Text>
              <View style={styles.toggleList}>
                {[
                  { label: 'Card border glow', value: cardGlow, onPress: () => setCardGlow((next) => !next) },
                  { label: 'Pipeline header track', value: pipelineTrack, onPress: () => setPipelineTrack((next) => !next) },
                  { label: 'Animated status dots', value: animatedDots, onPress: () => setAnimatedDots((next) => !next) },
                ].map((item) => (
                  <TouchableOpacity key={item.label} style={styles.toggleRow} onPress={item.onPress} accessibilityRole="switch" accessibilityState={{ checked: item.value }}>
                    <Text style={[styles.toggleLabel, { color: theme.muted }]}>{item.label}</Text>
                    <View style={[styles.switchTrack, item.value && { backgroundColor: '#25d0a4' }]}>
                      <View style={[styles.switchThumb, item.value && styles.switchThumbOn]} />
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      ) : null}
    </View>
  );
}

export default function RootLayout() {
  const pathname = usePathname();
  const [customizerOpen, setCustomizerOpen] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const updateCustomizerState = () => {
      const body = (globalThis as any).document?.body;
      setCustomizerOpen(body?.getAttribute('data-sentinel-echo-customizer') === 'open');
    };

    updateCustomizerState();
    globalThis.addEventListener?.('sentinel-echo-customizer-change', updateCustomizerState);

    return () => {
      globalThis.removeEventListener?.('sentinel-echo-customizer-change', updateCustomizerState);
    };
  }, []);

  const activeTab = getActiveOperatorTab(pathname);
  const showTabs = Platform.OS !== 'web' && shouldShowOperatorTabs(pathname) && !customizerOpen;
  const useWebShell = Platform.OS === 'web' && shouldShowOperatorTabs(pathname) && activeTab !== 'index';

  const stack = (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: useWebShell ? 'transparent' : '#050416' },
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
  );

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <View style={styles.root}>
        {useWebShell ? <WebOperatorShell pathname={pathname}>{stack}</WebOperatorShell> : stack}
        {showTabs && <BottomTabBar />}
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#050416',
  },
  tabBar: {
    backgroundColor: 'rgba(8, 6, 24, 0.96)',
    borderTopWidth: 1,
    borderTopColor: 'rgba(244, 63, 94, 0.28)',
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
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  tabItemActive: {
    backgroundColor: 'rgba(244, 63, 94, 0.13)',
  },
  tabIconWrap: {
    width: 38,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabIconWrapActive: {
    backgroundColor: 'rgba(244, 63, 94, 0.17)',
  },
  tabLabel: {
    fontSize: 10,
    color: '#68779b',
    fontWeight: '700',
  },
  tabLabelActive: {
    color: '#fb7185',
  },
  webShellRoot: {
    flex: 1,
    minHeight: Platform.OS === 'web' ? ('100vh' as any) : undefined,
    backgroundColor: '#050416',
    overflow: 'hidden',
    position: 'relative',
  },
  webBgCanvas: {
    backgroundColor: '#050416',
  },
  patternLayer: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.72,
  },
  triangleMark: {
    position: 'absolute',
    width: 0,
    height: 0,
    borderLeftWidth: 10,
    borderRightWidth: 10,
    borderBottomWidth: 18,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    transform: [{ rotate: '20deg' }],
  },
  hexMark: {
    position: 'absolute',
    width: 54,
    height: 54,
    borderWidth: 1,
    borderRadius: 8,
    transform: [{ rotate: '45deg' }],
  },
  circuitLineH: {
    position: 'absolute',
    width: '56%',
    height: 1,
  },
  circuitLineV: {
    position: 'absolute',
    width: 1,
    height: '32%',
  },
  circuitNode: {
    position: 'absolute',
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 1,
  },
  webHeader: {
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    zIndex: 20,
    position: 'relative',
  },
  webHeaderBrand: {
    width: 62,
    height: '100%',
    borderRightWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  webLogo: {
    width: 32,
    height: 32,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  webPipeline: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 18,
    overflow: 'hidden',
  },
  webPipelineStage: {
    minWidth: 92,
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  webPipelineIcon: {
    width: 20,
    height: 20,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  webPipelineLabel: {
    minWidth: 0,
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.4,
  },
  webHeaderSpacer: {
    flex: 1,
    minWidth: 0,
  },
  webHeaderActions: {
    height: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 8,
    paddingRight: 16,
    flexShrink: 0,
  },
  discordPill: {
    minHeight: 30,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 11,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  statusDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
  },
  statusDotAnimated: {
    width: 13,
    height: 13,
    borderRadius: 7,
    borderWidth: 3,
  },
  discordPillText: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.4,
  },
  autoTradePill: {
    minHeight: 30,
    borderWidth: 1,
    borderColor: 'rgba(104, 119, 155, 0.34)',
    borderRadius: 999,
    paddingHorizontal: 11,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(10, 12, 32, 0.68)',
  },
  autoTradeText: {
    color: '#aec0e5',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  miniSwitchTrack: {
    width: 32,
    height: 18,
    borderRadius: 999,
    padding: 3,
    backgroundColor: 'rgba(37, 208, 164, 0.9)',
  },
  miniSwitchThumb: {
    width: 12,
    height: 12,
    borderRadius: 999,
    backgroundColor: '#ffffff',
    transform: [{ translateX: 14 }],
  },
  headerIconButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(104, 119, 155, 0.36)',
    backgroundColor: 'rgba(10, 12, 32, 0.74)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  webBodyRow: {
    flex: 1,
    minHeight: 0,
    flexDirection: 'row',
    overflow: 'hidden',
    position: 'relative',
    zIndex: 1,
  },
  sidebarRail: {
    width: 62,
    height: '100%',
    flexShrink: 0,
    borderRightWidth: 1,
    borderRightColor: 'rgba(41, 33, 58, 0.84)',
    backgroundColor: 'rgba(5, 4, 22, 0.9)',
    overflow: 'hidden',
    zIndex: 12,
  },
  sidebarRailOpen: {
    width: 218,
  },
  sidebarTopRail: {
    flex: 1,
    paddingTop: 10,
  },
  navRailItem: {
    minHeight: 42,
    paddingLeft: 18,
    paddingRight: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
    position: 'relative',
  },
  navRailActiveBar: {
    position: 'absolute',
    left: 0,
    top: 6,
    bottom: 6,
    width: 3,
    borderTopRightRadius: 3,
    borderBottomRightRadius: 3,
  },
  navRailIcon: {
    width: 20,
    textAlign: 'center',
    flexShrink: 0,
  },
  navRailLabel: {
    flex: 1,
    minWidth: 0,
    fontSize: 13,
    fontWeight: '800',
  },
  sidebarFootRail: {
    borderTopWidth: 1,
    borderTopColor: 'rgba(41, 33, 58, 0.84)',
    paddingVertical: 10,
  },
  brokerRailStatus: {
    minHeight: 34,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  brokerRailLabel: {
    flex: 1,
    minWidth: 0,
    color: '#68779b',
    fontSize: 12,
    fontWeight: '800',
  },
  webContentHost: {
    flex: 1,
    minWidth: 0,
    minHeight: 0,
    overflow: 'hidden',
    borderLeftWidth: 0,
    position: 'relative',
  },
  customizerScrim: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 1000,
    alignItems: 'flex-end',
    backgroundColor: 'rgba(0, 0, 0, 0.16)',
  },
  customizerDrawer: {
    width: '100%',
    maxWidth: 430,
    height: '100%',
    borderLeftWidth: 1,
    borderLeftColor: 'rgba(104, 119, 155, 0.3)',
    backgroundColor: '#050416',
    padding: 20,
    overflow: 'hidden',
    gap: 16,
  },
  customizerHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  customizerTitle: {
    color: '#edf3ff',
    fontSize: 22,
    fontWeight: '900',
  },
  customizerSub: {
    marginTop: 4,
    color: '#aec0e5',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  closeButton: {
    width: 40,
    height: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(104, 119, 155, 0.36)',
    backgroundColor: 'rgba(104, 119, 155, 0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  prefEyebrow: {
    marginTop: 20,
    marginBottom: 12,
    color: '#68779b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2.8,
  },
  swatchGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  swatch: {
    width: 42,
    height: 42,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  swatchSelected: {
    borderColor: '#ffffff',
  },
  segmentWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  segmentChoice: {
    minHeight: 48,
    flex: 1,
    minWidth: 112,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(104, 119, 155, 0.28)',
    backgroundColor: 'rgba(10, 12, 32, 0.7)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  segmentChoiceText: {
    color: '#aec0e5',
    fontSize: 14,
    fontWeight: '900',
  },
  prefSlider: {
    marginTop: 16,
    gap: 9,
  },
  prefSliderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  prefLabel: {
    color: '#aec0e5',
    fontSize: 14,
    fontWeight: '800',
  },
  prefValue: {
    color: '#aec0e5',
    fontSize: 14,
    fontWeight: '900',
  },
  toggleList: {
    gap: 10,
    paddingBottom: 26,
  },
  toggleRow: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  toggleLabel: {
    flex: 1,
    minWidth: 0,
    fontSize: 14,
    fontWeight: '800',
  },
  switchTrack: {
    width: 54,
    height: 30,
    borderRadius: 999,
    padding: 4,
    backgroundColor: 'rgba(104, 119, 155, 0.26)',
    justifyContent: 'center',
  },
  switchThumb: {
    width: 22,
    height: 22,
    borderRadius: 999,
    backgroundColor: '#ffffff',
  },
  switchThumbOn: {
    transform: [{ translateX: 24 }],
  },
});
