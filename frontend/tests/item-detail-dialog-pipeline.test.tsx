import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMock }));

type Mut = { mutateAsync: ReturnType<typeof vi.fn>; mutate: ReturnType<typeof vi.fn>; isPending: boolean };
const m = vi.hoisted(() => ({ muts: {} as Record<string, unknown>, live: undefined as unknown }));

vi.mock('@/lib/hooks/use-items', () => {
  const mk = (name: string) => () => {
    const cur = m.muts[name] as Mut | undefined;
    return cur ?? { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false };
  };
  const names = [
    'useUpdateItem', 'useDeleteItem', 'useReanalyzeItem', 'useRotateImage', 'useRemoveBackground',
    'useRestoreOriginal', 'useReplaceItemImage', 'useAddItemImage', 'useDeleteItemImage',
    'useSetPrimaryImage', 'useDetectCalibration', 'useApplyCalibration', 'useManualWhiteBalance',
    'useResetCalibration',
  ];
  const out: Record<string, unknown> = {};
  for (const n of names) out[n] = mk(n);
  out.useItem = () => ({ data: m.live });
  out.useItemWearStats = () => ({ data: undefined, isLoading: false });
  out.useItemWearHistory = () => ({ data: undefined, isLoading: false });
  return out;
});
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useBodyParts: () => [],
  useClothingColors: () => [],
  useClothingTypes: () => [],
  useStyles: () => [],
  useSeasons: () => [],
  useFormalityLabel: () => (v: string) => v,
  useMaterialLabel: () => (v: string) => v,
  useSubtypeLabel: () => (v: string) => v,
}));
vi.mock('@/lib/hooks/use-vocabulary', () => ({ useVocabManagement: () => ({}) }));
vi.mock('@/lib/hooks/use-features', () => ({ useFeatures: () => ({ data: {} }) }));
vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element
  default: (p: { alt?: string; src?: string }) => <img alt={p.alt ?? ''} src={String(p.src)} />,
}));
vi.mock('@/components/vocab/vocab-add-dialog', () => ({ VocabAddDialog: () => null }));
vi.mock('@/components/vocab/style-multi-select', () => ({ StyleMultiSelect: () => null }));
vi.mock('@/components/vocab/part-type-select', () => ({ PartTypeSelect: () => null }));
vi.mock('@/components/vocab/color-multi-select', () => ({ ColorMultiSelect: () => null }));
vi.mock('@/components/item-detail/item-records-section', () => ({ ItemRecordsSection: () => null }));
vi.mock('@/components/item-detail/item-companions-section', () => ({ ItemCompanionsSection: () => null }));
vi.mock('@/components/item-detail/wear-count-editor', () => ({ WearCountEditor: () => null }));
vi.mock('@/components/color-eyedropper', () => ({ ColorEyedropper: () => null }));
vi.mock('@/components/mask-brush-canvas', () => ({ default: () => null }));

import { ItemDetailDialog } from '@/components/item-detail-dialog';
import type { Item } from '@/lib/types';

const ITEM = {
  id: 'item-1',
  name: 'Shirt',
  type: 'shirt',
  status: 'ready',
  image_path: 'a.jpg',
  image_url: 'http://x/a.jpg',
  images: [],
  primary_colors: [],
  secondary_colors: [],
  style: [],
  tags: {},
  tagging_status: 'untagged',
  mask_path: 'a.mask.png',
} as unknown as Item;

function setMut(name: string, mutateAsync: ReturnType<typeof vi.fn>) {
  m.muts[name] = { mutateAsync, mutate: vi.fn(), isPending: false };
}

function renderDialog(item: Item = ITEM) {
  return render(<ItemDetailDialog item={item} open onOpenChange={vi.fn()} />);
}

beforeEach(() => {
  m.muts = {};
  m.live = undefined;
  Object.values(toastMock).forEach((f) => f.mockReset());
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('ItemDetailDialog pipeline feedback', () => {
  it('re-syncs the calibrate step when the item calibration_state changes', () => {
    const { rerender } = renderDialog({ ...ITEM, calibration_state: 'none' } as Item);
    expect(screen.getByTestId('pipeline-calibrate')).not.toBeDisabled();
    rerender(<ItemDetailDialog item={{ ...ITEM, calibration_state: 'done' } as Item} open onOpenChange={vi.fn()} />);
    expect(screen.getByTestId('pipeline-calibrate')).toBeDisabled();
    expect(screen.getByTestId('pipeline-calibrate').textContent).toMatch(/state\.done/);
  });

  it('re-syncs from the live (polled) item', () => {
    const base = { ...ITEM, calibration_state: 'none' } as Item;
    m.live = { ...base, calibration_state: 'done' };
    renderDialog(base);
    expect(screen.getByTestId('pipeline-calibrate')).toBeDisabled();
  });

  it('does not clobber pending while the box editor is open', async () => {
    setMut('useDetectCalibration', vi.fn().mockResolvedValue({ kind: 'gray', box: [10, 10, 60, 60] }));
    const base = { ...ITEM, calibration_state: 'none' } as Item;
    const { rerender } = renderDialog(base);
    fireEvent.click(screen.getByTestId('pipeline-calibrate'));
    await waitFor(() =>
      expect(screen.getByTestId('pipeline-calibrate').textContent).toMatch(/state\.pending/),
    );
    rerender(<ItemDetailDialog item={{ ...base, calibration_state: 'done' } as Item} open onOpenChange={vi.fn()} />);
    expect(screen.getByTestId('pipeline-calibrate').textContent).toMatch(/state\.pending/);
  });

  it('maps stage cutting to a running cutout step', () => {
    renderDialog({ ...ITEM, mask_path: null, status: 'processing', processing_kind: 'background_removal' } as unknown as Item);
    const cut = screen.getByTestId('pipeline-cutout');
    expect(cut).toBeDisabled();
    expect(cut.querySelector('[aria-label$="running"]')).not.toBeNull();
    expect(screen.getByTestId('pipeline-tag').querySelector('[aria-label$="running"]')).toBeNull();
  });

  it('maps failed-image to a failed cutout step', () => {
    renderDialog({ ...ITEM, mask_path: null, status: 'error', processing_kind: 'pipeline' } as unknown as Item);
    expect(screen.getByTestId('pipeline-cutout').getAttribute('title')).toMatch(/failed/);
    expect(screen.getByTestId('pipeline-tag').getAttribute('title')).toBeNull();
  });

  it('maps failed-tag to a failed tag step', () => {
    renderDialog({ ...ITEM, mask_path: 'a.mask.png', status: 'error', processing_kind: null, tagging_status: 'untagged' } as unknown as Item);
    expect(screen.getByTestId('pipeline-tag').getAttribute('title')).toMatch(/failed/);
    expect(screen.getByTestId('pipeline-cutout').getAttribute('title')).toBeNull();
  });

  it('shows calibration as done when the item has calibration_state=done', () => {
    renderDialog({ ...ITEM, calibration_state: 'done' } as Item);
    const btn = screen.getByTestId('pipeline-calibrate');
    expect(btn).toBeDisabled();
  });

  it('shows the tag step as running while the item is tagging', () => {
    renderDialog({ ...ITEM, status: 'processing', processing_kind: null } as unknown as Item);
    const tag = screen.getByTestId('pipeline-tag');
    expect(tag).toBeDisabled();
    expect(tag.querySelector('[aria-label$="running"]')).not.toBeNull();
    expect(screen.getByTestId('pipeline-cutout').querySelector('[aria-label$="running"]')).toBeNull();
  });

  it('toasts an error when calibration detection rejects', async () => {
    setMut('useDetectCalibration', vi.fn().mockRejectedValue(new Error('boom')));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-calibrate'));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
  });

  it('toasts an error when reset calibration rejects', async () => {
    setMut('useResetCalibration', vi.fn().mockRejectedValue(new Error('boom')));
    renderDialog();
    fireEvent.click(screen.getByText('pipeline.reset'));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
  });

  it('tag action calls the analyze mutation, not retag', async () => {
    const analyze = vi.fn().mockResolvedValue({ status: 'queued', job_id: 'j1' });
    setMut('useReanalyzeItem', analyze);
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(analyze).toHaveBeenCalledWith('item-1'));
    expect(toastMock.success).toHaveBeenCalledWith('pipeline.retagQueued');
  });

  it('treats already_queued as queued', async () => {
    setMut('useReanalyzeItem', vi.fn().mockResolvedValue({ status: 'already_queued' }));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('pipeline.retagQueued'));
  });

  it('shows an info toast when vision is disabled (deferred)', async () => {
    setMut('useReanalyzeItem', vi.fn().mockResolvedValue({ status: 'deferred' }));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(toastMock.info).toHaveBeenCalledWith('pipeline.retagDeferred'));
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('shows an info toast on cooldown', async () => {
    setMut('useReanalyzeItem', vi.fn().mockResolvedValue({ status: 'cooldown', retry_after_seconds: 30 }));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(toastMock.info).toHaveBeenCalledTimes(1));
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('toasts an error when the analyze call rejects', async () => {
    setMut('useReanalyzeItem', vi.fn().mockRejectedValue(new Error('boom')));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('drops a stale detection box after a successful rotate', async () => {
    setMut(
      'useDetectCalibration',
      vi.fn().mockResolvedValue({ kind: 'gray', box: [10, 10, 60, 60] }),
    );
    setMut('useRotateImage', vi.fn().mockResolvedValue({}));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-calibrate'));
    await screen.findByTestId('box-apply');

    fireEvent.click(screen.getByTitle('titles.rotateRight'));

    await waitFor(() => expect(screen.queryByTestId('box-apply')).toBeNull());
  });
});
