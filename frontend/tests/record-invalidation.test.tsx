import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 't' }, status: 'authenticated' }),
}));
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  api: { delete: vi.fn().mockResolvedValue(undefined), patch: vi.fn().mockResolvedValue({}) },
}));

import { useDeleteRecord } from '@/lib/hooks/use-records';
import { useDeleteItem, useUpdateItem } from '@/lib/hooks/use-items';

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const keys = () => spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[0]);
  return { wrapper, keys };
}

describe('stale-data invalidation', () => {
  it('record mutation refreshes analytics, item, wear-stats, companions and records', async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useDeleteRecord(), { wrapper });
    await result.current.mutateAsync('r1');
    expect(keys()).toEqual(expect.arrayContaining(['analytics', 'item', 'wear-stats', 'item-companions', 'records']));
  });

  it('item update refreshes analytics (manual wear_count moves total wears)', async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useUpdateItem(), { wrapper });
    await result.current.mutateAsync({ id: 'i1', data: { wear_count: 5 } });
    expect(keys()).toContain('analytics');
  });

  it('item delete refreshes companions and records', async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useDeleteItem(), { wrapper });
    await result.current.mutateAsync('i1');
    expect(keys()).toEqual(expect.arrayContaining(['item-companions', 'records']));
  });
});
