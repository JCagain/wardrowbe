import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

import { RecordCard } from '@/components/records/record-card';

const record = {
  id: 'r1', date: '2026-10-01', season: 'fall', city: '杭州',
  weather: { temp_high: 24, temp_low: 16, condition: 'rain' },
  occasion: null, notes: null,
  photos: [{ id: 'p1', position: 0, image_url: 'u', thumbnail_url: 't1' }],
  items: [{ id: 'i1', type: 't-shirt', primary_colors: [], thumbnail_url: 'ti' }],
  created_at: '', updated_at: '',
};

describe('RecordCard', () => {
  it('links to the edit page and shows cover, city, temps, items', () => {
    render(<RecordCard record={record} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/dashboard/history/r1');
    expect(screen.getByTestId('record-card-cover')).toHaveAttribute('src', 't1');
    expect(screen.getByTestId('record-card-city').textContent).toContain('杭州');
    expect(screen.getByTestId('record-card-temps').textContent).toContain('16');
    expect(screen.getByTestId('record-card-temps').textContent).toContain('24');
    expect(screen.getAllByTestId('record-card-item')).toHaveLength(1);
  });

  it('omits weather block when weather is null', () => {
    render(<RecordCard record={{ ...record, weather: null, city: null }} />);
    expect(screen.queryByTestId('record-card-temps')).toBeNull();
    expect(screen.queryByTestId('record-card-city')).toBeNull();
  });
});
