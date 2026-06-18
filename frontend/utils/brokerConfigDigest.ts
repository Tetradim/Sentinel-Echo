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

type BrokerConfigMap = Record<string, Record<string, string | null | undefined>>;

function hasValue(value: string | null | undefined): boolean {
  return String(value || '').trim().length > 0;
}

function configsEqual(
  current: Record<string, string | null | undefined> = {},
  saved: Record<string, string | null | undefined> = {}
): boolean {
  const keys = new Set([...Object.keys(current), ...Object.keys(saved)]);
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
  config: Record<string, string | null | undefined> = {}
): number {
  return fields.filter((field) => hasValue(config[field.key])).length;
}

function isBrokerConfigured(
  broker: DigestBroker,
  configs: BrokerConfigMap
): boolean {
  const fields = getFields(broker);
  return fields.length > 0 && configuredFieldCount(fields, configs[broker.id]) === fields.length;
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
    .filter((field) => !hasValue(selectedConfig[field.key]))
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
