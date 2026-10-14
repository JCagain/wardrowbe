import { describe, expect, it } from 'vitest';
import { RECORD_SEASONS, seasonForDate } from '@/lib/records/season';

describe('seasonForDate (spec §3.1: 3-5 春 / 6-9 夏 / 10-11 秋 / 12-2 冬)', () => {
  const cases: Array<[string, string]> = [
    ['2026-01-15', 'winter'], ['2026-02-28', 'winter'], ['2026-03-01', 'spring'],
    ['2026-05-31', 'spring'], ['2026-06-01', 'summer'], ['2026-09-30', 'summer'],
    ['2026-10-01', 'fall'], ['2026-11-30', 'fall'], ['2026-12-01', 'winter'],
  ];
  it.each(cases)('%s → %s', (iso, expected) => {
    expect(seasonForDate(iso)).toBe(expected);
  });

  it('accepts Date objects using local calendar date', () => {
    expect(seasonForDate(new Date(2026, 9, 14))).toBe('fall');
  });

  it('has no all-season', () => {
    expect(RECORD_SEASONS).toEqual(['spring', 'summer', 'fall', 'winter']);
  });
});
