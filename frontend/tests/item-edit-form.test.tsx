import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PartTypeSelect } from '@/components/vocab/part-type-select';
import { partTypeChangeHandlers } from '@/lib/item-edit-form';
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
