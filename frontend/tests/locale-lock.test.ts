import { describe, expect, it, vi } from 'vitest';

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: (name: string) => (name === 'NEXT_LOCALE' ? { value: 'en' } : undefined) }),
  headers: async () => new Headers({ 'accept-language': 'ja,en;q=0.8' }),
}));
vi.mock('next-intl/server', () => ({
  getRequestConfig: (fn: unknown) => fn,
}));

describe('UI locale is locked to zh-CN (fixes D4)', () => {
  it('ignores the locale cookie and Accept-Language', async () => {
    const { default: config } = await import('@/i18n/request');
    const result = await (config as unknown as () => Promise<{ locale: string }>)();
    expect(result.locale).toBe('zh-CN');
  });
});
