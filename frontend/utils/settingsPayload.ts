export interface PremiumBufferSettingsPayload {
  premium_buffer_enabled: boolean;
  premium_buffer_amount: number;
}

export function buildPremiumBufferSettingsParams(
  settings: PremiumBufferSettingsPayload,
): PremiumBufferSettingsPayload {
  return {
    premium_buffer_enabled: Boolean(settings.premium_buffer_enabled),
    premium_buffer_amount: Number(settings.premium_buffer_amount),
  };
}
