import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export interface PremiumBufferSettingsPayload {
  premium_buffer_enabled: boolean;
  premium_buffer_amount: number;
}

export interface PremiumBufferSettingsInput {
  premium_buffer_enabled: BooleanLike;
  premium_buffer_amount: number | string;
}

export function buildPremiumBufferSettingsParams(
  settings: PremiumBufferSettingsInput,
): PremiumBufferSettingsPayload {
  return {
    premium_buffer_enabled: parseBooleanFlag(settings.premium_buffer_enabled),
    premium_buffer_amount: Number(settings.premium_buffer_amount),
  };
}
