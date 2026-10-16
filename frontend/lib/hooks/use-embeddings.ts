'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';
import type { EmbeddingStatus } from '@/lib/types';

const STATUS_KEY = ['embeddings', 'status'] as const;

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function useEmbeddingStatus() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: STATUS_KEY,
    queryFn: () => api.get<EmbeddingStatus>('/embeddings/status'),
    enabled: status !== 'loading',
    staleTime: 30_000,
    refetchInterval: (query) => (query.state.data && query.state.data.job !== 'idle' ? 3000 : false),
  });
}

export function useSyncEmbeddings() {
  useSetTokenIfAvailable();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rebuild }: { rebuild: boolean }) =>
      api.post<{ queued: boolean; job: EmbeddingStatus['job'] }>('/embeddings/sync', { rebuild }),
    onSuccess: () => qc.invalidateQueries({ queryKey: STATUS_KEY }),
  });
}
