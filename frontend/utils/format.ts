/**
 * Validates a price string entered by the user.
 * Returns the parsed float on success, or null with a reason on failure.
 */
export function validatePrice(
  raw: string,
  opts: { min?: number; max?: number } = {}
): { value: number; error: null } | { value: null; error: string } {
  const { min = 0.01, max = 100_000 } = opts;
  const parsed = parseFloat(raw);
  if (!raw || raw.trim() === '') return { value: null, error: 'Price is required' };
  if (isNaN(parsed)) return { value: null, error: 'Enter a valid number' };
  if (parsed < min) return { value: null, error: `Price must be at least $${min.toFixed(2)}` };
  if (parsed > max) return { value: null, error: `Price must be under $${max.toLocaleString()}` };
  return { value: parsed, error: null };
}

/**
 * Validates a percentage string (1–100).
 */
export function validatePercentage(
  raw: string,
  opts: { min?: number; max?: number } = {}
): { value: number; error: null } | { value: null; error: string } {
  const { min = 0.1, max = 100 } = opts;
  const parsed = parseFloat(raw);
  if (!raw || raw.trim() === '') return { value: null, error: 'Value is required' };
  if (isNaN(parsed)) return { value: null, error: 'Enter a valid number' };
  if (parsed < min) return { value: null, error: `Must be at least ${min}%` };
  if (parsed > max) return { value: null, error: `Must be at most ${max}%` };
  return { value: parsed, error: null };
}

/**
 * Formats a date string for display. Returns 'Never' for null.
 */
export function formatDate(dateString: string | null): string {
  if (!dateString) return 'Never';
  return new Date(dateString).toLocaleString();
}

export function finiteNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatCurrency(
  value: number | string | null | undefined,
  fallback = '--'
): string {
  const numeric = finiteNumber(value);
  return numeric === null ? fallback : `$${numeric.toFixed(2)}`;
}

/**
 * Formats a P&L value as a dollar string with sign.
 */
export function formatPnL(value: number | null | undefined): string {
  if (value === null || value === undefined) return '$0.00';
  const formatted = Math.abs(value).toFixed(2);
  return value >= 0 ? `+$${formatted}` : `-$${formatted}`;
}

/**
 * Returns the appropriate colour for a P&L value.
 */
export function getPnLColor(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return '#94a3b8';
  return value > 0 ? '#22c55e' : '#ef4444';
}
