import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StudioEditorPage from '@/app/dashboard/outfits/new/page';
import type { Vocabulary } from '@/lib/hooks/use-vocabulary';
import { setTypeRoles } from '@/lib/vocab-roles';
import { VOCABULARY } from './fixtures/vocabulary';

// The studio sorts, slots and warns by type role, and roles come from the live
// vocabulary (lib/vocab-roles, filled by useVocabulary's queryFn). So the page
// must not put anything on the canvas until the vocabulary is in — otherwise a
// direct load orders the canvas against an empty role map and never re-sorts.

const vocab = vi.hoisted(() => ({
  state: { data: undefined, isError: false, refetch: () => {} } as {
    data: Vocabulary | undefined;
    isError: boolean;
    refetch: () => void;
  },
}));
vi.mock('@/lib/hooks/use-vocabulary', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/hooks/use-vocabulary')>()),
  useVocabulary: () => vocab.state,
}));

const outfit = {
  id: 'o1',
  name: 'Look',
  occasion: null,
  feedback: null,
  items: ['sneakers', 'jeans', 'shirt'].map((type, i) => ({
    id: `i${i}`,
    type,
    name: null,
    thumbnail_url: null,
    image_url: null,
    primary_color: null,
  })),
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/dashboard/outfits/new',
  useSearchParams: () => new URLSearchParams('edit=o1'),
}));
vi.mock('next/link', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/lib/hooks/use-outfits', () => ({
  useOutfit: () => ({ data: outfit, isLoading: false, isError: false, error: null, refetch: vi.fn() }),
}));
vi.mock('@/lib/hooks/use-items', () => ({ useItems: () => ({ data: undefined }) }));
vi.mock('@/lib/hooks/use-studio', () => ({
  useCreateStudioOutfit: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePatchOutfit: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/components/studio/canvas-panel', () => ({
  CanvasPanel: ({ items }: { items: { id: string; type: string }[] }) => (
    <ul>
      {items.map((i) => (
        <li key={i.id} data-testid="canvas-item">{i.type}</li>
      ))}
    </ul>
  ),
}));
vi.mock('@/components/studio/details-panel', () => ({ DetailsPanel: () => null }));
vi.mock('@/components/shared/item-picker', () => ({ ItemPicker: () => null }));
vi.mock('@/components/shared/clone-to-lookbook-dialog', () => ({ CloneToLookbookDialog: () => null }));

const canvasTypes = () => screen.queryAllByTestId('canvas-item').map((el) => el.textContent);

describe('studio waits for the live vocabulary', () => {
  beforeEach(() => {
    setTypeRoles([]);
    vocab.state = { data: undefined, isError: false, refetch: vi.fn() };
  });

  it('keeps the canvas empty until the vocabulary loads, then orders it canonically', () => {
    const { rerender } = render(<StudioEditorPage />);
    expect(canvasTypes()).toEqual([]);

    // What useVocabulary's queryFn does on success: fill the registry, then hand back data.
    setTypeRoles(VOCABULARY.types);
    vocab.state = { ...vocab.state, data: VOCABULARY };
    rerender(<StudioEditorPage />);

    expect(canvasTypes()).toEqual(['shirt', 'jeans', 'sneakers']);
  });

  it('shows the error state instead of spinning when the vocabulary fails', () => {
    const refetch = vi.fn();
    vocab.state = { data: undefined, isError: true, refetch };
    render(<StudioEditorPage />);

    expect(canvasTypes()).toEqual([]);
    expect(screen.getByText('somethingWentWrong')).toBeInTheDocument();
    fireEvent.click(screen.getByText('tryAgain'));
    expect(refetch).toHaveBeenCalled();
  });
});
