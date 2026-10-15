import { describe, expect, it } from 'vitest';
import {
  EMPTY_VOCAB_FILTERS,
  colorOptionsFor,
  countVocabFilters,
  readVocabFilters,
  setBodyPart,
  setColorFamily,
  typeOptionsFor,
  vocabFiltersToItemFilter,
  writeVocabFilters,
} from '@/lib/wardrobe-filters';

const types = [
  { value: 'jeans', label: '牛仔裤', body_part: 'bottoms' },
  { value: 't-shirt', label: 'T恤', body_part: 'tops' },
  { value: 'old-top', label: '旧上衣', body_part: 'tops', disabled: true },
];
const colors = [
  { value: 'wine', label: '酒红', family: 'red', hex: '#8a2b42' },
  { value: 'navy', label: '藏青', family: 'blue', hex: '#1b2a4a' },
  { value: 'brick', label: '砖红', family: 'red', hex: '#a1422f', disabled: true },
];

describe('readVocabFilters', () => {
  it('reads every dimension from the URL', () => {
    const p = new URLSearchParams('part=tops&type=t-shirt&family=red&color=wine&style=goth&season=summer');
    expect(readVocabFilters(p)).toEqual({
      bodyPart: 'tops', type: 't-shirt', colorFamily: 'red', color: 'wine', colorScope: 'primary', style: 'goth', season: 'summer',
    });
  });
  it('treats legacy type=all as no type filter', () => {
    expect(readVocabFilters(new URLSearchParams('type=all')).type).toBe('');
  });
  it('reads colorScope and falls back to primary on junk', () => {
    expect(readVocabFilters(new URLSearchParams('colorScope=secondary')).colorScope).toBe('secondary');
    expect(readVocabFilters(new URLSearchParams('colorScope=both')).colorScope).toBe('primary');
  });
});

describe('writeVocabFilters', () => {
  it('sets non-empty keys and deletes empty ones, keeping unrelated params', () => {
    const p = new URLSearchParams('search=x&family=blue');
    writeVocabFilters(p, { ...EMPTY_VOCAB_FILTERS, style: 'goth' });
    expect(p.get('style')).toBe('goth');
    expect(p.has('family')).toBe(false);
    expect(p.get('search')).toBe('x');
    expect(p.has('colorScope')).toBe(false);
    writeVocabFilters(p, { ...EMPTY_VOCAB_FILTERS, colorScope: 'any' });
    expect(p.get('colorScope')).toBe('any');
  });
});

describe('vocabFiltersToItemFilter', () => {
  it('maps to API field names and drops empties', () => {
    expect(vocabFiltersToItemFilter({ ...EMPTY_VOCAB_FILTERS, colorFamily: 'red', color: 'wine', season: 'fall' }))
      .toEqual({ color_family: 'red', colors: ['wine'], season: 'fall' });
    expect(vocabFiltersToItemFilter(EMPTY_VOCAB_FILTERS)).toEqual({});
  });
  it('sends color_scope only when a color dimension is set and scope is not primary', () => {
    expect(vocabFiltersToItemFilter({ ...EMPTY_VOCAB_FILTERS, color: 'wine', colorScope: 'secondary' }))
      .toEqual({ colors: ['wine'], color_scope: 'secondary' });
    expect(vocabFiltersToItemFilter({ ...EMPTY_VOCAB_FILTERS, colorScope: 'any' })).toEqual({});
  });
});

describe('countVocabFilters', () => {
  it('counts each active dimension once', () => {
    expect(countVocabFilters({ ...EMPTY_VOCAB_FILTERS, bodyPart: 'tops', type: 't-shirt' })).toBe(2);
    expect(countVocabFilters(EMPTY_VOCAB_FILTERS)).toBe(0);
    // 匹配范围是颜色维度的修饰，不单独算一个筛选。
    expect(countVocabFilters({ ...EMPTY_VOCAB_FILTERS, colorScope: 'secondary' })).toBe(0);
  });
});

describe('cascade', () => {
  it('changing body part clears a type outside that part', () => {
    const s = { ...EMPTY_VOCAB_FILTERS, bodyPart: 'tops', type: 't-shirt' };
    expect(setBodyPart(s, 'bottoms', types)).toMatchObject({ bodyPart: 'bottoms', type: '' });
    expect(setBodyPart(s, 'tops', types)).toMatchObject({ type: 't-shirt' });
  });
  it('changing color family clears a color outside that family', () => {
    const s = { ...EMPTY_VOCAB_FILTERS, colorFamily: 'red', color: 'wine' };
    expect(setColorFamily(s, 'blue', colors)).toMatchObject({ colorFamily: 'blue', color: '' });
    expect(setColorFamily(s, '', colors)).toMatchObject({ colorFamily: '', color: 'wine' });
  });
});

describe('option lists include disabled entries (old data still carries them)', () => {
  it('types narrow by part and keep disabled', () => {
    expect(typeOptionsFor('tops', types).map((t) => t.value)).toEqual(['t-shirt', 'old-top']);
    expect(typeOptionsFor('', types)).toHaveLength(3);
  });
  it('colors narrow by family and keep disabled', () => {
    expect(colorOptionsFor('red', colors).map((c) => c.value)).toEqual(['wine', 'brick']);
  });
});
