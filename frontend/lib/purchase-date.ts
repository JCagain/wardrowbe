const PATTERN = /^\d{4}(-\d{2})?$/;

export function normalizePurchaseDate(input: string): string {
  const value = input.trim();
  if (value === '') return '';
  if (!PATTERN.test(value)) throw new Error(`invalid purchase date: ${input}`);
  const [year, month] = value.split('-');
  // The pattern alone admits "2024-13" / "0000"; the backend 422s them, so
  // surface the same verdict here instead of sending doomed payloads.
  if (Number(year) < 1) throw new Error(`invalid purchase date: ${input}`);
  if (month !== undefined && (Number(month) < 1 || Number(month) > 12)) {
    throw new Error(`invalid purchase date: ${input}`);
  }
  return value;
}

export function formatPurchaseDate(
  value: string | null | undefined,
  precision: string | null | undefined,
): string {
  if (!value) return '';
  const [year, month] = value.split('-');
  if (precision === 'year' || !month) return year;
  return `${year}-${month}`;
}
