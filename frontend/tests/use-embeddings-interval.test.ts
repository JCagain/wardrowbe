import { describe, expect, it } from 'vitest';

import { statusRefetchInterval } from '@/lib/hooks/use-embeddings';
import type { EmbeddingStatus } from '@/lib/types';

const base: EmbeddingStatus = { configured: true, available: true, model: 'm', total: 3, embedded: 3, stale: 0, job: 'idle' };

describe('statusRefetchInterval', () => {
  it('does not poll before data arrives', () => {
    expect(statusRefetchInterval(undefined)).toBe(false);
  });

  it('polls every 3 s while a job is queued or running', () => {
    expect(statusRefetchInterval({ ...base, job: 'queued' })).toBe(3000);
    expect(statusRefetchInterval({ ...base, job: 'running', stale: 2 })).toBe(3000);
  });

  it('polls every 30 s when idle with pending items on an available service', () => {
    expect(statusRefetchInterval({ ...base, stale: 2 })).toBe(30_000);
  });

  it('stops when idle and nothing is pending', () => {
    expect(statusRefetchInterval(base)).toBe(false);
  });

  it('stops when idle with pending items but the service is unavailable', () => {
    expect(statusRefetchInterval({ ...base, stale: 2, available: false })).toBe(false);
  });
});
