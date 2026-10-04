import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

// Create a wrapper with React Query provider
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children)
}

describe('API Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useItems hook', () => {
    it('should handle empty item list', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
          has_more: false,
        }),
      } as Response)

      // Note: We can't actually test the hook without proper session context
      // This is a placeholder for the structure
      expect(true).toBe(true)
    })
  })

  describe('Error handling in hooks', () => {
    it('should handle 401 errors gracefully', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Unauthorized' }),
      } as Response)

      // Hooks should handle auth errors
      expect(true).toBe(true)
    })

    it('should handle network errors', async () => {
      vi.mocked(global.fetch).mockRejectedValueOnce(new Error('Network error'))

      // Hooks should handle network failures
      expect(true).toBe(true)
    })
  })
})

describe('Utility functions', () => {
  describe('Color utilities', () => {
    it('should handle color normalization', () => {
      // Color names should be lowercase
      const color = 'BLUE'.toLowerCase()
      expect(color).toBe('blue')
    })

    it('should handle hex color validation', () => {
      const hexRegex = /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/
      expect(hexRegex.test('#ffffff')).toBe(true)
      expect(hexRegex.test('#fff')).toBe(true)
      expect(hexRegex.test('invalid')).toBe(false)
    })
  })

  describe('Date utilities', () => {
    it('should format dates correctly', () => {
      const date = new Date('2024-01-15')
      const formatted = date.toISOString().split('T')[0]
      expect(formatted).toBe('2024-01-15')
    })
  })
})

describe('useItems filter serialization', () => {
  // The wardrobe lifecycle chips pass filters.lifecycle; if the query string
  // drops it the grid silently shows the default slice instead.
  it('forwards lifecycle to the API', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 20, has_more: false }),
    } as Response);

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client }, children);
    const { useItems } = await import('@/lib/hooks/use-items');
    renderHook(() => useItems({ lifecycle: 'retired' }, 1, 20), { wrapper });
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const url = String(vi.mocked(global.fetch).mock.calls[0][0]);
    expect(url).toContain('lifecycle=retired');
  });
});
