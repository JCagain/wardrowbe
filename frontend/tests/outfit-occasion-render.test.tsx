import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OutfitCard } from '@/components/outfits/outfit-card';
import { OutfitHistoryCard } from '@/components/outfit-history-card';
import { OutfitPreviewDialog } from '@/components/outfit-preview-dialog';
import type { Outfit, OutfitItem } from '@/lib/hooks/use-outfits';

// Render pins for the null-occasion fallbacks that live inline in JSX (the
// title ternaries and the occasion-chip guards). The pure helpers —
// getCardTitle and defaultCloneName — are pinned in
// outfit-occasion-fallbacks.test.ts; these cover the component surfaces that
// still contain their own fallback code.
vi.mock('next/image', () => ({ default: () => null }));
vi.mock('next/link', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/lib/hooks/use-items', () => ({
  useRotateImage: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/hooks/use-outfits', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/hooks/use-outfits')>();
  return {
    ...actual,
    useAcceptOutfit: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useRejectOutfit: () => ({ mutateAsync: vi.fn(), isPending: false }),
  };
});

const item: OutfitItem = {
  id: 'item-1',
  type: 'shirt',
  subtype: null,
  name: null,
  primary_color: null,
  colors: [],
  image_path: '/tmp/shirt.jpg',
  thumbnail_path: null,
  layer_type: null,
  position: 0,
};

function makeOutfit(overrides: Partial<Outfit> = {}): Outfit {
  return {
    id: 'outfit-1',
    occasion: null,
    scheduled_for: null,
    status: 'accepted',
    source: 'manual',
    name: null,
    replaces_outfit_id: null,
    cloned_from_outfit_id: null,
    reasoning: null,
    style_notes: null,
    season: null,
    formality: null,
    palette: null,
    notes: null,
    highlights: null,
    weather: null,
    items: [item],
    feedback: null,
    family_ratings: null,
    family_rating_average: null,
    family_rating_count: null,
    created_at: '2026-10-07T00:00:00Z',
    ...overrides,
  };
}

describe('OutfitCard with a nullable occasion', () => {
  it('falls back to the untitled label and renders no occasion chip', () => {
    render(<OutfitCard outfit={makeOutfit()} />);
    expect(screen.getByText('untitledOutfit')).toBeInTheDocument();
    expect(screen.queryByText('dinner')).not.toBeInTheDocument();
  });

  it('renders the occasion fallback title and the occasion chip', () => {
    render(<OutfitCard outfit={makeOutfit({ occasion: 'dinner' })} />);
    // next-intl is mocked to echo the key; the interpolation is pinned in
    // outfit-occasion-fallbacks.test.ts, here we pin the branch taken.
    expect(screen.getByText('outfitFallback')).toBeInTheDocument();
    expect(screen.queryByText('untitledOutfit')).not.toBeInTheDocument();
    expect(screen.getByText('dinner')).toBeInTheDocument();
  });
});

describe('OutfitHistoryCard with a nullable occasion', () => {
  it('omits the occasion chip instead of crashing', () => {
    render(<OutfitHistoryCard outfit={makeOutfit()} onFeedback={() => {}} />);
    expect(screen.queryByText('dinner')).not.toBeInTheDocument();
    // The rest of the header still renders around the missing chip.
    expect(screen.getByText('sourceBadges.manual')).toBeInTheDocument();
  });

  it('shows the occasion chip when occasion is present', () => {
    render(
      <OutfitHistoryCard outfit={makeOutfit({ occasion: 'dinner' })} onFeedback={() => {}} />,
    );
    expect(screen.getByText('dinner')).toBeInTheDocument();
  });
});

describe('OutfitPreviewDialog title with a nullable occasion', () => {
  it('falls back to the untitled label instead of crashing', () => {
    render(<OutfitPreviewDialog outfit={makeOutfit()} open onClose={() => {}} />);
    expect(screen.getByText('untitledOutfit')).toBeInTheDocument();
    expect(screen.queryByText('title')).not.toBeInTheDocument();
  });

  it('uses the occasion title when occasion is present', () => {
    render(
      <OutfitPreviewDialog outfit={makeOutfit({ occasion: 'dinner' })} open onClose={() => {}} />,
    );
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.queryByText('untitledOutfit')).not.toBeInTheDocument();
  });
});
