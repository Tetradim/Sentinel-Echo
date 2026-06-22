export type ProfileBooleanLike = boolean | string | number | null | undefined;

export interface BrokerSettingsData {
  broker_id: string;
  enabled: ProfileBooleanLike;
  auto_trading_enabled: ProfileBooleanLike;
  alerts_only: ProfileBooleanLike;
  premium_buffer_enabled: ProfileBooleanLike;
  take_profit_enabled: ProfileBooleanLike;
  take_profit_percentage: number;
  bracket_order_enabled: ProfileBooleanLike;
  stop_loss_enabled: ProfileBooleanLike;
  stop_loss_percentage: number;
  trailing_stop_enabled: ProfileBooleanLike;
  trailing_stop_percent: number;
  averaging_down_enabled: ProfileBooleanLike;
  auto_shutdown_enabled: ProfileBooleanLike;
  max_consecutive_losses: number;
}

export interface Broker {
  id: string;
  name: string;
  description: string;
}

export interface Profile {
  id: string;
  name: string;
  description: string;
  active_brokers: string[];
  created_at: string;
  is_active: boolean;
}
