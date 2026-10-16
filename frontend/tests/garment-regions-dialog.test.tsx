import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { accessToken: 't' }, status: 'authenticated' }),
}));

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();
vi.mock('@/lib/api', async (orig) => {
  const mod = await orig<typeof import('@/lib/api')>();
  return { ...mod, api: { ...mod.api, get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a), put: (...a: unknown[]) => put(...a) } };
});

import { GarmentRegionsDialog } from '@/components/records/garment-regions-dialog';
import type { GarmentRegion, RecordPhoto } from '@/lib/types';

const box = { l: 0, t: 0, r: 99, b: 99 };
const r1: GarmentRegion = { body_part: 'tops', box, source: 'auto' };
const r2: GarmentRegion = { body_part: 'bottoms', box, source: 'auto' };

function photo(regions: GarmentRegion[] | null): RecordPhoto {
  return { id: 'p1', position: 0, image_url: 'data:image/png;base64,iVBORw0KGgo=', garment_regions: regions };
}

function mount(p: RecordPhoto, onOpenChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <GarmentRegionsDialog recordId="r1" photo={p} open onOpenChange={onOpenChange} linkedIds={new Set()} onToggleItem={vi.fn()} />
    </QueryClientProvider>,
  );
  return onOpenChange;
}

const response = (regions: GarmentRegion[]) => ({ photo_id: 'p1', width: 100, height: 100, regions });

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ configured: true, available: true, model: 'm', total: 1, embedded: 1, stale: 0, job: 'idle' });
  post.mockReset();
  put.mockReset();
});
afterEach(() => vi.restoreAllMocks());

describe('GarmentRegionsDialog', () => {
  it('renders one chip per stored region', () => {
    mount(photo([r1, r2]));
    expect(screen.getByTestId('region-chip-0')).toBeInTheDocument();
    expect(screen.getByTestId('region-chip-1')).toBeInTheDocument();
    expect(screen.queryByTestId('region-chip-2')).toBeNull();
  });

  it('detect posts to the detect endpoint and replaces the boxes (no confirm when empty)', async () => {
    const confirm = vi.spyOn(window, 'confirm');
    post.mockResolvedValue(response([r1, r2]));
    mount(photo(null));
    fireEvent.click(screen.getByTestId('regions-detect'));
    await waitFor(() => expect(screen.getByTestId('region-chip-1')).toBeInTheDocument());
    expect(post.mock.calls[0][0]).toBe('/records/r1/photos/p1/garment-regions/detect');
    expect(confirm).not.toHaveBeenCalled();
  });

  it('detect does not invalidate record queries (nothing changed server-side); save does', async () => {
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    post.mockResolvedValue(response([r1]));
    put.mockResolvedValue(response([r1]));
    render(
      <QueryClientProvider client={qc}>
        <GarmentRegionsDialog recordId="r1" photo={photo(null)} open onOpenChange={vi.fn()} linkedIds={new Set()} onToggleItem={vi.fn()} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByTestId('regions-detect'));
    await waitFor(() => expect(screen.getByTestId('region-chip-0')).toBeInTheDocument());
    expect(put).not.toHaveBeenCalled();
    expect(spy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('regions-save'));
    await waitFor(() => expect(put).toHaveBeenCalled());
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it('shows the backend detail on detect failure and stays open', async () => {
    post.mockRejectedValue(Object.assign(new Error('X_DETAIL'), { status: 502 }));
    const onOpenChange = mount(photo(null));
    fireEvent.click(screen.getByTestId('regions-detect'));
    await waitFor(() => expect(screen.getByTestId('regions-error')).toHaveTextContent('X_DETAIL'));
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('save PUTs the current boxes and closes', async () => {
    put.mockResolvedValue(response([r1]));
    const onOpenChange = mount(photo([r1]));
    fireEvent.click(screen.getByTestId('regions-save'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(put).toHaveBeenCalledWith('/records/r1/photos/p1/garment-regions', { regions: [r1] });
  });

  it('cancel aborts the in-flight detect and re-enables the button', async () => {
    let signal: AbortSignal | undefined;
    post.mockImplementation(
      (_u: string, _d: unknown, opts: { signal: AbortSignal }) =>
        new Promise((_res, rej) => {
          signal = opts.signal;
          opts.signal.addEventListener('abort', () => rej(new Error('aborted')));
        }),
    );
    mount(photo(null));
    fireEvent.click(screen.getByTestId('regions-detect'));
    await waitFor(() => expect(screen.getByTestId('regions-detect')).toBeDisabled());
    await act(async () => {
      fireEvent.click(screen.getByTestId('regions-cancel'));
    });
    expect(signal?.aborted).toBe(true);
    expect(screen.getByTestId('regions-detect')).not.toBeDisabled();
    expect(screen.queryByTestId('regions-error')).toBeNull();
  });

  it('asks before replacing existing boxes: declined sends nothing, accepted sends', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    post.mockResolvedValue(response([r2]));
    mount(photo([r1]));
    fireEvent.click(screen.getByTestId('regions-detect'));
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('regions-detect'));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(confirm).toHaveBeenCalledTimes(2);
  });
});

describe('GarmentRegionsDialog suggest panel', () => {
  it('suggest-run is enabled only once a box is selected', async () => {
    mount(photo([r1]));
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.getByTestId('suggest-run')).toBeDisabled();
    fireEvent.click(screen.getByTestId('region-chip-0'));
    await waitFor(() => expect(screen.getByTestId('suggest-run')).not.toBeDisabled());
  });
});

describe('GarmentRegionsDialog stability', () => {
  it('disables save while detecting', async () => {
    post.mockImplementation(() => new Promise(() => {}));
    mount(photo(null));
    fireEvent.click(screen.getByTestId('regions-detect'));
    await waitFor(() => expect(screen.getByTestId('regions-save')).toBeDisabled());
  });

  it('keeps the initial image src when the photo prop gets a new signed url', () => {
    const qc = new QueryClient();
    const ui = (p: RecordPhoto) => (
      <QueryClientProvider client={qc}>
        <GarmentRegionsDialog recordId="r1" photo={p} open onOpenChange={vi.fn()} linkedIds={new Set()} onToggleItem={vi.fn()} />
      </QueryClientProvider>
    );
    const { rerender } = render(ui({ ...photo([r1]), image_url: 'data:image/png;base64,AAAA' }));
    rerender(ui({ ...photo([r1]), image_url: 'data:image/png;base64,BBBB' }));
    expect(document.querySelector('img')!.getAttribute('src')).toBe('data:image/png;base64,AAAA');
  });
});
