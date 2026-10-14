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
    'useResetCalibration',
  ];
  const out: Record<string, unknown> = {};
  for (const n of names) out[n] = mk(n);
  out.useItemWearStats = () => ({ data: undefined, isLoading: false });
  out.useItemWearHistory = () => ({ data: undefined, isLoading: false });
  return out;
});
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useBodyParts: () => [],
  useClothingColors: () => [
    { value: 'black', label: '黑', name: '黑', hex: '#000000' },
    { value: 'white', label: '白', name: '白', hex: '#ffffff' },
  ],
  useClothingTypes: () => [],
  useStyles: () => [],
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


function renderWithTags(tags: Record<string, unknown>) {
  const item = { ...ITEM, tags } as unknown as Item;
  return render(<ItemDetailDialog item={item} open onOpenChange={vi.fn()} />);
}

beforeEach(() => {
  m.muts = {};
  toastMock.error.mockClear();
});

describe('ItemDetailDialog AI color tags', () => {
  it('shows AI primary and secondary colors by their Chinese names', async () => {
    renderWithTags({ primary_colors: ['black'], secondary_colors: ['white'] });
    expect(await screen.findByText('黑')).toBeInTheDocument();
    expect(screen.getByText('白')).toBeInTheDocument();
    expect(screen.queryByText('black')).not.toBeInTheDocument();
  });

  it('still shows legacy tags.colors for items tagged before the contract change', async () => {
    renderWithTags({ colors: ['black'] });
    expect(await screen.findByText('黑')).toBeInTheDocument();
  });

  it('falls back to the slug for a color missing from the vocabulary', async () => {
    renderWithTags({ primary_colors: ['chartreuse'] });
    expect(await screen.findByText('chartreuse')).toBeInTheDocument();
  });

  it('ignores legacy tags.colors once the new keys are present', async () => {
    renderWithTags({ primary_colors: ['black'], colors: ['white'] });
    expect(await screen.findByText('黑')).toBeInTheDocument();
    expect(screen.queryByText('白')).not.toBeInTheDocument();
    expect(screen.queryByText('white')).not.toBeInTheDocument();
  });
});

describe('ItemDetailDialog primary color required', () => {
  async function openEditAndSave(primary: string[]) {
    const mutateAsync = vi.fn().mockResolvedValue({});
    m.muts = { useUpdateItem: { mutateAsync, mutate: vi.fn(), isPending: false } };
    const item = { ...ITEM, primary_colors: primary } as unknown as Item;
    render(<ItemDetailDialog item={item} open onOpenChange={vi.fn()} />);
    fireEvent.click(await screen.findByTitle('actions.editItem'));
    fireEvent.click(await screen.findByRole('button', { name: /save/i }));
    return mutateAsync;
  }

  it('refuses to save with no primary color and shows an error toast', async () => {
    const mutateAsync = await openEditAndSave([]);
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('primaryColorRequired'));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('saves normally when a primary color is set', async () => {
    const mutateAsync = await openEditAndSave(['black']);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(toastMock.error).not.toHaveBeenCalledWith('primaryColorRequired');
  });
});
