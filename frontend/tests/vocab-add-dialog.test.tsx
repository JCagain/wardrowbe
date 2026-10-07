import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { VocabAddDialog } from '@/components/vocab/vocab-add-dialog';
import { BODY_PART_LABELS } from '@/lib/generated/garment-vocabulary';

const mutateAsync = vi.hoisted(() => vi.fn()); // vi.mock factories are hoisted above module init
vi.mock('@/lib/hooks/use-vocabulary', () => ({
  useVocabulary: () => ({ data: { colors: { families: [] }, types: [], styles: [] } }),
  useAddStyle: () => ({ mutateAsync, isPending: false }),
  useAddType: () => ({ mutateAsync, isPending: false }),
  useAddColorValue: () => ({ mutateAsync, isPending: false }),
}));

describe('VocabAddDialog body-part preselect', () => {
  it('reseeds the select when the mounted dialog reopens without a family', () => {
    const { rerender } = render(
      <VocabAddDialog kind="types" open onOpenChange={() => {}} family="tops" />,
    );
    // close and reopen with no family prop — the component stays mounted, so
    // only an open-time reseed clears the previous session's choice
    rerender(<VocabAddDialog kind="types" open={false} onOpenChange={() => {}} family="tops" />);
    rerender(<VocabAddDialog kind="types" open onOpenChange={() => {}} family={undefined} />);

    // fresh open must show the placeholder, not the previous dialog's 'tops'
    expect(screen.getByText('bodyPartPlaceholder')).toBeInTheDocument();
    expect(screen.queryByText(BODY_PART_LABELS.tops)).not.toBeInTheDocument();
  });

  it('submits the current family prop after a previous session picked a part', async () => {
    mutateAsync.mockClear();
    const { rerender } = render(
      <VocabAddDialog kind="types" open onOpenChange={() => {}} family="tops" />,
    );
    rerender(<VocabAddDialog kind="types" open={false} onOpenChange={() => {}} family="tops" />);
    rerender(<VocabAddDialog kind="types" open onOpenChange={() => {}} family="footwear" />);

    fireEvent.change(screen.getByLabelText('label'), { target: { value: 'Sneakers' } });
    fireEvent.change(screen.getByLabelText('slug'), { target: { value: 'sneakers' } });
    fireEvent.click(screen.getByText('submit'));

    // display and payload must agree on the new prop, not the stale state
    expect(mutateAsync).toHaveBeenCalledWith({
      value: 'sneakers',
      label: 'Sneakers',
      body_part: 'footwear',
    });
  });
});
