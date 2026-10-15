import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, p?: Record<string, unknown>) => (p ? `${key}:${JSON.stringify(p)}` : key),
}));
vi.mock('next/image', () => ({ default: (p: { alt: string }) => <img alt={p.alt} /> }));
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingColors: () => [{ value: 'wine', label: '酒红', family: 'red', hex: '#8a2b42', name: '酒红' }],
  useStyles: () => [{ value: 'goth', label: '哥特' }],
  useClothingTypes: () => [{ value: 'jeans', label: '牛仔裤', body_part: 'bottoms' }],
}));
vi.mock('@/lib/hooks/use-analytics', () => ({
  useAnalytics: () => ({
    isLoading: false,
    isError: false,
    data: {
      wardrobe: {
        total_items: 5, total_wears: 9,
        items_by_status: { ready: 3, processing: 1, archived: 0, error: 1 },
        total_records: 12, records_this_month: 7,
      },
      color_distribution: [{ color: 'wine', count: 4, percentage: 50 }],
      style_distribution: [{ style: 'goth', count: 3, percentage: 60 }],
      type_distribution: [{ type: 'jeans', count: 2, percentage: 40 }],
      most_worn: [], least_worn: [], never_worn: [],
    },
  }),
}));

import AnalyticsPage from '@/app/dashboard/analytics/page';

describe('analytics page', () => {
  it('renders total and this-month record counts, no week figure (user ruling)', () => {
    render(<AnalyticsPage />);
    expect(screen.getByText('12')).toBeTruthy();
    expect(screen.getByText('stats.records.description:{"month":7}')).toBeTruthy();
  });

  it('renders all four pipeline buckets including zero', () => {
    render(<AnalyticsPage />);
    for (const k of ['ready', 'processing', 'archived', 'error']) {
      expect(screen.getByText(`pipeline.${k}`)).toBeTruthy();
    }
  });

  it('labels colors, styles and types from the vocabulary and says 件次', () => {
    render(<AnalyticsPage />);
    expect(screen.getByText('酒红')).toBeTruthy();
    expect(screen.getByText('哥特')).toBeTruthy();
    expect(screen.getByText('牛仔裤')).toBeTruthy();
    expect(screen.getByText((c) => c.includes('pieces:{"count":4}'))).toBeTruthy();
    expect(screen.getByText((c) => c.includes('pieces:{"count":3}'))).toBeTruthy();
  });
});
