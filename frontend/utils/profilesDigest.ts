export type ProfilesDigestTone = 'live' | 'attention' | 'idle';

type BooleanLike = boolean | string | number | null | undefined;

export interface DigestProfile {
  id: string;
  name?: string | null;
  is_active?: BooleanLike;
}

export interface DigestBrokerSettings {
  enabled?: BooleanLike;
  auto_trading_enabled?: BooleanLike;
  alerts_only?: BooleanLike;
  take_profit_enabled?: BooleanLike;
  stop_loss_enabled?: BooleanLike;
  auto_shutdown_enabled?: BooleanLike;
}

export interface ProfilesDigestStatus {
  title: string;
  detail: string;
  tone: ProfilesDigestTone;
}

export interface ProfilesDigestWarning {
  title: string;
  detail: string;
}

export interface ProfilesDigest {
  primaryStatus: ProfilesDigestStatus;
  warningItems: ProfilesDigestWarning[];
  totalProfiles: number;
  activeProfileName: string;
  enabledBrokers: number;
  autoTradingBrokers: number;
  guardedBrokers: number;
  profileCoveragePercent: number;
}

type ProfileSettingsMap = Record<string, Record<string, DigestBrokerSettings | undefined>>;

function profileName(profile: DigestProfile | undefined): string {
  return profile?.name?.trim() || 'None';
}

function parseBooleanFlag(value: BooleanLike, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (value === 1) return true;
    if (value === 0) return false;
    return fallback;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false;
  }
  return fallback;
}

function isGuarded(settings: DigestBrokerSettings): boolean {
  if (!parseBooleanFlag(settings.enabled)) return false;
  if (parseBooleanFlag(settings.alerts_only)) return true;
  return (
    parseBooleanFlag(settings.take_profit_enabled) &&
    parseBooleanFlag(settings.stop_loss_enabled) &&
    parseBooleanFlag(settings.auto_shutdown_enabled)
  );
}

export function summarizeProfiles(
  profiles: DigestProfile[],
  allBrokerSettings: ProfileSettingsMap
): ProfilesDigest {
  const activeProfiles = profiles.filter((profile) => parseBooleanFlag(profile.is_active));
  const activeProfile = activeProfiles[0];
  const activeSettings = activeProfile ? Object.values(allBrokerSettings[activeProfile.id] || {}) : [];
  const enabledSettings = activeSettings.filter(
    (settings): settings is DigestBrokerSettings => parseBooleanFlag(settings?.enabled)
  );
  const autoTradingSettings = enabledSettings.filter((settings) => parseBooleanFlag(settings.auto_trading_enabled));
  const guardedBrokers = enabledSettings.filter(isGuarded).length;
  const profileCoveragePercent = enabledSettings.length === 0
    ? 0
    : Math.round((guardedBrokers / enabledSettings.length) * 100);

  const warnings: ProfilesDigestWarning[] = [];

  if (profiles.length === 0) {
    return {
      primaryStatus: {
        title: 'No Profiles',
        detail: 'Create a trading profile before broker behavior can be tuned.',
        tone: 'idle',
      },
      warningItems: [],
      totalProfiles: 0,
      activeProfileName: 'None',
      enabledBrokers: 0,
      autoTradingBrokers: 0,
      guardedBrokers: 0,
      profileCoveragePercent: 0,
    };
  }

  if (!activeProfile) {
    warnings.push({
      title: 'No active profile',
      detail: 'Activate one profile to define the current broker policy.',
    });
  }

  if (activeProfiles.length > 1) {
    warnings.push({
      title: 'Multiple active profiles',
      detail: `${activeProfiles.length} profiles are marked active.`,
    });
  }

  if (activeProfile && enabledSettings.length === 0) {
    warnings.push({
      title: 'No brokers enabled',
      detail: `${profileName(activeProfile)} has no enabled broker routes.`,
    });
  }

  if (autoTradingSettings.length > 0 && guardedBrokers < enabledSettings.length) {
    warnings.push({
      title: 'Auto broker missing exits',
      detail: 'At least one auto-trading broker is missing exits or shutdown controls.',
    });
  }

  let primaryStatus: ProfilesDigestStatus = {
    title: 'Profile Ready',
    detail: `${profileName(activeProfile)} has ${enabledSettings.length} enabled broker${enabledSettings.length === 1 ? '' : 's'} configured.`,
    tone: 'live',
  };

  if (!activeProfile) {
    primaryStatus = {
      title: 'Activate Profile',
      detail: 'No profile is currently active.',
      tone: 'attention',
    };
  } else if (activeProfiles.length > 1) {
    primaryStatus = {
      title: 'Profile Conflict',
      detail: `${activeProfiles.length} profiles are marked active.`,
      tone: 'attention',
    };
  } else if (enabledSettings.length === 0) {
    primaryStatus = {
      title: 'No Active Brokers',
      detail: `${profileName(activeProfile)} needs at least one enabled broker route.`,
      tone: 'attention',
    };
  } else if (autoTradingSettings.length > 0 && guardedBrokers < enabledSettings.length) {
    primaryStatus = {
      title: 'Guardrail Review',
      detail: `${enabledSettings.length - guardedBrokers} enabled broker${enabledSettings.length - guardedBrokers === 1 ? '' : 's'} need exits or shutdowns.`,
      tone: 'attention',
    };
  }

  return {
    primaryStatus,
    warningItems: warnings,
    totalProfiles: profiles.length,
    activeProfileName: profileName(activeProfile),
    enabledBrokers: enabledSettings.length,
    autoTradingBrokers: autoTradingSettings.length,
    guardedBrokers,
    profileCoveragePercent,
  };
}
