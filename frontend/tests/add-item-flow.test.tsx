import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMock }));

const h = vi.hoisted(() => ({
  createItem: vi.fn(),
  runPipeline: vi.fn(),
  bulkCreate: vi.fn(),
  bulkPipeline: vi.fn(),
}));

vi.mock('@/lib/hooks/use-items', () => ({
  useCreateItem: () => ({ mutateAsync: h.createItem, isPending: false }),
  useRunPipeline: () => ({ mutateAsync: h.runPipeline, isPending: false }),
  useBulkCreateItems: () => ({ mutateAsync: h.bulkCreate, isPending: false, uploadProgress: 0 }),
  useBulkPipeline: () => ({ mutateAsync: h.bulkPipeline, isPending: false }),
}));

import { AddItemDialog } from '@/components/add-item-dialog';

function pickImage() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['x'], 'shirt.jpg', { type: 'image/jpeg' });
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  fireEvent.change(input);
}

function renderDialog(onCreated = vi.fn(), onOpenChange = vi.fn()) {
  render(<AddItemDialog open onOpenChange={onOpenChange} onCreated={onCreated} />);
  return { onCreated, onOpenChange };
}

beforeEach(() => {
  Object.values(h).forEach((f) => f.mockReset());
  Object.values(toastMock).forEach((f) => f.mockReset());
  vi.spyOn(console, 'error').mockImplementation(() => {});
  h.createItem.mockResolvedValue({ id: 'new-id' });
  h.runPipeline.mockResolvedValue({ status: 'queued', job_id: 'j' });
});

describe('AddItemDialog AI-first entry', () => {
  it('AI 处理 creates the item with only the image, runs the pipeline, hands off', async () => {
    const { onCreated, onOpenChange } = renderDialog();
    expect(screen.getByTestId('entry-run-ai')).toBeDisabled();
    pickImage();
    await waitFor(() => expect(screen.getByTestId('entry-run-ai')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('entry-run-ai'));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('new-id', true));
    const fd = h.createItem.mock.calls[0][0] as FormData;
    expect(Array.from(fd.keys())).toEqual(['image']);
    expect(h.runPipeline).toHaveBeenCalledWith({ id: 'new-id' });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('skip AI hands off without running the pipeline', async () => {
    const { onCreated } = renderDialog();
    pickImage();
    await waitFor(() => expect(screen.getByTestId('entry-skip-ai')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('entry-skip-ai'));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('new-id', false));
    expect(h.runPipeline).not.toHaveBeenCalled();
  });

  it('pipeline enqueue failure still hands off the created item', async () => {
    h.runPipeline.mockRejectedValue(new Error('queue down'));
    const { onCreated } = renderDialog();
    pickImage();
    await waitFor(() => expect(screen.getByTestId('entry-run-ai')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('entry-run-ai'));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('new-id', false));
    expect(toastMock.warning).toHaveBeenCalled();
  });

  it('create failure stays in the dialog', async () => {
    h.createItem.mockRejectedValue(new Error('boom'));
    const { onCreated, onOpenChange } = renderDialog();
    pickImage();
    await waitFor(() => expect(screen.getByTestId('entry-run-ai')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('entry-run-ai'));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(onCreated).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(h.runPipeline).not.toHaveBeenCalled();
  });

  it('bulk results offer to run the pipeline on the successfully uploaded items', async () => {
    h.bulkCreate.mockResolvedValue({
      staged: 0,
      unprotected: {
        total: 2,
        successful: 1,
        failed: 1,
        results: [
          { filename: 'a.jpg', success: true, item: { id: 'b1' } },
          { filename: 'b.jpg', success: false, error: 'bad' },
        ],
      },
    });
    h.bulkPipeline.mockResolvedValue({ queued: 1, failed: 0, skipped: 0 });
    renderDialog();
    fireEvent.mouseDown(screen.getByText('bulkUpload'), { button: 0 });
    await waitFor(() => expect(screen.queryByTestId('entry-run-ai')).toBeNull());
    pickImage();
    await waitFor(() => expect(screen.getByText('bulk.uploadButton')).toBeInTheDocument());
    fireEvent.click(screen.getByText('bulk.uploadButton'));

    await waitFor(() => expect(screen.getByTestId('bulk-run-ai')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('bulk-run-ai'));
    await waitFor(() => expect(h.bulkPipeline).toHaveBeenCalledWith({ item_ids: ['b1'] }));
    await waitFor(() => expect(screen.getByTestId('bulk-run-ai')).toBeDisabled());
  });
});
