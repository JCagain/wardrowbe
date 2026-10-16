import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string, v?: Record<string, unknown>) => (v ? `${k}:${JSON.stringify(v)}` : k),
}));

import { RecordPhotoStrip } from '@/components/records/record-photo-strip';

const base = { onAdd: vi.fn(), onRemove: vi.fn(), canRemove: true };

describe('RecordPhotoStrip regions', () => {
  it('shows a count badge only when regionCount > 0', () => {
    render(
      <RecordPhotoStrip
        {...base}
        photos={[
          { key: 'a', src: 'a.jpg', regionCount: 3 },
          { key: 'b', src: 'b.jpg', regionCount: 0 },
          { key: 'c', src: 'c.jpg' },
        ]}
      />,
    );
    const badges = screen.getAllByTestId('record-photo-region-count');
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent('3');
    expect(badges[0].getAttribute('aria-label')).toBe('regions.count:{"count":3}');
  });

  it('frame button exists only with onFrame and reports the photo key', () => {
    const onFrame = vi.fn();
    const photos = [{ key: 'a', src: 'a.jpg' }];
    const { rerender } = render(<RecordPhotoStrip {...base} photos={photos} />);
    expect(screen.queryByTestId('record-photo-frame')).toBeNull();
    rerender(<RecordPhotoStrip {...base} photos={photos} onFrame={onFrame} />);
    fireEvent.click(screen.getByTestId('record-photo-frame'));
    expect(onFrame).toHaveBeenCalledWith('a');
  });
});
