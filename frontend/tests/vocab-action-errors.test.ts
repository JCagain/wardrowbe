import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { runVocabAction } from '@/components/vocab/vocab-managed-chip';

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

// setup.ts's next-intl stub already renders keys as-is.
const t = (key: string) => key;

describe('runVocabAction', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports a failed mutation and returns false', async () => {
    const ok = await runVocabAction(t, () => Promise.reject(new Error('offline')));
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('actionFailed');
  });

  it('stays quiet and returns true on success', async () => {
    const ok = await runVocabAction(t, () => Promise.resolve());
    expect(ok).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('catches synchronous throws too', async () => {
    const ok = await runVocabAction(t, () => {
      throw new Error('boom');
    });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('actionFailed');
  });
});
