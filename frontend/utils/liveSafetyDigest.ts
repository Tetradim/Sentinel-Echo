import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export type LiveSafetyTone = 'live' | 'attention' | 'blocked' | 'idle';

export interface LiveReadinessIssue {
  code: string;
  summary: string;
}

export interface LiveReadinessPayload {
  ready_for_live?: BooleanLike;
  blocking_issues?: LiveReadinessIssue[];
  checks?: {
    runtime?: {
      live_trading_armed?: BooleanLike;
      live_trading_armed_until?: string;
      shutdown_triggered?: BooleanLike;
    };
    trading?: {
      simulation_mode?: BooleanLike;
      auto_trading_enabled?: BooleanLike;
    };
    broker?: {
      active_broker?: string;
      connected?: BooleanLike;
    };
    source_policy?: {
      blocked_sources?: {
        key?: string;
        name?: string;
        reasons?: string[];
      }[];
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

function formatSourceBlockReason(reason: string): string {
  if (reason === 'paper_only') return 'is paper-only';
  if (reason === 'manual_confirm_required') return 'requires manual confirmation';
  if (reason === 'disabled') return 'is disabled';
  return reason.replace(/_/g, ' ');
}

function formatSourcePolicyBlockers(readiness: LiveReadinessPayload | null | undefined): string | null {
  const blockedSources = readiness?.checks?.source_policy?.blocked_sources || [];
  const details = blockedSources
    .map((source) => {
      const label = String(source.name || source.key || '').trim();
      const reasons = (source.reasons || [])
        .map((reason) => formatSourceBlockReason(String(reason || '').trim()))
        .filter(Boolean);
      if (!label || reasons.length <= 0) return '';
      return `${label} ${reasons.join(' and ')}`;
    })
    .filter(Boolean);

  if (details.length <= 0) return null;
  return `No live source: ${details.join('; ')}.`;
}

export function summarizeLiveSafety(readiness: LiveReadinessPayload | null | undefined): LiveSafetyDigest {
  const blockers = readiness?.blocking_issues || [];
  const runtime = readiness?.checks?.runtime || {};
  const trading = readiness?.checks?.trading || {};
  const broker = readiness?.checks?.broker || {};
  const isArmed = parseBooleanFlag(runtime.live_trading_armed);
  const canArm = parseBooleanFlag(readiness?.ready_for_live) && !isArmed;

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
    const firstBlocker = blockers[0];
    const sourcePolicyDetail = firstBlocker?.code === 'no_live_source'
      ? formatSourcePolicyBlockers(readiness)
      : null;
    return {
      title: 'Live Blocked',
      detail: sourcePolicyDetail || firstBlocker?.summary || 'Readiness checks are blocking live arming.',
      tone: 'blocked',
      blockerCount: blockers.length,
      canArm: false,
      isArmed: false,
      armedUntilLabel: 'Not armed',
      primaryAction: 'review',
    };
  }

  if (canArm) {
    const simulationMode = parseBooleanFlag(trading.simulation_mode);
    return {
      title: 'Ready To Arm',
      detail: `${String(broker.active_broker || 'broker').toUpperCase()} is ready; simulation is ${simulationMode ? 'on' : 'off'}.`,
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
