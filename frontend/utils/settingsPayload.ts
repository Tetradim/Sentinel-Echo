export interface PremiumBufferSettingsPayload {
  premium_buffer_enabled: boolean;
  premium_buffer_amount: number;
}

export interface PremiumBufferSettingsInput {
  premium_buffer_enabled: boolean | string | number | null | undefined;
  premium_buffer_amount: number | string;
}

function parseBooleanFlag(value: PremiumBufferSettingsInput['premium_buffer_enabled']): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value === 1;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false;
  }
  return false;
}

export function buildPremiumBufferSettingsParams(
  settings: PremiumBufferSettingsInput,
): PremiumBufferSettingsPayload {
  return {
    premium_buffer_enabled: parseBooleanFlag(settings.premium_buffer_enabled),
    premium_buffer_amount: Number(settings.premium_buffer_amount),
  };
}
