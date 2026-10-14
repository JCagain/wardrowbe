// spec §3.1 / §10.1：记录季节按日期推导（与后端 app/utils/season.py 同表）。
export const RECORD_SEASONS = ['spring', 'summer', 'fall', 'winter'] as const;
export type RecordSeason = (typeof RECORD_SEASONS)[number];

const BY_MONTH: Record<number, RecordSeason> = {
  1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
  6: 'summer', 7: 'summer', 8: 'summer', 9: 'summer',
  10: 'fall', 11: 'fall', 12: 'winter',
};

export function seasonForDate(d: Date | string): RecordSeason {
  // 'YYYY-MM-DD' 直接取月份，避免 new Date(iso) 按 UTC 解析造成跨日偏移
  const month = typeof d === 'string' ? Number(d.slice(5, 7)) : d.getMonth() + 1;
  return BY_MONTH[month];
}
