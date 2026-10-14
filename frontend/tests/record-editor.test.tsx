import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const createMutate = vi.fn();
const updateMutate = vi.fn();
const fetchWeather = vi.fn();

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/shared/item-picker', () => ({ ItemPicker: () => null }));
vi.mock('@/lib/hooks/use-preferences', () => ({
  usePreferences: () => ({
    data: {
      cities: [{ name: '杭州', latitude: 30.27, longitude: 120.15 }],
      default_city: '杭州',
    },
  }),
}));
vi.mock('@/lib/hooks/use-records', () => ({
  useCreateRecord: () => ({ mutateAsync: createMutate, isPending: false }),
  useUpdateRecord: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteRecord: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAddRecordPhoto: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteRecordPhoto: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRotateRecordPhoto: () => ({ mutateAsync: vi.fn(), isPending: false }),
  fetchRecordWeather: (...args: unknown[]) => fetchWeather(...args),
}));

import { RecordEditor } from '@/components/records/record-editor';

beforeEach(() => {
  createMutate.mockReset();
  updateMutate.mockReset();
  fetchWeather.mockReset();
  global.URL.createObjectURL = vi.fn(() => 'blob:x');
  global.URL.revokeObjectURL = vi.fn();
});

describe('RecordEditor (new)', () => {
  it('defaults date to today, derives season, and prefills weather for default city', async () => {
    fetchWeather.mockResolvedValue({ temp_high: 24, temp_low: 16, condition: 'rain' });
    render(<RecordEditor today="2026-10-14" onSaved={vi.fn()} />);
    expect((screen.getByTestId('record-date') as HTMLInputElement).value).toBe('2026-10-14');
    expect(screen.getByTestId('record-season')).toHaveAttribute('data-value', 'fall');
    await waitFor(() => expect(fetchWeather).toHaveBeenCalledWith('杭州', '2026-10-14'));
    await waitFor(() =>
      expect((screen.getByTestId('record-temp-high') as HTMLInputElement).value).toBe('24')
    );
  });

  it('changing date re-derives season and refetches weather', async () => {
    fetchWeather.mockResolvedValue(null);
    render(<RecordEditor today="2026-10-14" onSaved={vi.fn()} />);
    fireEvent.change(screen.getByTestId('record-date'), { target: { value: '2026-07-01' } });
    expect(screen.getByTestId('record-season')).toHaveAttribute('data-value', 'summer');
    await waitFor(() => expect(fetchWeather).toHaveBeenCalledWith('杭州', '2026-07-01'));
  });

  it('save disabled without photos', () => {
    fetchWeather.mockResolvedValue(null);
    render(<RecordEditor today="2026-10-14" onSaved={vi.fn()} />);
    expect(screen.getByTestId('record-save')).toBeDisabled();
  });

  it('creates with photos and form fields; cleared weather sent as null', async () => {
    fetchWeather.mockResolvedValue({ temp_high: 24, temp_low: 16, condition: 'rain' });
    createMutate.mockResolvedValue({ id: 'r1' });
    const onSaved = vi.fn();
    render(<RecordEditor today="2026-10-14" onSaved={onSaved} />);
    await waitFor(() =>
      expect((screen.getByTestId('record-temp-high') as HTMLInputElement).value).toBe('24')
    );
    fireEvent.click(screen.getByTestId('record-clear-weather'));

    const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByTestId('record-photo-input'), { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('record-save'));

    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    const { input, photos } = createMutate.mock.calls[0][0];
    expect(photos).toEqual([file]);
    expect(input).toMatchObject({
      date: '2026-10-14', season: 'fall', city: '杭州', weather: null, item_ids: [],
    });
    expect(onSaved).toHaveBeenCalledWith({ id: 'r1' });
  });
});

describe('RecordEditor (edit)', () => {
  const record = {
    id: 'r1', date: '2026-10-01', season: 'summer', city: '已删除的城市',
    weather: { temp_high: 20, temp_low: 10, condition: 'sunny' },
    occasion: null, notes: null,
    photos: [{ id: 'p1', position: 0, image_url: 'u', thumbnail_url: 't' }],
    items: [], created_at: '', updated_at: '',
  };

  it('does not overwrite stored weather on mount and keeps a removed city', () => {
    render(<RecordEditor record={record} today="2026-10-14" onSaved={vi.fn()} />);
    expect(fetchWeather).not.toHaveBeenCalled();
    expect((screen.getByTestId('record-temp-high') as HTMLInputElement).value).toBe('20');
    expect(screen.getByTestId('record-city')).toHaveAttribute('data-value', '已删除的城市');
    expect(screen.getByTestId('record-season')).toHaveAttribute('data-value', 'summer');
  });

  it('last photo cannot be removed', () => {
    render(<RecordEditor record={record} today="2026-10-14" onSaved={vi.fn()} />);
    expect(screen.getByTestId('record-photo-remove')).toBeDisabled();
  });
});
