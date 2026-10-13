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
const m = vi.hoisted(() => ({ muts: {} as Record<string, unknown> }));

vi.mock('@/lib/hooks/use-items', () => {
  const mk = (name: string) => () => {
    const cur = m.muts[name] as Mut | undefined;
    return cur ?? { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false };
  };
  const names = [
    'useUpdateItem', 'useDeleteItem', 'useReanalyzeItem', 'useRotateImage', 'useRemoveBackground',
    'useRestoreOriginal', 'useReplaceItemImage', 'useAddItemImage', 'useDeleteItemImage',
    'useSetPrimaryImage', 'useDetectCalibration', 'useApplyCalibration', 'useManualWhiteBalance',
    'useResetCalibration', 'useRetagItem',
  ];
  const out: Record<string, unknown> = {};
  for (const n of names) out[n] = mk(n);
  out.useItemWearStats = () => ({ data: undefined, isLoading: false });
  out.useItemWearHistory = () => ({ data: undefined, isLoading: false });
  return out;
});
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useBodyParts: () => [],
  useClothingColors: () => [],
  useClothingTypes: () => [],
  useStyles: () => [],
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

function renderDialog() {
  return render(<ItemDetailDialog item={ITEM} open onOpenChange={vi.fn()} />);
}

beforeEach(() => {
  m.muts = {};
  Object.values(toastMock).forEach((f) => f.mockReset());
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('ItemDetailDialog pipeline feedback', () => {
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

  it('toasts an error when retag rejects', async () => {
    setMut('useRetagItem', vi.fn().mockRejectedValue(new Error('boom')));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('toasts success when retag is queued', async () => {
    setMut('useRetagItem', vi.fn().mockResolvedValue(undefined));
    renderDialog();
    fireEvent.click(screen.getByTestId('pipeline-tag'));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledTimes(1));
    expect(toastMock.error).not.toHaveBeenCalled();
  });
});
