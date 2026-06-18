export type StrikeOptionType = 'CALL' | 'PUT';
export type StrikeStrategy = 'ATM' | 'OTM' | 'ITM' | 'DELTA' | 'RISK' | 'IV' | 'LIQ';
export type StrikeDigestTone = 'live' | 'attention' | 'idle';

export interface StrikeContract {
  strike: number;
  bid: number;
  ask: number;
  iv: number;
  delta: number;
  theta: number;
  oi: number;
}

export interface StrikeChain {
  underlying: number;
  calls: StrikeContract[];
  puts: StrikeContract[];
}

export interface StrikeDigestStatus {
  title: string;
  detail: string;
  tone: StrikeDigestTone;
}

export interface StrikeDigestWarning {
  title: string;
  detail: string;
}

export interface StrikeComparisonRow {
  strategy: StrikeStrategy;
  strategyName: string;
  strike: number;
  premiumLabel: string;
  deltaLabel: string;
  ivLabel: string;
  spreadLabel: string;
  scoreLabel: string;
}

export interface StrikeSelectionDigest {
  primaryStatus: StrikeDigestStatus;
  warningItems: StrikeDigestWarning[];
  selectedContract: StrikeContract | null;
  selectedStrike: number | null;
  selectedPremiumLabel: string;
  spreadLabel: string;
  deltaLabel: string;
  ivLabel: string;
  moneynessLabel: string;
  liquidityLabel: string;
  contractCount: number;
  comparisonRows: StrikeComparisonRow[];
}

export interface StrikeSelectionInput {
  chain: StrikeChain;
  optionType: StrikeOptionType;
  strategy: StrikeStrategy;
  targetDelta?: number | null;
}

export const STRIKE_STRATEGIES: { id: StrikeStrategy; name: string; detail: string }[] = [
  { id: 'ATM', name: 'At the Money', detail: 'Closest strike to the underlying.' },
  { id: 'OTM', name: 'Momentum OTM', detail: 'Five percent out of the money.' },
  { id: 'ITM', name: 'Safer ITM', detail: 'Ten percent in the money.' },
  { id: 'DELTA', name: 'Target Delta', detail: 'Closest to the selected delta.' },
  { id: 'RISK', name: 'Risk Weighted', detail: 'Balances delta, spread, price, and open interest.' },
  { id: 'IV', name: 'High IV', detail: 'Highest implied volatility.' },
  { id: 'LIQ', name: 'Most Liquid', detail: 'Highest open interest.' },
];

const STRATEGY_NAMES = new Map(STRIKE_STRATEGIES.map((strategy) => [strategy.id, strategy.name]));

function contractsFor(chain: StrikeChain, optionType: StrikeOptionType): StrikeContract[] {
  return optionType === 'CALL' ? chain.calls : chain.puts;
}

function midpoint(contract: StrikeContract | null): number {
  if (!contract) return 0;
  return (contract.bid + contract.ask) / 2;
}

function spread(contract: StrikeContract | null): number {
  if (!contract) return 0;
  return Math.max(0, contract.ask - contract.bid);
}

function spreadPercent(contract: StrikeContract | null): number {
  const mid = midpoint(contract);
  return mid > 0 ? (spread(contract) / mid) * 100 : 0;
}

function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

function formatDelta(value: number): string {
  return value.toFixed(2);
}

function nearestBy(contracts: StrikeContract[], score: (contract: StrikeContract) => number): StrikeContract | null {
  if (contracts.length === 0) return null;
  return contracts.reduce((best, contract) => (score(contract) < score(best) ? contract : best), contracts[0]);
}

function maxBy(contracts: StrikeContract[], score: (contract: StrikeContract) => number): StrikeContract | null {
  if (contracts.length === 0) return null;
  return contracts.reduce((best, contract) => (score(contract) > score(best) ? contract : best), contracts[0]);
}

function targetStrike(chain: StrikeChain, optionType: StrikeOptionType, strategy: 'OTM' | 'ITM'): number {
  const direction = optionType === 'CALL' ? 1 : -1;
  const percent = strategy === 'OTM' ? 0.05 : -0.1;
  return chain.underlying * (1 + direction * percent);
}

function riskScore(contract: StrikeContract, contracts: StrikeContract[]): number {
  const maxOi = Math.max(...contracts.map((candidate) => candidate.oi), 1);
  const maxAsk = Math.max(...contracts.map((candidate) => candidate.ask), 1);
  const deltaScore = 1 - Math.min(Math.abs(Math.abs(contract.delta) - 0.22) / 0.22, 1);
  const liquidityScore = contract.oi / maxOi;
  const spreadScore = 1 - Math.min(spreadPercent(contract) / 20, 1);
  const priceScore = 1 - Math.min(contract.ask / maxAsk, 1);
  return (deltaScore * 50) + (liquidityScore * 25) + (spreadScore * 15) + (priceScore * 10);
}

function selectContract(
  chain: StrikeChain,
  optionType: StrikeOptionType,
  strategy: StrikeStrategy,
  targetDelta = 0.3
): StrikeContract | null {
  const contracts = contractsFor(chain, optionType);

  switch (strategy) {
    case 'ATM':
      return nearestBy(contracts, (contract) => Math.abs(contract.strike - chain.underlying));
    case 'OTM':
      return nearestBy(contracts, (contract) => Math.abs(contract.strike - targetStrike(chain, optionType, 'OTM')));
    case 'ITM':
      return nearestBy(contracts, (contract) => Math.abs(contract.strike - targetStrike(chain, optionType, 'ITM')));
    case 'DELTA':
      return nearestBy(contracts, (contract) => Math.abs(Math.abs(contract.delta) - targetDelta));
    case 'RISK':
      return maxBy(contracts, (contract) => riskScore(contract, contracts));
    case 'IV':
      return maxBy(contracts, (contract) => contract.iv);
    case 'LIQ':
      return maxBy(contracts, (contract) => contract.oi);
  }
}

function moneynessLabel(chain: StrikeChain, optionType: StrikeOptionType, contract: StrikeContract | null): string {
  if (!contract) return '-';
  const distancePercent = ((contract.strike - chain.underlying) / chain.underlying) * 100;
  if (Math.abs(distancePercent) < 0.75) return 'ATM';
  const isOtm = optionType === 'CALL' ? contract.strike > chain.underlying : contract.strike < chain.underlying;
  return `${Math.abs(distancePercent).toFixed(1)}% ${isOtm ? 'OTM' : 'ITM'}`;
}

function warningItems(contract: StrikeContract | null): StrikeDigestWarning[] {
  if (!contract) {
    return [{ title: 'No contracts', detail: 'No options are available for this side of the chain.' }];
  }

  const warnings: StrikeDigestWarning[] = [];
  if (spreadPercent(contract) > 12) {
    warnings.push({
      title: 'Wide bid/ask spread',
      detail: `${spreadPercent(contract).toFixed(1)}% spread can create poor fills.`,
    });
  }
  if (contract.oi < 1000) {
    warnings.push({
      title: 'Thin open interest',
      detail: `${contract.oi.toLocaleString()} contracts of open interest is below the liquidity floor.`,
    });
  }
  if (Math.abs(contract.delta) < 0.12) {
    warnings.push({
      title: 'Low delta',
      detail: 'The selected strike may not respond strongly to the underlying move.',
    });
  }
  return warnings;
}

function scoreLabel(strategy: StrikeStrategy): string {
  if (strategy === 'RISK') return 'Risk weighted';
  if (strategy === 'LIQ') return 'Liquidity';
  if (strategy === 'IV') return 'Volatility';
  return 'Balanced';
}

export function compareStrikeStrategies(
  chain: StrikeChain,
  optionType: StrikeOptionType,
  targetDelta = 0.3
): StrikeComparisonRow[] {
  return STRIKE_STRATEGIES.map((strategy) => {
    const contract = selectContract(chain, optionType, strategy.id, targetDelta);
    return {
      strategy: strategy.id,
      strategyName: STRATEGY_NAMES.get(strategy.id) || strategy.id,
      strike: contract?.strike ?? 0,
      premiumLabel: formatCurrency(midpoint(contract)),
      deltaLabel: contract ? formatDelta(contract.delta) : '-',
      ivLabel: contract ? `${contract.iv.toFixed(1)}%` : '-',
      spreadLabel: formatCurrency(spread(contract)),
      scoreLabel: scoreLabel(strategy.id),
    };
  });
}

export function summarizeStrikeSelection(input: StrikeSelectionInput): StrikeSelectionDigest {
  const targetDelta = Number(input.targetDelta ?? 0.3);
  const selectedContract = selectContract(input.chain, input.optionType, input.strategy, targetDelta);
  const warnings = warningItems(selectedContract);
  const contractCount = contractsFor(input.chain, input.optionType).length;

  let primaryStatus: StrikeDigestStatus;
  if (!selectedContract) {
    primaryStatus = {
      title: 'Chain Empty',
      detail: 'No contracts are available for this ticker, expiration, and side.',
      tone: 'idle',
    };
  } else if (warnings.length > 0) {
    primaryStatus = {
      title: 'Execution Review',
      detail: `${warnings.length} strike quality signal${warnings.length === 1 ? '' : 's'} need review.`,
      tone: 'attention',
    };
  } else {
    primaryStatus = {
      title: 'Strike Ready',
      detail: `${input.strategy} selected a ${input.optionType} strike with usable spread and liquidity.`,
      tone: 'live',
    };
  }

  return {
    primaryStatus,
    warningItems: warnings,
    selectedContract,
    selectedStrike: selectedContract?.strike ?? null,
    selectedPremiumLabel: formatCurrency(midpoint(selectedContract)),
    spreadLabel: formatCurrency(spread(selectedContract)),
    deltaLabel: selectedContract ? formatDelta(selectedContract.delta) : '-',
    ivLabel: selectedContract ? `${selectedContract.iv.toFixed(1)}%` : '-',
    moneynessLabel: moneynessLabel(input.chain, input.optionType, selectedContract),
    liquidityLabel: selectedContract ? `${selectedContract.oi.toLocaleString()} OI` : '-',
    contractCount,
    comparisonRows: compareStrikeStrategies(input.chain, input.optionType, targetDelta),
  };
}
