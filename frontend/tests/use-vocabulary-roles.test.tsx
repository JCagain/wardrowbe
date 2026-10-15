import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useVocabulary } from '@/lib/hooks/use-vocabulary';
import { roleForType, setTypeRoles } from '@/lib/vocab-roles';
import { api } from '@/lib/api';
import { VOCABULARY } from './fixtures/vocabulary';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ status: 'authenticated', data: { accessToken: 'test-token' } }),
}));

describe('useVocabulary -> role registry', () => {
  beforeEach(() => {
    setTypeRoles([]);
  });

  it('registers the loaded types so hook-free code can resolve roles', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(VOCABULARY);
    expect(roleForType('suit')).toBeUndefined();

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useVocabulary(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(roleForType('suit')).toBe('suit');
  });
});
