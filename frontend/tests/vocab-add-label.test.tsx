import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { VocabAddChip } from '@/components/vocab/vocab-managed-chip';

// next-intl is mocked in setup.ts to echo bare keys; interpolation values are
// dropped — so the pin is "which message key is rendered", not the copy.
describe('VocabAddChip label', () => {
  it('renders the vocabulary title message, not a raw kind noun', () => {
    render(<VocabAddChip kind="color" onClick={() => {}} />);
    expect(screen.getByText('title.colors')).toBeInTheDocument();
  });

  it('maps style and type kinds onto their title keys', () => {
    const { unmount } = render(<VocabAddChip kind="style" onClick={() => {}} />);
    expect(screen.getByText('title.styles')).toBeInTheDocument();
    unmount();
    render(<VocabAddChip kind="type" onClick={() => {}} />);
    expect(screen.getByText('title.types')).toBeInTheDocument();
  });
});
