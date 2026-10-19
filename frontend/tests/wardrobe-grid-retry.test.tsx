import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// 网格卡片的失败重试按 processing_kind 分流：流水线图像步骤失败（kind=pipeline）
// 不是打标失败，重试要走 POST /items/{id}/pipeline，而不是打标重试（final-findings #3）。
const g = vi.hoisted(() => ({
  reanalyze: vi.fn(),
  removeBg: vi.fn(),
  runPipeline: vi.fn(),
  kind: 'pipeline' as string | null,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }))
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
  return {
    ...actual,
    useItems: () => ({
      data: {
        items: [
          {
            id: 'item-1', type: 'shirt', status: 'error', processing_kind: g.kind, name: 'n1',
            updated_at: '2026-10-19T00:00:00Z', primary_colors: [], tags: {},
          },
        ],
        total: 1,
      },
      isLoading: false,
      error: null,
    }),
    useTaggingProgress: () => ({ data: undefined }),
    useItemTypes: () => ({ data: [] }),
    useItem: () => ({ data: undefined }),
    useReanalyzeItem: () => ({ mutate: g.reanalyze, isPending: false }),
    useRemoveBackground: () => ({ mutate: g.removeBg, isPending: false }),
    useRunPipeline: () => ({ mutate: g.runPipeline, isPending: false }),
    useCancelAnalysis: idle,
    useBulkDeleteItems: idle,
    useBulkReanalyzeItems: idle,
    useBulkCancelAnalysis: idle,
    useBulkRotateItems: idle,
    useBulkRemoveBackgroundItems: idle,
    useBulkPipeline: idle,
  }
})

async function renderPage() {
  const { default: WardrobePage } = await import('@/app/dashboard/wardrobe/page')
  return render(<WardrobePage />)
}

beforeEach(() => {
  g.reanalyze.mockClear(); g.removeBg.mockClear(); g.runPipeline.mockClear()
})

describe('wardrobe grid failed-card retry routing', () => {
  it('retries a pipeline image failure through the pipeline, not tagging', async () => {
    g.kind = 'pipeline'
    await renderPage()
    expect(screen.getByText('ai.pipelineFailed')).toBeInTheDocument()
    expect(screen.queryByText('ai.analysisFailed')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'retry' }))
    expect(g.runPipeline).toHaveBeenCalledWith({ id: 'item-1' })
    expect(g.reanalyze).not.toHaveBeenCalled()
  })

  it('still retries a tagging failure through reanalyze', async () => {
    g.kind = null
    await renderPage()
    expect(screen.getByText('ai.analysisFailed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'retry' }))
    expect(g.reanalyze).toHaveBeenCalled()
    expect(g.runPipeline).not.toHaveBeenCalled()
  })
})
