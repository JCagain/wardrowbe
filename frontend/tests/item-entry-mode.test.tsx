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
    'useResetCalibration', 'useCancelAnalysis',
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
vi.mock('@/lib/hooks/use-vocabulary', () => ({ useVocabManagement: () => ({ handlersFor: () => ({}), openAdd: vi.fn() }) }));
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
import { entryYearMonth } from '@/lib/purchase-date';
import type { Item } from '@/lib/types';

const ITEM = {
  id: 'item-1',
  name: 'Shirt',
  type: 'shirt',
  status: 'ready',
  image_path: 'a.jpg',
  image_url: 'http://x/a.jpg',
  additional_images: [],
  primary_colors: ['blue'],
  secondary_colors: [],
  style: [],
  tags: {},
  calibration_state: 'done',
  tagging_status: 'tagged',
  tagged_at: '2026-10-19T00:00:00Z',
  mask_path: 'a.mask.png',
  purchase_date: '2025-03-01',
  purchase_date_precision: 'month',
  lifecycle: 'active',
} as unknown as Item;

const TAGGING = {
  ...ITEM,
  status: 'processing',
  processing_kind: null,
  tagging_status: 'pending',
  tagged_at: null,
  ai_started_at: new Date().toISOString(),
} as unknown as Item;

function setMut(name: string, mutateAsync: ReturnType<typeof vi.fn>) {
  m.muts[name] = { mutateAsync, mutate: vi.fn(), isPending: false };
}

function renderEntry(item: Item, onOpenChange = vi.fn()) {
  const utils = render(
    <ItemDetailDialog item={item} open onOpenChange={onOpenChange} mode="entry" />,
  );
  return { ...utils, onOpenChange };
}

beforeEach(() => {
  m.muts = {};
  m.live = undefined;
  Object.values(toastMock).forEach((f) => f.mockReset());
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('ItemDetailDialog entry mode', () => {
  it('save while tagging cancels the analysis before patching', async () => {
    const order: string[] = [];
    setMut('useCancelAnalysis', vi.fn(async () => { order.push('cancel'); return {}; }));
    setMut('useUpdateItem', vi.fn(async () => { order.push('update'); return {}; }));
    const { onOpenChange } = renderEntry(TAGGING);

    fireEvent.click(screen.getByTestId('entry-save'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(order).toEqual(['cancel', 'update']);
  });

  // 轮询的 status 可能晚 ~2s：props 里是 ready，也照样先取消再 PATCH
  it('save still cancels before patching when the polled status is stale (ready)', async () => {
    const order: string[] = [];
    setMut('useCancelAnalysis', vi.fn(async (id: string) => { order.push(`cancel:${id}`); return {}; }));
    setMut('useUpdateItem', vi.fn(async () => { order.push('update'); return {}; }));
    const { onOpenChange } = renderEntry(ITEM);

    fireEvent.click(screen.getByTestId('entry-save'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(order).toEqual(['cancel:item-1', 'update']);
  });

  it('cancel failure aborts the save and says so (T6c)', async () => {
    const update = vi.fn().mockResolvedValue({});
    setMut('useCancelAnalysis', vi.fn().mockRejectedValue(new Error('redis down')));
    setMut('useUpdateItem', update);
    const { onOpenChange } = renderEntry(TAGGING);

    fireEvent.click(screen.getByTestId('entry-save'));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('entry.cancelError'));
    expect(update).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('patch failure toasts an error and keeps the window open', async () => {
    setMut('useCancelAnalysis', vi.fn().mockResolvedValue({}));
    setMut('useUpdateItem', vi.fn().mockRejectedValue(new Error('500')));
    const { onOpenChange } = renderEntry(ITEM);

    fireEvent.click(screen.getByTestId('entry-save'));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('entry.saveError'));
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('entry-save')).not.toBeDisabled();
  });

  it('discard cancels then deletes', async () => {
    const order: string[] = [];
    setMut('useCancelAnalysis', vi.fn(async () => { order.push('cancel'); return {}; }));
    setMut('useDeleteItem', vi.fn(async (id: string) => { order.push(`delete:${id}`); }));
    const { onOpenChange } = renderEntry(TAGGING);

    fireEvent.click(screen.getByTestId('entry-discard'));
    fireEvent.click(await screen.findByTestId('entry-discard-confirm'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(order).toEqual(['cancel', 'delete:item-1']);
  });

  it('discard still deletes when cancel throws (T6c)', async () => {
    const del = vi.fn().mockResolvedValue(undefined);
    setMut('useCancelAnalysis', vi.fn().mockRejectedValue(new Error('redis down')));
    setMut('useDeleteItem', del);
    const { onOpenChange } = renderEntry(TAGGING);

    fireEvent.click(screen.getByTestId('entry-discard'));
    fireEvent.click(await screen.findByTestId('entry-discard-confirm'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(del).toHaveBeenCalledWith('item-1');
  });

  it('closing asks keep/delete/cancel instead of closing', async () => {
    const del = vi.fn().mockResolvedValue(undefined);
    setMut('useDeleteItem', del);
    const { onOpenChange } = renderEntry(ITEM);

    fireEvent.click(screen.getByTitle('close'));
    expect(await screen.findByTestId('entry-close-keep')).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();

    // 继续编辑：不关窗
    fireEvent.click(screen.getByTestId('entry-close-cancel'));
    await waitFor(() => expect(screen.queryByTestId('entry-close-keep')).toBeNull());
    expect(onOpenChange).not.toHaveBeenCalled();

    // 保留在衣橱：关窗、不删
    fireEvent.click(screen.getByTitle('close'));
    fireEvent.click(await screen.findByTestId('entry-close-keep'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(del).not.toHaveBeenCalled();
  });

  it('close-delete cancels then deletes, even when the polled status is ready', async () => {
    const order: string[] = [];
    setMut('useCancelAnalysis', vi.fn(async () => { order.push('cancel'); return {}; }));
    setMut('useDeleteItem', vi.fn(async (id: string) => { order.push(`delete:${id}`); }));
    const { onOpenChange } = renderEntry(ITEM);

    fireEvent.click(screen.getByTitle('close'));
    fireEvent.click(await screen.findByTestId('entry-close-delete'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(order).toEqual(['cancel', 'delete:item-1']);
  });

  it('form waits while processing and offers fill-now', () => {
    renderEntry(TAGGING);

    expect(screen.getByTestId('entry-status').textContent).toMatch(/entry\.status\.tagging/);
    expect(screen.getByTestId('entry-fill-now')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Shirt')).toBeDisabled();
    expect(screen.getByTestId('entry-save')).not.toBeDisabled();
    // 查看态动作在 entry 模式下隐藏
    expect(screen.queryByTitle('titles.toggleFavorite')).toBeNull();
    expect(screen.queryByText('actions.deleteItem')).toBeNull();

    fireEvent.click(screen.getByTestId('entry-fill-now'));
    expect(screen.queryByTestId('entry-fill-now')).toBeNull();
    expect(screen.getByDisplayValue('Shirt')).not.toBeDisabled();
  });

  it('empty purchase date is defaulted to the entry month on init', () => {
    renderEntry({ ...ITEM, purchase_date: null, purchase_date_precision: null } as unknown as Item);
    expect(screen.getByDisplayValue(entryYearMonth())).toBeInTheDocument();
  });

  it('a user-edited form is not overwritten when tagging finishes; overwrite is offered', () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <ItemDetailDialog item={TAGGING} open onOpenChange={onOpenChange} mode="entry" />,
    );
    fireEvent.click(screen.getByTestId('entry-fill-now'));
    fireEvent.change(screen.getByDisplayValue('Shirt'), { target: { value: 'My shirt' } });

    rerender(
      <ItemDetailDialog
        item={{ ...ITEM, name: 'AI shirt' } as Item}
        open
        onOpenChange={onOpenChange}
        mode="entry"
      />,
    );
    expect(screen.getByDisplayValue('My shirt')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('entry-overwrite'));
    expect(screen.getByDisplayValue('AI shirt')).toBeInTheDocument();
  });

  it('a clean form refreshes automatically when tagging finishes', () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <ItemDetailDialog item={TAGGING} open onOpenChange={onOpenChange} mode="entry" />,
    );
    fireEvent.click(screen.getByTestId('entry-fill-now'));
    rerender(
      <ItemDetailDialog
        item={{ ...ITEM, name: 'AI shirt' } as Item}
        open
        onOpenChange={onOpenChange}
        mode="entry"
      />,
    );
    expect(screen.getByDisplayValue('AI shirt')).toBeInTheDocument();
    expect(screen.queryByTestId('entry-overwrite')).toBeNull();
  });
});
