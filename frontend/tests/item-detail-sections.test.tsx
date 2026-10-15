import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mutateAsync = vi.fn();
const fetchNextPage = vi.fn();
let recordsState: Record<string, unknown> = {};
let companionsState: Record<string, unknown> = {};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('next/image', () => ({ default: (p: { alt: string }) => <img alt={p.alt} /> }));
vi.mock('next/link', () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/hooks/use-items', () => ({
  useUpdateItem: () => ({ mutateAsync, isPending: false }),
  useItemCompanions: () => companionsState,
}));
vi.mock('@/lib/hooks/use-records', () => ({ useItemRecords: () => recordsState }));
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingTypes: () => [{ value: 'jeans', label: '牛仔裤', body_part: 'bottoms' }],
}));

import { WearCountEditor } from '@/components/item-detail/wear-count-editor';
import { ItemRecordsSection } from '@/components/item-detail/item-records-section';
import { ItemCompanionsSection } from '@/components/item-detail/item-companions-section';

const item = { id: 'i1', wear_count: 3 } as never;

beforeEach(() => {
  mutateAsync.mockReset().mockResolvedValue({});
  fetchNextPage.mockReset();
});

describe('WearCountEditor', () => {
  it('sends only wear_count', async () => {
    render(<WearCountEditor item={item} />);
    fireEvent.click(screen.getByRole('button', { name: 'wearCount.edit' }));
    fireEvent.change(screen.getByLabelText('wearCount.label'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'wearCount.save' }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ id: 'i1', data: { wear_count: 7 } }));
  });

  it('rejects negative and non-integer input without calling the API', () => {
    render(<WearCountEditor item={item} />);
    fireEvent.click(screen.getByRole('button', { name: 'wearCount.edit' }));
    for (const bad of ['-1', '1.5', '']) {
      fireEvent.change(screen.getByLabelText('wearCount.label'), { target: { value: bad } });
      fireEvent.click(screen.getByRole('button', { name: 'wearCount.save' }));
    }
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});

describe('ItemRecordsSection', () => {
  it('lists records newest first with links and loads more', () => {
    recordsState = {
      isLoading: false, isError: false, hasNextPage: true, isFetchingNextPage: false, fetchNextPage,
      data: { pages: [{ total: 3, records: [
        { id: 'r2', date: '2026-10-02', photos: [], items: [], occasion: null },
        { id: 'r1', date: '2026-09-01', photos: [], items: [], occasion: null },
      ] }] },
    };
    render(<ItemRecordsSection itemId="i1" />);
    const links = screen.getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/dashboard/history/r2', '/dashboard/history/r1']);
    fireEvent.click(screen.getByRole('button', { name: 'records.loadMore' }));
    expect(fetchNextPage).toHaveBeenCalled();
  });

  it('shows the empty state', () => {
    recordsState = { isLoading: false, isError: false, hasNextPage: false, data: { pages: [{ total: 0, records: [] }] } };
    render(<ItemRecordsSection itemId="i1" />);
    expect(screen.getByText('records.empty')).toBeTruthy();
  });
});

describe('ItemCompanionsSection', () => {
  it('shows counts and marks retired companions', () => {
    companionsState = { isLoading: false, isError: false, data: [
      { id: 'c1', type: 'jeans', name: null, primary_colors: [], lifecycle: 'active', count: 4, thumbnail_url: null },
      { id: 'c2', type: 'jeans', name: '旧裤', primary_colors: [], lifecycle: 'retired', count: 1, thumbnail_url: null },
    ] };
    render(<ItemCompanionsSection itemId="i1" />);
    expect(screen.getByText('companions.times:{"count":4}')).toBeTruthy();
    expect(screen.getAllByText('companions.retired')).toHaveLength(1);
    expect(screen.getByText('牛仔裤')).toBeTruthy();
    expect(screen.getByText('旧裤')).toBeTruthy();
  });
});
