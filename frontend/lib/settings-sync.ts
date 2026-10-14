import type { Preferences } from '@/lib/types';

/**
 * 偏好重新拉取后同步到设置页表单：
 * 有未保存改动时只并入城市卡片（独立保存）管理的字段，保留其余未保存编辑；
 * 无改动时整体替换。
 */
export function syncFormWithPreferences(
  current: Partial<Preferences>,
  fresh: Preferences,
  hasChanges: boolean
): Partial<Preferences> {
  if (!hasChanges) return fresh;
  return { ...current, cities: fresh.cities, default_city: fresh.default_city };
}
