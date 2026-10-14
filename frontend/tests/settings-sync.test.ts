import { describe, expect, it } from 'vitest';
import { syncFormWithPreferences } from '@/lib/settings-sync';
import type { Preferences } from '@/lib/types';

const fresh = {
  cities: [{ name: '杭州', latitude: 1, longitude: 2 }],
  default_city: '杭州',
  color_favorites: ['red'],
} as unknown as Preferences;

describe('syncFormWithPreferences', () => {
  it('replaces the form when nothing is dirty', () => {
    expect(syncFormWithPreferences({ color_favorites: ['blue'] }, fresh, false)).toBe(fresh);
  });

  it('keeps unsaved edits and only merges city fields when dirty', () => {
    const current = { color_favorites: ['blue'], cities: [], default_city: null } as Partial<Preferences>;
    const next = syncFormWithPreferences(current, fresh, true);
    expect(next.color_favorites).toEqual(['blue']);
    expect(next.cities).toBe(fresh.cities);
    expect(next.default_city).toBe('杭州');
  });
});
