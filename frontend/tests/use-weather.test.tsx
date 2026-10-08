import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useWeather } from '@/lib/hooks/use-weather';

// The hook only fetches on an authenticated session carrying a token.
vi.mock('next-auth/react', () => ({
  useSession: () => ({
    status: 'authenticated',
    data: { accessToken: 'test-token' },
  }),
}));

function renderUseWeather() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useWeather(), { wrapper });
}

describe('useWeather', () => {
  it('returns the forecast when one is available', async () => {
    const payload = {
      temperature: 21,
      feels_like: 20,
      humidity: 40,
      precipitation_chance: 10,
      precipitation_mm: 0,
      wind_speed: 3,
      condition: 'clear',
      condition_code: 1,
      is_day: true,
      uv_index: 4,
      timestamp: '2026-10-08T00:00:00Z',
    };
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response);

    const { result } = renderUseWeather();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(payload);
  });

  // Location is optional (spec: 没设就空着), so the endpoint's "no coordinates"
  // 400 must resolve to null data rather than an error the global QueryCache
  // handler would toast on every page load.
  it('reports null instead of erroring when no location is set', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({
        detail: 'Location not set. Please provide coordinates or set your location in settings.',
      }),
    } as Response);

    const { result } = renderUseWeather();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it('still surfaces non-400 failures as errors', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Weather service temporarily unavailable' }),
    } as Response);

    const { result } = renderUseWeather();
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
