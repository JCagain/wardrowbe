import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 't' }, status: 'authenticated' }),
}));

import { fetchRecordWeather, useCreateRecord } from '@/lib/hooks/use-records';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('use-records', () => {
  it('create posts multipart with data JSON and every photo', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 'r1' }), { status: 201 })
    );
    const { result } = renderHook(() => useCreateRecord(), { wrapper });
    const photo = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
    await result.current.mutateAsync({ input: { date: '2026-10-14', item_ids: [] }, photos: [photo, photo] });

    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/records');
    const body = (init as RequestInit).body as FormData;
    expect(JSON.parse(body.get('data') as string)).toEqual({ date: '2026-10-14', item_ids: [] });
    expect(body.getAll('photos')).toHaveLength(2);
  });

  it('fetchRecordWeather returns null weather as null', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ weather: null }), { status: 200 })
    );
    await expect(fetchRecordWeather('杭州', '2026-10-10')).resolves.toBeNull();
    const [url] = vi.mocked(global.fetch).mock.calls[0];
    expect(String(url)).toContain('/api/v1/records/weather?city=%E6%9D%AD%E5%B7%9E&date=2026-10-10');
  });
});
