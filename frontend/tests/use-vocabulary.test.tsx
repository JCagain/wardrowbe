import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useVocabulary } from '@/lib/hooks/use-vocabulary';

// The hook only fetches on an authenticated session carrying a token.
vi.mock('next-auth/react', () => ({
  useSession: () => ({
    status: 'authenticated',
    data: { accessToken: 'test-token' },
  }),
}));

describe('useVocabulary', () => {
  it('fetches the runtime vocabulary', async () => {
    const payload = {
      body_parts: [],
      types: [],
      colors: { families: [], values: [] },
      seasons: [],
      styles: [],
      materials: [],
      formality: [],
    };
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response);

    const client = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useVocabulary(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(payload);
  });
});
