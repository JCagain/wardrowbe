import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));

import { GarmentRegionEditor } from '@/components/records/garment-region-editor';
import type { GarmentRegion } from '@/lib/types';

const parts = [
  { value: 'tops', label: 'TOPS' },
  { value: 'bottoms', label: 'BOTTOMS' },
];

function Harness({ initial, spy }: { initial: GarmentRegion[]; spy: (r: GarmentRegion[]) => void }) {
  const [regions, setRegions] = useState(initial);
  return (
    <GarmentRegionEditor
      imageSrc="data:image/png;base64,iVBORw0KGgo="
      regions={regions}
      bodyParts={parts}
      onChange={(r) => {
        setRegions(r);
        spy(r);
      }}
    />
  );
}

const top: GarmentRegion = { body_part: 'tops', box: { l: 0, t: 0, r: 99, b: 99 }, source: 'auto' };

describe('GarmentRegionEditor', () => {
  it('adds a manual box and selects it', () => {
    const spy = vi.fn();
    render(<Harness initial={[]} spy={spy} />);
    fireEvent.click(screen.getByTestId('regions-add'));
    const last = spy.mock.calls.at(-1)![0] as GarmentRegion[];
    expect(last).toHaveLength(1);
    expect(last[0].source).toBe('manual');
    expect(screen.getByTestId('regions-delete')).not.toBeDisabled();
  });

  it('disables add at the 12-box cap', () => {
    render(<Harness initial={Array.from({ length: 12 }, () => top)} spy={vi.fn()} />);
    expect(screen.getByTestId('regions-add')).toBeDisabled();
  });

  it('changes the part of the selected box and marks it manual', () => {
    const spy = vi.fn();
    render(<Harness initial={[top]} spy={spy} />);
    fireEvent.click(screen.getByTestId('region-chip-0'));
    fireEvent.change(screen.getByTestId('regions-part'), { target: { value: 'bottoms' } });
    expect(spy.mock.calls.at(-1)![0]).toEqual([{ ...top, body_part: 'bottoms', source: 'manual' }]);
  });

  it('deletes the selected box', () => {
    const spy = vi.fn();
    render(<Harness initial={[top]} spy={spy} />);
    expect(screen.getByTestId('regions-delete')).toBeDisabled();
    fireEvent.click(screen.getByTestId('region-chip-0'));
    fireEvent.click(screen.getByTestId('regions-delete'));
    expect(spy.mock.calls.at(-1)![0]).toEqual([]);
  });
});

describe('GarmentRegionEditor redraw on image load', () => {
  it('redraws every time the image fires load (canvas resize clears it)', () => {
    const strokeRect = vi.fn();
    const ctx = {
      clearRect: vi.fn(), strokeRect, fillRect: vi.fn(), fillText: vi.fn(),
      lineWidth: 0, strokeStyle: '', fillStyle: '', font: '',
    };
    const spy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as never);
    const { container } = render(<Harness initial={[top]} spy={vi.fn()} />);
    const img = container.querySelector('img')!;
    fireEvent.load(img);
    const first = strokeRect.mock.calls.length;
    expect(first).toBeGreaterThan(0);
    fireEvent.load(img);
    expect(strokeRect.mock.calls.length).toBeGreaterThan(first);
    spy.mockRestore();
  });
});
