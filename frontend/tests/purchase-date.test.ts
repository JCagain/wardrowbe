import { describe, expect, it } from 'vitest';
import { formatPurchaseDate, normalizePurchaseDate } from '@/lib/purchase-date';

describe('purchase date', () => {
  it('accepts year-only and year-month', () => {
    expect(normalizePurchaseDate('2024')).toBe('2024');
    expect(normalizePurchaseDate('2024-03')).toBe('2024-03');
    expect(() => normalizePurchaseDate('2024-03-05')).toThrow();
    expect(() => normalizePurchaseDate('abcd')).toThrow();
    expect(normalizePurchaseDate('')).toBe('');
  });

  it('formats by precision', () => {
    expect(formatPurchaseDate('2024-01', 'year')).toBe('2024');
    expect(formatPurchaseDate('2024-03', 'month')).toBe('2024-03');
    expect(formatPurchaseDate('2024-03', null)).toBe('2024-03');
    expect(formatPurchaseDate(null, null)).toBe('');
  });
});
