import { api } from './api';

export const API_ROUTES = {
  settings: '/api/settings',
  toggleTrading: '/api/toggle-trading',
  positions: '/api/positions',
  operatorEvents: '/api/operator/events',
  operatorTestAlert: '/api/operator/test-alert',
  operatorSimulateExit: '/api/operator/simulate-exit',
  liveReadiness: '/api/operator/live-readiness',
  liveArm: '/api/operator/live-arm',
  liveDisarm: '/api/operator/live-disarm',
  panicStop: '/api/operator/panic-stop',
  reconciliation: '/api/operator/reconciliation',
  alertChains: '/api/operator/alert-chains',
  brokerSwitch: '/api/broker/switch',
  brokerCheck: '/api/broker/check',
} as const;

export function getSettings() {
  return api.get(API_ROUTES.settings);
}

export function updateSettings(payload: Record<string, unknown>) {
  return api.put(API_ROUTES.settings, payload);
}

export function toggleTrading() {
  return api.post(API_ROUTES.toggleTrading);
}

export function getPositions() {
  return api.get(API_ROUTES.positions);
}

export function sellPosition(positionId: string, sellPercentage: number, exitPrice: number) {
  return api.post(`${API_ROUTES.positions}/${positionId}/sell?sell_percentage=${sellPercentage}&exit_price=${exitPrice}`);
}

export function closeTrade(tradeId: string, exitPrice: number) {
  return api.post(`/api/trades/${tradeId}/close`, { exit_price: exitPrice });
}

export function updateTradePrice(tradeId: string, currentPrice: number) {
  return api.put(`/api/trades/${tradeId}/price`, { current_price: currentPrice });
}

export function switchBroker(brokerId: string) {
  return api.post(`${API_ROUTES.brokerSwitch}/${brokerId}`);
}

export function checkBroker(brokerId: string) {
  return api.post(`${API_ROUTES.brokerCheck}/${brokerId}`);
}

export function getOperatorEvents(limit = 100) {
  return api.get(`${API_ROUTES.operatorEvents}?limit=${limit}`);
}

export function createOperatorTestAlert() {
  return api.post(API_ROUTES.operatorTestAlert);
}

export function simulateOperatorExit(payload: { sell_percentage: number; exit_price: number; position_id?: string }) {
  return api.post(API_ROUTES.operatorSimulateExit, payload);
}

export function getLiveReadiness() {
  return api.get(API_ROUTES.liveReadiness);
}

export function armLiveTrading(payload: { duration_minutes: number; confirmation: string; reason?: string }) {
  return api.post(API_ROUTES.liveArm, payload);
}

export function disarmLiveTrading() {
  return api.post(API_ROUTES.liveDisarm);
}

export function panicStop() {
  return api.post(API_ROUTES.panicStop);
}

export function getReconciliation(limit = 100) {
  return api.get(`${API_ROUTES.reconciliation}?limit=${limit}`);
}

export function getAlertChains(limit = 100) {
  return api.get(`${API_ROUTES.alertChains}?limit=${limit}`);
}
