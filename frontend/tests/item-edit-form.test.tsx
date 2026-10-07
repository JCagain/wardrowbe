import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PartTypeSelect } from '@/components/vocab/part-type-select';
import { editFormFromItem, lifecycleBadgeProps, lifecycleLabelKey, partTypeChangeHandlers } from '@/lib/item-edit-form';
import type { Item } from '@/lib/types';
import {
  BODY_PART_LABELS,
  BODY_PART_VALUES,
  TYPE_ENTRIES,
} from '@/lib/generated/garment-vocabulary';

// PartTypeSelect fires onBodyPartChange and onTypeChange in the same change
// event (picking a part resets the type). Value-form setters would let the
// second call overwrite the first from the same stale closure — the detail
// dialog shipped exactly that bug. This harness holds a single form object the
// way editForm does and wires the dialog's real handlers, so the double-fire
// has to land both updates.

interface Form {
  name: string;
  body_part: string;
  type: string;
}

const PARTS = BODY_PART_VALUES.map((value) => ({ value, label: BODY_PART_LABELS[value] }));

function Harness({ initial }: { initial: Form }) {
  const [form, setForm] = useState<Form>(initial);
  return (
    <>
      <PartTypeSelect
        parts={PARTS}
        entries={[...TYPE_ENTRIES]}
        bodyPart={form.body_part}
        type={form.type}
        {...partTypeChangeHandlers(setForm)}
      />
      <pre data-testid="form">{JSON.stringify(form)}</pre>
    </>
  );
}

const readForm = () =>
  JSON.parse(screen.getByTestId('form').textContent ?? '{}') as Form;

describe('PartTypeSelect-driven edit form state', () => {
  it('keeps the body-part change and resets the type in one change event', () => {
    render(<Harness initial={{ name: 'coat', body_part: 'tops', type: 'shirt' }} />);
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'bottoms' } });
    expect(readForm()).toEqual({ name: 'coat', body_part: 'bottoms', type: '' });
  });

  it('updates the type alone without touching the body part', () => {
    render(<Harness initial={{ name: 'coat', body_part: 'bottoms', type: '' }} />);
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'jeans' } });
    expect(readForm()).toEqual({ name: 'coat', body_part: 'bottoms', type: 'jeans' });
  });
});

describe('editFormFromItem purchase date', () => {
  // The detail dialog used to back-fill the raw wire value ("2024-01"), so the
  // first unrelated save rewrote a year-only purchase date to month precision.
  // The form must refill from the precision marker.
  const baseItem = {
    name: null,
    type: 'shirt',
    body_part: 'tops',
    subtype: null,
    brand: null,
    primary_colors: [],
    secondary_colors: [],
    style: [],
    tags: {},
    temp_low: null,
    temp_high: null,
    purchase_price: null,
    is_archived: false,
    archive_reason: null,
    notes: null,
    favorite: false,
    wash_interval: null,
  };

  it('refills year-only dates as YYYY', () => {
    const form = editFormFromItem({
      ...baseItem,
      purchase_date: '2024-01',
      purchase_date_precision: 'year',
    } as unknown as Item);
    expect(form.purchase_date).toBe('2024');
  });

  it('refills month dates as YYYY-MM', () => {
    const form = editFormFromItem({
      ...baseItem,
      purchase_date: '2024-01',
      purchase_date_precision: 'month',
    } as unknown as Item);
    expect(form.purchase_date).toBe('2024-01');
  });
});

describe('lifecycle edit form', () => {
  // 状态三态（spec §5/§10.16）：表单以 lifecycle 为权威，is_archived 只是兼容视图。
  const baseItem = {
    name: null,
    type: 'shirt',
    body_part: 'tops',
    subtype: null,
    brand: null,
    primary_colors: [],
    secondary_colors: [],
    style: [],
    tags: {},
    temp_low: null,
    temp_high: null,
    purchase_date: null,
    purchase_date_precision: null,
    purchase_price: null,
    archive_reason: null,
    notes: null,
    favorite: false,
    wash_interval: null,
  };

  it('maps the three states onto the edit form', () => {
    expect(
      editFormFromItem({ ...baseItem, lifecycle: 'idle', is_archived: false } as unknown as Item)
        .lifecycle,
    ).toBe('idle');
    expect(
      editFormFromItem({ ...baseItem, lifecycle: 'retired', is_archived: true } as unknown as Item)
        .lifecycle,
    ).toBe('retired');
  });

  it('falls back to the compat view for rows without lifecycle', () => {
    expect(
      editFormFromItem({ ...baseItem, is_archived: true } as unknown as Item).lifecycle,
    ).toBe('retired');
    expect(
      editFormFromItem({ ...baseItem, is_archived: false } as unknown as Item).lifecycle,
    ).toBe('active');
  });
});

describe('lifecycle read-view label', () => {
  it('maps the three states onto distinct status keys', () => {
    expect(lifecycleLabelKey({ lifecycle: 'active', is_archived: false })).toBe('statusActive');
    expect(lifecycleLabelKey({ lifecycle: 'idle', is_archived: false })).toBe('statusIdle');
    expect(lifecycleLabelKey({ lifecycle: 'retired', is_archived: true })).toBe('statusRetired');
  });

  it('falls back to the compat view for rows without lifecycle', () => {
    expect(lifecycleLabelKey({ is_archived: true } as Item)).toBe('statusRetired');
    expect(lifecycleLabelKey({ is_archived: false } as Item)).toBe('statusActive');
  });
});

describe('lifecycle read-view badge', () => {
  // The chip used to key off is_archived alone, so an idle item wore the same
  // filled secondary chip as an active one and only the label differed.
  it('gives each of the three states its own chip', () => {
    expect(lifecycleBadgeProps({ lifecycle: 'active', is_archived: false })).toEqual({
      variant: 'secondary',
      className: '',
    });
    expect(lifecycleBadgeProps({ lifecycle: 'idle', is_archived: false })).toEqual({
      variant: 'outline',
      className: 'border-dashed text-muted-foreground',
    });
    expect(lifecycleBadgeProps({ lifecycle: 'retired', is_archived: true })).toEqual({
      variant: 'outline',
      className: '',
    });
  });

  it('falls back to the compat view for rows without lifecycle', () => {
    expect(lifecycleBadgeProps({ is_archived: true } as Item)).toEqual({
      variant: 'outline',
      className: '',
    });
    expect(lifecycleBadgeProps({ is_archived: false } as Item)).toEqual({
      variant: 'secondary',
      className: '',
    });
  });
});
