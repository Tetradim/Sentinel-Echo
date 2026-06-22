export type LiveSafetyTone = 'live' | 'attention' | 'blocked' | 'idle';

export interface LiveReadinessIssue {
  code: string;
  summary: string;
}

export interface LiveReadinessPayload {
  ready_for_live?: boolean;
  blocking_issues?: LiveReadinessIssue[];
  checks?: {
    runtime?: {
      live_trading_armed?: boolean;
      live_trading_armed_until?: string;
      shutdown_triggered?: boolean;
    };
    trading?: {
      simulation_mode?: boolean;
      auto_trading_enabled?: boolean;
    };
    broker?: {
      active_broker?: string;
      connected?: boolean;
    };
  };
}

export interface LiveSafetyDigest {
  title: string;
  detail: string;
  tone: LiveSafetyTone;
  blockerCount: number;
  canArm: boolean;
  isArmed: boolean;
  armedUntilLabel: string;
  primaryAction: 'arm' | 'disarm' | 'review';
}

function formatArmedUntil(value: string | undefined): string {
  if (!value) return 'Not armed';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Invalid expiry';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function summarizeLiveSafety(readiness: LiveReadinessPayload | null | undefined): LiveSafetyDigest {
  const blockers = readiness?.blocking_issues || [];
  const runtime = readiness?.checks?.runtime || {};
  const trading = readiness?.checks?.trading || {};
  const broker = readiness?.checks?.broker || {};
  const isArmed = Boolean(runtime.live_trading_armed);
  const canArm = Boolean(readiness?.ready_for_live) && !isArmed;

  if (isArmed) {
    return {
      title: 'Live Armed',
      detail: `Live broker orders are armed until ${formatArmedUntil(runtime.live_trading_armed_until)}.`,
      tone: 'attention',
      blockerCount: blockers.length,
      canArm: false,
      isArmed: true,
      armedUntilLabel: formatArmedUntil(runtime.live_trading_armed_until),
      primaryAction: 'disarm',
    };
  }

  if (blockers.length > 0) {
    return {
      title: 'Live Blocked',
      detail: blockers[0]?.summary || 'Readiness checks are blocking live arming.',
      tone: 'blocked',
      blockerCount: blockers.length,
      canArm: false,
      isArmed: false,
      armedUntilLabel: 'Not armed',
      primaryAction: 'review',
    };
  }

  if (canArm) {
    return {
      title: 'Ready To Arm',
      detail: `${String(broker.active_broker || 'broker').toUpperCase()} is ready; simulation is ${trading.simulation_mode ? 'on' : 'off'}.`,
      tone: 'live',
      blockerCount: 0,
      canArm: true,
      isArmed: false,
      armedUntilLabel: 'Not armed',
      primaryAction: 'arm',
    };
  }

  return {
    title: 'Safety Idle',
    detail: 'Readiness has not been loaded yet.',
    tone: 'idle',
    blockerCount: 0,
    canArm: false,
    isArmed: false,
    armedUntilLabel: 'Not armed',
    primaryAction: 'review',
  };
}
