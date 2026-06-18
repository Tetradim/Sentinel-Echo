export type OperatorRouteName =
  | 'index'
  | 'alerts'
  | 'trades'
  | 'positions'
  | 'operator-lab'
  | 'strike-selection'
  | 'trading-settings'
  | 'risk-settings'
  | 'discord-settings'
  | 'broker-config'
  | 'profiles'
  | 'settings';

export interface OperatorTab {
  name: OperatorRouteName;
  label: string;
  icon: string;
  iconActive: string;
}

export const OPERATOR_TABS: OperatorTab[] = [
  { name: 'index', label: 'Dashboard', icon: 'pulse-outline', iconActive: 'pulse' },
  { name: 'alerts', label: 'Alerts', icon: 'notifications-outline', iconActive: 'notifications' },
  { name: 'trades', label: 'Trades', icon: 'receipt-outline', iconActive: 'receipt' },
  { name: 'positions', label: 'Positions', icon: 'briefcase-outline', iconActive: 'briefcase' },
  { name: 'operator-lab', label: 'Lab', icon: 'flask-outline', iconActive: 'flask' },
  { name: 'strike-selection', label: 'Strikes', icon: 'trending-up-outline', iconActive: 'trending-up' },
  { name: 'trading-settings', label: 'Trading', icon: 'options-outline', iconActive: 'options' },
  { name: 'risk-settings', label: 'Risk', icon: 'shield-outline', iconActive: 'shield' },
  { name: 'discord-settings', label: 'Discord', icon: 'chatbubbles-outline', iconActive: 'chatbubbles' },
  { name: 'broker-config', label: 'Broker', icon: 'key-outline', iconActive: 'key' },
  { name: 'profiles', label: 'Profiles', icon: 'people-outline', iconActive: 'people' },
  { name: 'settings', label: 'Settings', icon: 'settings-outline', iconActive: 'settings' },
];

const OPERATOR_TAB_NAMES = new Set(OPERATOR_TABS.map((tab) => tab.name));

export function getOperatorRoutePath(name: OperatorRouteName): string {
  return name === 'index' ? '/' : `/${name}`;
}

export function getActiveOperatorTab(pathname: string): OperatorRouteName | null {
  const normalized = pathname === '/' ? 'index' : pathname.replace(/^\/+/, '').split('/')[0];
  return OPERATOR_TAB_NAMES.has(normalized as OperatorRouteName)
    ? normalized as OperatorRouteName
    : null;
}

export function shouldShowOperatorTabs(pathname: string): boolean {
  return getActiveOperatorTab(pathname) !== null;
}
