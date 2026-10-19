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
