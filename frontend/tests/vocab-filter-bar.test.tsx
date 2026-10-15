import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { EMPTY_VOCAB_FILTERS } from '@/lib/wardrobe-filters';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, string>) =>
    params?.label ? `${params.label}(off)` : key,
}));
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useBodyParts: () => [{ value: 'tops', label: '上衣' }, { value: 'bottoms', label: '下装' }],
  useClothingTypes: () => [
    { value: 't-shirt', label: 'T恤', body_part: 'tops' },
    { value: 'jeans', label: '牛仔裤', body_part: 'bottoms' },
  ],
  useColorFamilies: () => [{ value: 'red', label: '红色系' }, { value: 'blue', label: '蓝色系' }],
  useClothingColors: () => [
    { value: 'wine', label: '酒红', family: 'red', hex: '#8a2b42' },
    { value: 'brick', label: '砖红', family: 'red', hex: '#a1422f', disabled: true },
    { value: 'navy', label: '藏青', family: 'blue', hex: '#1b2a4a' },
  ],
  useStyles: () => [{ value: 'goth', label: '哥特' }],
  useSeasons: () => [{ value: 'summer', label: '夏' }, { value: 'all-season', label: '四季' }],
}));

import { VocabFilterBar } from '@/components/wardrobe/vocab-filter-bar';

describe('VocabFilterBar', () => {
  it('picking a body part narrows the type options and clears an out-of-part type', () => {
    const onChange = vi.fn();
    render(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, type: 'jeans' }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('bodyPart'), { target: { value: 'tops' } });
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_VOCAB_FILTERS, bodyPart: 'tops', type: '' });
  });

  it('type options follow the selected part', () => {
    render(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, bodyPart: 'tops' }} onChange={() => {}} />);
    const typeSelect = screen.getByLabelText('type') as HTMLSelectElement;
    expect(Array.from(typeSelect.options).map((o) => o.value)).toEqual(['', 't-shirt']);
  });

  it('color options follow the family and mark disabled colors', () => {
    render(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, colorFamily: 'red' }} onChange={() => {}} />);
    const colorSelect = screen.getByLabelText('color') as HTMLSelectElement;
    expect(Array.from(colorSelect.options).map((o) => o.textContent)).toEqual(['allColors', '酒红', '砖红(off)']);
  });

  it('color scope select switches between primary, secondary and any', () => {
    const onChange = vi.fn();
    render(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, color: 'wine' }} onChange={onChange} />);
    const scope = screen.getByLabelText('colorScope') as HTMLSelectElement;
    expect(Array.from(scope.options).map((o) => o.value)).toEqual(['primary', 'secondary', 'any']);
    fireEvent.change(scope, { target: { value: 'secondary' } });
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_VOCAB_FILTERS, color: 'wine', colorScope: 'secondary' });
  });

  it('style and season selects emit single values', () => {
    const onChange = vi.fn();
    render(<VocabFilterBar value={EMPTY_VOCAB_FILTERS} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('season'), { target: { value: 'summer' } });
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_VOCAB_FILTERS, season: 'summer' });
    fireEvent.change(screen.getByLabelText('style'), { target: { value: 'goth' } });
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_VOCAB_FILTERS, style: 'goth' });
  });

  it('keeps a hand-edited filter visible even when it is outside the narrowed options', () => {
    render(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, bodyPart: 'tops', type: 'jeans' }} onChange={() => {}} />);
    const typeSelect = screen.getByLabelText('type') as HTMLSelectElement;
    expect(typeSelect.value).toBe('jeans');
    expect(typeSelect.selectedOptions[0].textContent).toBe('牛仔裤');
  });

  it('keeps an unknown color value visible with its raw value', () => {
    render(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, color: 'zzz' }} onChange={() => {}} />);
    const colorSelect = screen.getByLabelText('color') as HTMLSelectElement;
    expect(colorSelect.selectedOptions[0].textContent).toBe('zzz');
  });

  it('color scope select is disabled without a color dimension and enabled with one', () => {
    const { rerender } = render(<VocabFilterBar value={EMPTY_VOCAB_FILTERS} onChange={() => {}} />);
    expect((screen.getByLabelText('colorScope') as HTMLSelectElement).disabled).toBe(true);
    rerender(<VocabFilterBar value={{ ...EMPTY_VOCAB_FILTERS, colorFamily: 'red' }} onChange={() => {}} />);
    expect((screen.getByLabelText('colorScope') as HTMLSelectElement).disabled).toBe(false);
  });
});
