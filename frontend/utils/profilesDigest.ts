export type ProfilesDigestTone = 'live' | 'attention' | 'idle';

export interface DigestProfile {
  id: string;
  name?: string | null;
  is_active?: boolean | null;
}

export interface DigestBrokerSettings {
  enabled?: boolean | null;
  auto_trading_enabled?: boolean | null;
  alerts_only?: boolean | null;
  take_profit_enabled?: boolean | null;
  stop_loss_enabled?: boolean | null;
  auto_shutdown_enabled?: boolean | null;
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

function isGuarded(settings: DigestBrokerSettings): boolean {
  if (!settings.enabled) return false;
  if (settings.alerts_only) return true;
  return Boolean(settings.take_profit_enabled && settings.stop_loss_enabled && settings.auto_shutdown_enabled);
}

export function summarizeProfiles(
  profiles: DigestProfile[],
  allBrokerSettings: ProfileSettingsMap
): ProfilesDigest {
  const activeProfiles = profiles.filter((profile) => Boolean(profile.is_active));
  const activeProfile = activeProfiles[0];
  const activeSettings = activeProfile ? Object.values(allBrokerSettings[activeProfile.id] || {}) : [];
  const enabledSettings = activeSettings.filter((settings): settings is DigestBrokerSettings => Boolean(settings?.enabled));
  const autoTradingSettings = enabledSettings.filter((settings) => Boolean(settings.auto_trading_enabled));
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
