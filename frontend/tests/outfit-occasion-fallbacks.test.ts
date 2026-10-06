import { format } from 'date-fns';
import { describe, expect, it, vi } from 'vitest';
import { getCardTitle } from '@/components/outfits/outfit-card';
import { defaultCloneName } from '@/components/shared/clone-to-lookbook-dialog';
import type { Outfit } from '@/lib/hooks/use-outfits';

// The modules render next/image and next/link; nothing here renders them.
vi.mock('next/image', () => ({ default: () => null }));
vi.mock('next/link', () => ({ default: () => null }));

// Records the interpolation values so the fallback chain is observable.
const t = (key: string, values?: Record<string, string>) =>
  values ? `${key}(${values.occasion ?? ''})` : key;

describe('getCardTitle with a nullable occasion', () => {
  it('falls back to the untitled label instead of dereferencing null', () => {
    expect(getCardTitle({ occasion: null } as unknown as Outfit, t)).toBe('untitledOutfit');
  });

  it('capitalizes the occasion into the fallback template', () => {
    expect(getCardTitle({ occasion: 'dinner' } as unknown as Outfit, t)).toBe(
      'outfitFallback(Dinner)',
    );
  });

  it('prefers name, then reasoning, then the first highlight', () => {
    expect(getCardTitle({ name: 'N', occasion: 'dinner' } as unknown as Outfit, t)).toBe('N');
    expect(getCardTitle({ reasoning: 'R', occasion: 'dinner' } as unknown as Outfit, t)).toBe('R');
    expect(getCardTitle({ highlights: ['H'], occasion: 'dinner' } as unknown as Outfit, t)).toBe('H');
  });
});

describe('defaultCloneName with a nullable occasion', () => {
  it('drops the occasion prefix instead of crashing on null', () => {
    expect(defaultCloneName(null)).toBe(format(new Date(), 'MMM d'));
    expect(defaultCloneName('')).toBe(format(new Date(), 'MMM d'));
  });

  it('keeps the capitalized prefix for a present occasion', () => {
    expect(defaultCloneName('dinner')).toBe(`Dinner — ${format(new Date(), 'MMM d')}`);
  });
});
