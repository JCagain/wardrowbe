import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

import { SuggestPanel } from '@/components/records/suggest-panel';
import type { GarmentRegion, SuggestCandidate } from '@/lib/types';

const region: GarmentRegion = { body_part: 'tops', box: { l: 0, t: 0, r: 50, b: 50 }, source: 'auto' };
const status = { configured: true, available: true, model: 'm', total: 3, embedded: 3, stale: 0, job: 'idle' };
const cand = (id: string, verdict: SuggestCandidate['verdict'] = 'same'): SuggestCandidate => ({
  id, type: 'shirt', name: `n-${id}`, primary_colors: ['blue'], thumbnail_url: null, cosine: 0.9, verdict, lifecycle: 'active',
});

function mount(props: Partial<React.ComponentProps<typeof SuggestPanel>> = {}) {
  const onToggle = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SuggestPanel recordId="r1" photoId="p1" region={region} linkedIds={new Set()} onToggle={onToggle} {...props} />
    </QueryClientProvider>,
  );
  return { onToggle };
}

// 状态查询返回前按钮是禁用的；等它可用再点，否则点击是空操作
async function clickRun() {
  const btn = await screen.findByTestId('suggest-run');
  await waitFor(() => expect(btn).not.toBeDisabled());
  fireEvent.click(btn);
}

describe('SuggestPanel', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); get.mockResolvedValue(status); });

  it('runs for the selected region and lists candidates in order', async () => {
    post.mockResolvedValue({ candidates: [cand('a'), cand('b', 'similar')], recall_count: 2, part_filtered: true, reranked: true, rerank_error: null });
    mount();
    await clickRun();
    await screen.findByTestId('suggest-results');
    expect(post).toHaveBeenCalledWith('/records/r1/photos/p1/suggest', { region, rerank: true }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    const ids = screen.getAllByTestId(/^suggest-candidate-/).map((el) => el.getAttribute('data-testid'));
    expect(ids).toEqual(['suggest-candidate-a', 'suggest-candidate-b']);
    expect(screen.getByTestId('suggest-verdict-b')).toHaveTextContent('verdict.similar');
  });

  it('clicking a candidate toggles it into the record (no API write)', async () => {
    post.mockResolvedValue({ candidates: [cand('a')], recall_count: 1, part_filtered: true, reranked: true, rerank_error: null });
    const { onToggle } = mount();
    await clickRun();
    fireEvent.click(await screen.findByTestId('suggest-candidate-a'));
    expect(onToggle).toHaveBeenCalledWith(expect.objectContaining({ id: 'a', type: 'shirt' }));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('marks already-linked candidates as pressed', async () => {
    post.mockResolvedValue({ candidates: [cand('a')], recall_count: 1, part_filtered: true, reranked: true, rerank_error: null });
    mount({ linkedIds: new Set(['a']) });
    await clickRun();
    expect(await screen.findByTestId('suggest-candidate-a')).toHaveAttribute('aria-pressed', 'true');
  });

  it('greys out when embedding is unavailable', async () => {
    get.mockResolvedValue({ ...status, available: false });
    mount();
    expect(await screen.findByTestId('suggest-unavailable')).toBeInTheDocument();
    expect(screen.getByTestId('suggest-run')).toBeDisabled();
  });

  it('disabled with no selected region', async () => {
    mount({ region: null });
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.getByTestId('suggest-run')).toBeDisabled();
  });

  it('cancel aborts and drops the late result', async () => {
    let resolve!: (v: unknown) => void;
    post.mockImplementation(() => new Promise((r) => { resolve = r; }));
    mount();
    await clickRun();
    expect(await screen.findByTestId('suggest-running')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('suggest-cancel'));
    const signal = post.mock.calls[0][2].signal as AbortSignal;
    expect(signal.aborted).toBe(true);
    await act(async () => resolve({ candidates: [cand('late')], recall_count: 1, part_filtered: true, reranked: true, rerank_error: null }));
    expect(screen.queryByTestId('suggest-results')).toBeNull();
    expect(screen.queryByTestId('suggest-running')).toBeNull();
  });

  it('shows not-reranked note, empty state and errors', async () => {
    post.mockResolvedValueOnce({ candidates: [cand('a', null)], recall_count: 1, part_filtered: false, reranked: false, rerank_error: 'x' });
    mount();
    await clickRun();
    expect(await screen.findByTestId('suggest-not-reranked')).toBeInTheDocument();
    post.mockResolvedValueOnce({ candidates: [], recall_count: 0, part_filtered: false, reranked: false, rerank_error: null });
    await clickRun();
    expect(await screen.findByTestId('suggest-empty')).toBeInTheDocument();
    post.mockRejectedValueOnce(new Error('boom'));
    await clickRun();
    expect(await screen.findByTestId('suggest-error')).toHaveTextContent('boom');
  });

  it('clears results when the region changes', async () => {
    post.mockResolvedValue({ candidates: [cand('a')], recall_count: 1, part_filtered: true, reranked: true, rerank_error: null });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <SuggestPanel recordId="r1" photoId="p1" region={region} linkedIds={new Set()} onToggle={vi.fn()} />
      </QueryClientProvider>,
    );
    await clickRun();
    await screen.findByTestId('suggest-results');
    rerender(
      <QueryClientProvider client={qc}>
        <SuggestPanel recordId="r1" photoId="p1" region={{ ...region, box: { l: 1, t: 1, r: 60, b: 60 } }} linkedIds={new Set()} onToggle={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId('suggest-results')).toBeNull();
  });
});
