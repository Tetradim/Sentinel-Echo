import { parseBooleanFlag, type BooleanLike } from './booleanFlags';

export type BrokerConfigDigestTone = 'live' | 'attention' | 'idle';

export interface DigestConfigField {
  key: string;
  label: string;
}

export interface DigestBroker {
  id: string;
  name?: string | null;
  supports_options?: boolean | null;
  requires_gateway?: boolean | null;
  config_fields?: DigestConfigField[] | null;
}

export interface BrokerConfigDigestStatus {
  title: string;
  detail: string;
  tone: BrokerConfigDigestTone;
}

export interface BrokerConfigDigestWarning {
  title: string;
  detail: string;
}

export interface BrokerConfigDigest {
  primaryStatus: BrokerConfigDigestStatus;
  warningItems: BrokerConfigDigestWarning[];
  selectedBrokerName: string;
  configuredFields: number;
  totalFields: number;
  configuredBrokerCount: number;
  unsavedBrokerCount: number;
  readinessPercent: number;
}

export interface BrokerConnectionResponse {
  connected?: BooleanLike;
  message?: string | null;
}

export interface BrokerConnectionResult {
  connected: boolean;
  title: string;
  message: string;
}

type ConfiguredFieldsMap = Record<string, BooleanLike | null | undefined>;
type BrokerConfigRecord = Record<string, string | ConfiguredFieldsMap | null | undefined> & {
  configured_fields?: ConfiguredFieldsMap | null;
};
type BrokerConfigMap = Record<string, BrokerConfigRecord>;

function hasValue(value: string | null | undefined): boolean {
  return String(value || '').trim().length > 0;
}

function hasConfiguredFieldFlag(
  config: BrokerConfigRecord = {},
  key: string
): boolean {
  const configuredFields = config.configured_fields;
  return Boolean(configuredFields && parseBooleanFlag(configuredFields[key]));
}

function hasConfiguredField(
  config: BrokerConfigRecord = {},
  key: string
): boolean {
  const value = config[key];
  return (typeof value === 'string' && hasValue(value)) || hasConfiguredFieldFlag(config, key);
}

function configsEqual(
  current: BrokerConfigRecord = {},
  saved: BrokerConfigRecord = {}
): boolean {
  const keys = new Set([
    ...Object.keys(current).filter((key) => key !== 'configured_fields'),
    ...Object.keys(saved).filter((key) => key !== 'configured_fields'),
  ]);
  for (const key of keys) {
    if (String(current[key] || '') !== String(saved[key] || '')) return false;
  }
  return true;
}

function getBrokerName(broker: DigestBroker | undefined): string {
  return broker?.name?.trim() || broker?.id || 'None';
}

function getFields(broker: DigestBroker | undefined): DigestConfigField[] {
  return broker?.config_fields || [];
}

function configuredFieldCount(
  fields: DigestConfigField[],
  config: BrokerConfigRecord = {}
): number {
  return fields.filter((field) => hasConfiguredField(config, field.key)).length;
}

function isBrokerConfigured(
  broker: DigestBroker,
  configs: BrokerConfigMap
): boolean {
  const fields = getFields(broker);
  return fields.length > 0 && configuredFieldCount(fields, configs[broker.id]) === fields.length;
}

export function getBrokerConnectionResult(response?: BrokerConnectionResponse | null): BrokerConnectionResult {
  const connected = parseBooleanFlag(response?.connected);
  return {
    connected,
    title: connected ? 'Connected!' : 'Not Connected',
    message: String(response?.message || (connected ? 'Broker connection verified.' : 'Broker connection failed.')),
  };
}

export function summarizeBrokerConfig(
  brokers: DigestBroker[],
  activeBrokerId: string | null | undefined,
  selectedBrokerId: string | null | undefined,
  brokerConfigs: BrokerConfigMap,
  savedConfigs: BrokerConfigMap
): BrokerConfigDigest {
  if (brokers.length === 0) {
    return {
      primaryStatus: {
        title: 'No Brokers',
        detail: 'No broker integrations are available from the backend.',
        tone: 'idle',
      },
      warningItems: [],
      selectedBrokerName: 'None',
      configuredFields: 0,
      totalFields: 0,
      configuredBrokerCount: 0,
      unsavedBrokerCount: 0,
      readinessPercent: 0,
    };
  }

  const selectedBroker =
    brokers.find((broker) => broker.id === selectedBrokerId) ||
    brokers.find((broker) => broker.id === activeBrokerId) ||
    brokers[0];
  const selectedFields = getFields(selectedBroker);
  const selectedConfig = brokerConfigs[selectedBroker.id] || {};
  const configuredFields = configuredFieldCount(selectedFields, selectedConfig);
  const totalFields = selectedFields.length;
  const readinessPercent = totalFields === 0 ? 100 : Math.round((configuredFields / totalFields) * 100);
  const configuredBrokerCount = brokers.filter((broker) => isBrokerConfigured(broker, brokerConfigs)).length;
  const unsavedBrokerCount = brokers.filter((broker) => (
    !configsEqual(brokerConfigs[broker.id], savedConfigs[broker.id])
  )).length;

  const missingWarnings: BrokerConfigDigestWarning[] = selectedFields
    .filter((field) => !hasConfiguredField(selectedConfig, field.key))
    .map((field) => ({
      title: `${field.label} missing`,
      detail: `Add ${field.label.toLowerCase()} before this broker can be used reliably.`,
    }));

  const stateWarnings: BrokerConfigDigestWarning[] = [];
  if (unsavedBrokerCount > 0 && missingWarnings.length === 0) {
    stateWarnings.push({
      title: 'Unsaved broker keys',
      detail: `${unsavedBrokerCount} broker configuration${unsavedBrokerCount === 1 ? ' has' : 's have'} unsaved edits.`,
    });
  }
  if (selectedBroker.id !== activeBrokerId) {
    stateWarnings.push({
      title: 'Selected broker inactive',
      detail: `${getBrokerName(selectedBroker)} is not the active execution route.`,
    });
  }
  if (!selectedBroker.supports_options) {
    stateWarnings.push({
      title: 'Options unsupported',
      detail: `${getBrokerName(selectedBroker)} is not marked as options-capable.`,
    });
  }

  let primaryStatus: BrokerConfigDigestStatus = {
    title: 'Broker Ready',
    detail: `${getBrokerName(selectedBroker)} has all required fields saved.`,
    tone: 'live',
  };

  if (missingWarnings.length > 0) {
    primaryStatus = {
      title: 'Keys Needed',
      detail: `${missingWarnings.length} field${missingWarnings.length === 1 ? '' : 's'} missing for ${getBrokerName(selectedBroker)}.`,
      tone: 'attention',
    };
  } else if (unsavedBrokerCount > 0) {
    primaryStatus = {
      title: 'Unsaved Changes',
      detail: `${unsavedBrokerCount} broker configuration${unsavedBrokerCount === 1 ? ' needs' : 's need'} saving.`,
      tone: 'attention',
    };
  } else if (selectedBroker.id !== activeBrokerId) {
    primaryStatus = {
      title: 'Broker Review',
      detail: `${getBrokerName(selectedBroker)} is configured but not active.`,
      tone: 'attention',
    };
  }

  return {
    primaryStatus,
    warningItems: [...missingWarnings, ...stateWarnings],
    selectedBrokerName: getBrokerName(selectedBroker),
    configuredFields,
    totalFields,
    configuredBrokerCount,
    unsavedBrokerCount,
    readinessPercent,
  };
}
