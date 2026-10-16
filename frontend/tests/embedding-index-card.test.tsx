import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 't' }, status: 'authenticated' }),
}));
const get = vi.fn();
const post = vi.fn();
vi.mock('@/lib/api', async (orig) => {
  const mod = await orig<typeof import('@/lib/api')>();
  return { ...mod, api: { ...mod.api, get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } };
});

import { EmbeddingIndexCard } from '@/components/settings/embedding-index-card';

const base = { configured: true, available: true, model: 'm', total: 10, embedded: 7, stale: 3, job: 'idle' };

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={qc}><EmbeddingIndexCard /></QueryClientProvider>);
}

describe('EmbeddingIndexCard', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); });

  it('shows counts and sync triggers POST without rebuild', async () => {
    get.mockResolvedValue(base);
    post.mockResolvedValue({ queued: true, job: 'queued' });
    mount();
    expect(await screen.findByTestId('embedding-counts')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('embedding-sync'));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/embeddings/sync', { rebuild: false }));
  });

  it('rebuild asks for confirmation first', async () => {
    get.mockResolvedValue(base);
    post.mockResolvedValue({ queued: true, job: 'queued' });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    mount();
    fireEvent.click(await screen.findByTestId('embedding-rebuild'));
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('embedding-rebuild'));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/embeddings/sync', { rebuild: true }));
    expect(confirm).toHaveBeenCalledWith('rebuildConfirm');
  });

  it('unconfigured hides actions', async () => {
    get.mockResolvedValue({ ...base, configured: false, available: false, model: null });
    mount();
    expect(await screen.findByTestId('embedding-unconfigured')).toBeInTheDocument();
    expect(screen.queryByTestId('embedding-sync')).toBeNull();
  });

  it('unavailable disables actions and says so', async () => {
    get.mockResolvedValue({ ...base, available: false });
    mount();
    expect(await screen.findByTestId('embedding-unavailable')).toBeInTheDocument();
    expect(screen.getByTestId('embedding-sync')).toBeDisabled();
    expect(screen.getByTestId('embedding-rebuild')).toBeDisabled();
  });

  it('shows job state while running', async () => {
    get.mockResolvedValue({ ...base, job: 'running' });
    mount();
    expect(await screen.findByTestId('embedding-job')).toHaveTextContent('job.running');
  });
});
