import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

let params = new URLSearchParams();
const replace = vi.fn();
let monthState: Record<string, unknown> = {};
let timelineState: Record<string, unknown> = {};
const useRecordsSpy = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => params,
  useRouter: () => ({ replace, push: vi.fn() }),
}));
vi.mock('next/link', () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, p?: Record<string, unknown>) => (p ? `${key}:${JSON.stringify(p)}` : key),
}));
vi.mock('@/lib/hooks/use-records', () => ({
  useRecords: (from: string, to: string) => { useRecordsSpy(from, to); return monthState; },
  useRecordTimeline: () => timelineState,
}));
vi.mock('@/components/outfit-calendar', () => ({
  OutfitCalendar: (p: { year: number; month: number; selectedDate: Date | null }) => (
    <div data-testid="calendar">{`${p.year}-${p.month}-${p.selectedDate?.getDate()}`}</div>
  ),
}));
vi.mock('@/components/records/record-card', () => ({
  RecordCard: ({ record }: { record: { id: string } }) => <div data-testid="record">{record.id}</div>,
}));

import HistoryPage from '@/app/dashboard/history/page';

const rec = (id: string, date: string) => ({ id, date, photos: [], items: [] });

beforeEach(() => {
  params = new URLSearchParams();
  useRecordsSpy.mockReset();
  monthState = { isLoading: false, isError: false, data: { records: [] } };
  timelineState = { isLoading: false, isError: false, hasNextPage: false, data: { pages: [{ total: 0, records: [] }] } };
});

describe('history page', () => {
  it('?date= positions the calendar on that month and selects the day', () => {
    params = new URLSearchParams('date=2026-03-07');
    monthState = { isLoading: false, isError: false, data: { records: [rec('a', '2026-03-07'), rec('b', '2026-03-08')] } };
    render(<HistoryPage />);
    expect(useRecordsSpy).toHaveBeenCalledWith('2026-03-01', '2026-03-31');
    expect(screen.getByTestId('calendar').textContent).toBe('2026-3-7');
    expect(screen.getAllByTestId('record').map((e) => e.textContent)).toEqual(['a']);
  });

  it('an empty month shows the per-date empty state, not the global one', () => {
    render(<HistoryPage />);
    expect(screen.queryByText('empty.title')).toBeNull();
  });

  it('a load error keeps the new-record button', () => {
    monthState = { isLoading: false, isError: true };
    render(<HistoryPage />);
    expect(screen.getByText('loadError')).toBeTruthy();
    expect(screen.getAllByRole('link').some((a) => a.getAttribute('href') === '/dashboard/history/new')).toBe(true);
  });

  it('?view=timeline renders records grouped by date, newest first', () => {
    params = new URLSearchParams('view=timeline');
    timelineState = {
      isLoading: false, isError: false, hasNextPage: false,
      data: { pages: [{ total: 3, records: [rec('r3', '2026-10-02'), rec('r2', '2026-10-02'), rec('r1', '2026-09-30')] }] },
    };
    render(<HistoryPage />);
    expect(screen.queryByTestId('calendar')).toBeNull();
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['2026-10-02', '2026-09-30']);
    expect(screen.getAllByTestId('record').map((e) => e.textContent)).toEqual(['r3', 'r2', 'r1']);
  });
});
