import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { BulkActionToolbar, type BulkSelection } from '@/components/bulk-action-toolbar'

// 工具条只回调、不碰数据：页面的 handleBulkPipeline 与 handleBulkRemoveBackground
// 共用同一个 getBulkParams()，所以「选择参数同形」在页面层由构造保证；
// 这里测按钮存在、点击触发回调、进行中禁用。
const selection: BulkSelection = {
  mode: 'some',
  selectedIds: new Set(['a', 'b']),
  excludedIds: new Set(),
}

function renderToolbar(props: Partial<React.ComponentProps<typeof BulkActionToolbar>> = {}) {
  return render(
    <BulkActionToolbar
      selection={selection}
      totalItems={2}
      pageItems={2}
      onSelectAll={vi.fn()}
      onSelectAllMatching={vi.fn()}
      onClear={vi.fn()}
      onDelete={vi.fn()}
      page={1}
      pageSize={20}
      onPageChange={vi.fn()}
      {...props}
    />,
  )
}

describe('BulkActionToolbar AI process button', () => {
  it('calls onRunPipeline when bulk-pipeline is clicked', () => {
    const onRunPipeline = vi.fn()
    renderToolbar({ onRunPipeline })
    fireEvent.click(screen.getByTestId('bulk-pipeline'))
    expect(onRunPipeline).toHaveBeenCalledTimes(1)
  })

  it('is absent without a handler and disabled while running', () => {
    const { unmount } = renderToolbar()
    expect(screen.queryByTestId('bulk-pipeline')).toBeNull()
    unmount()
    renderToolbar({ onRunPipeline: vi.fn(), isRunningPipeline: true })
    expect(screen.getByTestId('bulk-pipeline')).toBeDisabled()
  })
})

// ---- 页面层：批量 AI 处理与批量抠图收到同形的选择参数 ----
const page = vi.hoisted(() => {
  const ok = { queued: 2, skipped: 1, failed: 1, already_done: 0 }
  const mk = () => vi.fn().mockResolvedValue(ok)
  return {
    pipeline: mk(),
    removeBg: mk(),
    toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
  }
})

vi.mock('sonner', () => ({ toast: page.toast }))
vi.mock('@/lib/hooks/use-user', () => ({ useUserProfile: () => ({ data: undefined }) }))
vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingColors: () => [],
  useSubtypeLabel: () => (v: string) => v,
}))
vi.mock('@/components/add-item-dialog', () => ({ AddItemDialog: () => null }))
vi.mock('@/components/analysis-queue-panel', () => ({ AnalysisQueuePanel: () => null }))
vi.mock('@/components/item-detail-dialog', () => ({ ItemDetailDialog: () => null }))
vi.mock('@/components/wardrobe/vocab-filter-bar', () => ({ VocabFilterBar: () => null }))
vi.mock('@/lib/hooks/use-items', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/hooks/use-items')>()
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })
  const items = [1, 2].map((n) => ({
    id: `item-${n}`, type: 'shirt', status: 'ready', name: `n${n}`,
    updated_at: '2026-10-19T00:00:00Z', primary_colors: [], tags: {},
  }))
  return {
    ...actual,
    useItems: () => ({ data: { items, total: 5 }, isLoading: false, error: null }),
    useTaggingProgress: () => ({ data: undefined }),
    useItemTypes: () => ({ data: [] }),
    useItem: () => ({ data: undefined }),
    useReanalyzeItem: idle,
    useCancelAnalysis: idle,
    useRemoveBackground: idle,
    useRunPipeline: idle,
    useBulkDeleteItems: idle,
    useBulkReanalyzeItems: idle,
    useBulkCancelAnalysis: idle,
    useBulkRotateItems: idle,
    useBulkRemoveBackgroundItems: () => ({ mutateAsync: page.removeBg, isPending: false }),
    useBulkPipeline: () => ({ mutateAsync: page.pipeline, isPending: false }),
  }
})

describe('wardrobe page bulk AI process', () => {
  async function renderPage() {
    const { default: WardrobePage } = await import('@/app/dashboard/wardrobe/page')
    return render(<WardrobePage />)
  }

  async function confirmRemoveBg() {
    // 抠图按钮在 AlertDialog 里，点触发器再点确认
    const trigger = screen.getAllByRole('button', { name: 'bulkActions.removeBackground' })[0]
    fireEvent.click(trigger)
    fireEvent.click(await screen.findByRole('button', { name: 'confirm' }))
  }

  it('passes the same params as bulk remove-bg, toasts and clears selection (page mode)', async () => {
    page.pipeline.mockClear(); page.removeBg.mockClear()
    Object.values(page.toast).forEach((f) => f.mockClear())
    await renderPage()
    fireEvent.click(screen.getByText('selectAll'))
    fireEvent.click(screen.getByTestId('bulk-pipeline'))
    await vi.waitFor(() => expect(page.pipeline).toHaveBeenCalledTimes(1))
    expect(page.pipeline).toHaveBeenCalledWith({ item_ids: ['item-1', 'item-2'] })
    expect(page.toast.success).toHaveBeenCalledWith('bulkActions.pipelineQueued')
    expect(page.toast.info).toHaveBeenCalledWith('bulkActions.pipelineSkipped')
    expect(page.toast.error).toHaveBeenCalledWith('bulkActions.pipelinePartialFailed')
    // 选择已清空：工具条上不再有按钮
    await vi.waitFor(() => expect(screen.queryByTestId('bulk-pipeline')).toBeNull())

    fireEvent.click(screen.getByText('selectAll'))
    await confirmRemoveBg()
    await vi.waitFor(() => expect(page.removeBg).toHaveBeenCalledTimes(1))
    expect(page.removeBg.mock.calls[0][0]).toEqual(page.pipeline.mock.calls[0][0])
  })

  it('passes the same params as bulk remove-bg in select-all-matching mode', async () => {
    page.pipeline.mockClear(); page.removeBg.mockClear()
    await renderPage()
    fireEvent.click(screen.getByText('selectAll'))
    fireEvent.click(screen.getByText('bulkActions.selectAllMatching'))
    fireEvent.click(screen.getByTestId('bulk-pipeline'))
    await vi.waitFor(() => expect(page.pipeline).toHaveBeenCalledTimes(1))
    const sent = page.pipeline.mock.calls[0][0]
    expect(sent.select_all).toBe(true)
    expect(sent.excluded_ids).toEqual([])
    await vi.waitFor(() => expect(screen.queryByTestId('bulk-pipeline')).toBeNull())

    fireEvent.click(screen.getByText('selectAll'))
    fireEvent.click(screen.getByText('bulkActions.selectAllMatching'))
    await confirmRemoveBg()
    await vi.waitFor(() => expect(page.removeBg).toHaveBeenCalledTimes(1))
    expect(page.removeBg.mock.calls[0][0]).toEqual(sent)
  })
})
