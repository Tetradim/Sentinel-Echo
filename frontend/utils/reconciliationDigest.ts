export interface ReconciliationRow {
  alert_id?: string;
  ticker?: string;
  trade_id?: string;
  trade_status?: string;
  order_id?: string;
  position_id?: string;
  position_status?: string;
  simulated?: boolean;
  attention_reason?: string;
}

export interface ReconciliationDigest {
  total: number;
  attentionCount: number;
  pendingCount: number;
  liveCount: number;
  title: string;
  detail: string;
}

export function summarizeReconciliation(rows: ReconciliationRow[] | null | undefined): ReconciliationDigest {
  const list = Array.isArray(rows) ? rows : [];
  const attentionCount = list.filter((row) => String(row.attention_reason || '').length > 0).length;
  const pendingCount = list.filter((row) => String(row.trade_status || '').toLowerCase() === 'pending').length;
  const liveCount = list.filter((row) => row.simulated === false).length;

  return {
    total: list.length,
    attentionCount,
    pendingCount,
    liveCount,
    title: attentionCount > 0 ? 'Reconciliation Review' : 'Reconciliation Clear',
    detail: attentionCount > 0
      ? `${attentionCount} chain${attentionCount === 1 ? '' : 's'} need operator review.`
      : `${list.length} chain${list.length === 1 ? '' : 's'} linked without attention flags.`,
  };
}
