import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const addCity = vi.fn();
const removeCity = vi.fn();
const updatePrefs = vi.fn();
let addPending = false;

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/hooks/use-preferences', () => ({
  usePreferences: () => ({
    data: {
      cities: [
        { name: '杭州', latitude: 30.27, longitude: 120.15 },
        { name: '香港', latitude: 22.31, longitude: 114.16 },
      ],
      default_city: '杭州',
    },
  }),
  useUpdatePreferences: () => ({ mutate: updatePrefs, isPending: false }),
  useAddCity: () => ({ mutateAsync: addCity, isPending: addPending }),
  useRemoveCity: () => ({ mutate: removeCity, isPending: false }),
}));

import { CitySettingsCard } from '@/components/settings/city-settings-card';

beforeEach(() => {
  addCity.mockReset();
  removeCity.mockReset();
  updatePrefs.mockReset();
  addPending = false;
});

describe('CitySettingsCard', () => {
  it('lists cities', () => {
    render(<CitySettingsCard />);
    expect(screen.getAllByTestId('city-row')).toHaveLength(2);
  });

  it('adds trimmed name', async () => {
    addCity.mockResolvedValueOnce({});
    render(<CitySettingsCard />);
    fireEvent.change(screen.getByTestId('city-add-input'), { target: { value: ' 上海 ' } });
    fireEvent.click(screen.getByTestId('city-add-button'));
    expect(addCity).toHaveBeenCalledWith('上海');
  });

  it('removes a city', () => {
    render(<CitySettingsCard />);
    fireEvent.click(screen.getAllByTestId('city-remove')[1]);
    expect(removeCity).toHaveBeenCalledWith('香港', expect.anything());
  });

  it('Enter does not submit while an add is pending', () => {
    addPending = true;
    render(<CitySettingsCard />);
    const input = screen.getByTestId('city-add-input');
    fireEvent.change(input, { target: { value: '上海' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(addCity).not.toHaveBeenCalled();
  });
});
