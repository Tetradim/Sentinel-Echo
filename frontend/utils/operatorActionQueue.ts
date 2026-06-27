import { DashboardReadiness, ReadinessState } from './dashboardReadiness';

export type OperatorActionTone = 'live' | 'attention' | 'blocked';

export type OperatorActionTarget =
  | '/broker-config'
  | '/discord-settings'
  | '/risk-settings'
  | '/trading-settings'
  | '/strike-selection'
  | '/trades'
  | '/profiles';

export interface OperatorAction {
  id: string;
  label: string;
  detail: string;
  target: OperatorActionTarget;
  tone: OperatorActionTone;
  icon: string;
}

const ISSUE_WEIGHT: Record<ReadinessState, number> = {
  blocked: 0,
  attention: 1,
  ready: 2,
};

const READY_ACTIONS: OperatorAction[] = [
  {
    id: 'scan-strikes',
    label: 'Scan Strikes',
    detail: 'Compare liquid contracts before the next alert arrives.',
    target: '/strike-selection',
    tone: 'live',
    icon: 'trending-up-outline',
  },
  {
    id: 'review-trades',
    label: 'Review Trades',
    detail: 'Audit recent fills, simulation tags, and open outcomes.',
    target: '/trades',
    tone: 'live',
    icon: 'receipt-outline',
  },
  {
    id: 'tune-profiles',
    label: 'Tune Profiles',
    detail: 'Check account routing before switching broker profiles.',
    target: '/profiles',
    tone: 'live',
    icon: 'people-outline',
  },
];

export function buildOperatorActionQueue(readiness: DashboardReadiness): OperatorAction[] {
  const issueActions = readiness.items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.state !== 'ready' && item.actionLabel && item.actionTarget)
    .sort((a, b) => ISSUE_WEIGHT[a.item.state] - ISSUE_WEIGHT[b.item.state] || a.index - b.index)
    .map(({ item }) => ({
      id: item.id,
      label: item.actionLabel || item.label,
      detail: item.detail,
      target: item.actionTarget as OperatorActionTarget,
      tone: item.state as OperatorActionTone,
      icon: item.icon,
    }));

  return (issueActions.length > 0 ? issueActions : READY_ACTIONS).slice(0, 3);
}
