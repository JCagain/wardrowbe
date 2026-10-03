const PATTERN = /^\d{4}(-\d{2})?$/;

export function normalizePurchaseDate(input: string): string {
  const value = input.trim();
  if (value === '') return '';
  if (!PATTERN.test(value)) throw new Error(`invalid purchase date: ${input}`);
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
