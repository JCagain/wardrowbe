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

// 3 s while a job runs; 30 s while idle with pending items (the cron starts the follow-up job
// within a minute and the card would otherwise never notice); otherwise stop.
export function statusRefetchInterval(data: EmbeddingStatus | undefined): number | false {
  if (!data) return false;
  if (data.job !== 'idle') return 3000;
  if (data.available && data.stale > 0) return 30_000;
  return false;
}

export function useEmbeddingStatus() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: STATUS_KEY,
    queryFn: () => api.get<EmbeddingStatus>('/embeddings/status'),
    enabled: status !== 'loading',
    staleTime: 30_000,
    refetchInterval: (query) => statusRefetchInterval(query.state.data),
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
