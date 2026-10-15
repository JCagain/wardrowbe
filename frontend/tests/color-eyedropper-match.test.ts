import { describe, expect, it } from 'vitest';
import { findClosestColor } from '@/components/color-eyedropper';

const colors = [
  { value: 'black', hex: '#1a1a1a' },
  { value: 'red', hex: '#e60012' },
  { value: 'new-teal', hex: '#008080' },           // runtime-added
  { value: 'old-teal', hex: '#008081', disabled: true },
];

describe('findClosestColor', () => {
  it('matches runtime-added colors', () => {
    expect(findClosestColor('#00807f', colors)?.value).toBe('new-teal');
  });
  it('skips disabled entries', () => {
    expect(findClosestColor('#008081', colors)?.value).toBe('new-teal');
  });
  it('returns null before the vocabulary loads', () => {
    expect(findClosestColor('#123456', [])).toBeNull();
  });
});
