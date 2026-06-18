export type ReadinessTone = 'live' | 'attention' | 'blocked';

export type ReadinessState = 'ready' | 'attention' | 'blocked';

export type ReadinessActionTarget =
  | '/broker-config'
  | '/discord-settings'
  | '/risk-settings'
  | '/trading-settings';

export interface ReadinessStatus {
  discord_connected?: boolean;
  broker_connected?: boolean;
  auto_trading_enabled?: boolean;
}

export interface DashboardReadinessInput {
  status: ReadinessStatus | null;
  simMode: boolean;
  autoShutdownEnabled: boolean;
  shutdownTriggered: boolean;
  takeProfitEnabled: boolean;
  stopLossEnabled: boolean;
  trailingStopEnabled: boolean;
  premiumBufferEnabled: boolean;
}

export interface ReadinessAction {
  label: string;
  target: ReadinessActionTarget;
}

export interface ReadinessItem {
  id: string;
  label: string;
  detail: string;
  state: ReadinessState;
  icon: string;
  actionLabel?: string;
  actionTarget?: ReadinessActionTarget;
}

export interface DashboardReadiness {
  title: string;
  summary: string;
  tone: ReadinessTone;
  score: number;
  items: ReadinessItem[];
  primaryAction: ReadinessAction;
}

const STATE_WEIGHT: Record<ReadinessState, number> = {
  ready: 1,
  attention: 0.5,
  blocked: 0,
};

function getTone(items: ReadinessItem[]): ReadinessTone {
  if (items.some((item) => item.state === 'blocked')) return 'blocked';
  if (items.some((item) => item.state === 'attention')) return 'attention';
  return 'live';
}

function getScore(items: ReadinessItem[]): number {
  const possible = items.length;
  const ready = items.reduce((total, item) => total + STATE_WEIGHT[item.state], 0);
  return Math.round((ready / possible) * 100);
}

function getTitle(tone: ReadinessTone): string {
  if (tone === 'blocked') return 'Intervention Needed';
  if (tone === 'attention') return 'Needs Review';
  return 'Ready';
}

function getPrimaryAction(items: ReadinessItem[], tone: ReadinessTone): ReadinessAction {
  const firstActionable = items.find(
    (item) => item.state !== 'ready' && item.actionLabel && item.actionTarget
  );

  if (firstActionable?.actionLabel && firstActionable.actionTarget) {
    return {
      label: firstActionable.actionLabel,
      target: firstActionable.actionTarget,
    };
  }

  return {
    label: tone === 'live' ? 'View Trading' : 'Review Trading',
    target: '/trading-settings',
  };
}

function getSummary(
  tone: ReadinessTone,
  items: ReadinessItem[],
  input: DashboardReadinessInput
): string {
  const firstIssue = items.find((item) => item.state !== 'ready');

  if (firstIssue) return firstIssue.detail;
  if (input.simMode) return 'Simulation trading is ready with protections online.';
  return 'Live trading path is ready with protections online.';
}

export function buildDashboardReadiness(input: DashboardReadinessInput): DashboardReadiness {
  const status = input.status;
  const exitGuardsEnabled = input.takeProfitEnabled || input.stopLossEnabled || input.trailingStopEnabled;

  const items: ReadinessItem[] = [
    input.shutdownTriggered
      ? {
          id: 'shutdown',
          label: 'Shutdown',
          detail: 'Loss limits paused automation. Review counters before resuming.',
          state: 'blocked',
          icon: 'warning',
          actionLabel: 'Review Shutdown',
          actionTarget: '/risk-settings',
        }
      : {
          id: 'shutdown',
          label: 'Shutdown',
          detail: input.autoShutdownEnabled
            ? 'Loss-limit shutdown is watching the session.'
            : 'Auto shutdown is off; enable it before unattended trading.',
          state: input.autoShutdownEnabled ? 'ready' : 'attention',
          icon: input.autoShutdownEnabled ? 'power' : 'power-outline',
          actionLabel: 'Tune Risk',
          actionTarget: '/risk-settings',
        },
    status?.broker_connected
      ? {
          id: 'broker',
          label: 'Broker',
          detail: 'Broker route is connected.',
          state: 'ready',
          icon: 'briefcase',
        }
      : {
          id: 'broker',
          label: 'Broker',
          detail: 'Broker is offline or not configured.',
          state: 'blocked',
          icon: 'briefcase-outline',
          actionLabel: 'Configure Broker',
          actionTarget: '/broker-config',
        },
    status?.discord_connected
      ? {
          id: 'discord',
          label: 'Discord',
          detail: 'Discord alerts are connected.',
          state: 'ready',
          icon: 'chatbubbles',
        }
      : {
          id: 'discord',
          label: 'Discord',
          detail: 'Discord alert ingestion is offline.',
          state: 'attention',
          icon: 'chatbubbles-outline',
          actionLabel: 'Open Discord',
          actionTarget: '/discord-settings',
        },
    status?.auto_trading_enabled
      ? {
          id: 'automation',
          label: 'Automation',
          detail: 'Automatic order handling is enabled.',
          state: 'ready',
          icon: 'flash',
        }
      : {
          id: 'automation',
          label: 'Automation',
          detail: 'Auto trading is paused; alerts will not execute automatically.',
          state: 'attention',
          icon: 'flash-outline',
          actionLabel: 'Open Trading',
          actionTarget: '/trading-settings',
        },
    exitGuardsEnabled
      ? {
          id: 'guards',
          label: 'Exit Guards',
          detail: input.premiumBufferEnabled
            ? 'Exit guards and premium buffer are armed.'
            : 'Exit guards are armed; premium buffer is off.',
          state: 'ready',
          icon: input.premiumBufferEnabled ? 'shield-checkmark' : 'shield-half',
        }
      : {
          id: 'guards',
          label: 'Exit Guards',
          detail: 'No take-profit, stop-loss, or trailing stop guard is enabled.',
          state: 'attention',
          icon: 'shield-outline',
          actionLabel: 'Tune Risk',
          actionTarget: '/risk-settings',
        },
  ];

  const tone = getTone(items);

  return {
    title: getTitle(tone),
    summary: getSummary(tone, items, input),
    tone,
    score: getScore(items),
    items,
    primaryAction: getPrimaryAction(items, tone),
  };
}
