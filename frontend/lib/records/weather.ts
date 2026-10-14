import type { RecordWeather } from '@/lib/types';

// 与后端 weather_service.RECORD_CONDITIONS 同序；中文名在 history.records.conditions.*
export const RECORD_CONDITIONS = [
  'sunny', 'partly_cloudy', 'cloudy', 'foggy', 'drizzle',
  'rain', 'heavy_rain', 'sleet', 'snow', 'thunderstorm',
] as const;
export type RecordCondition = (typeof RECORD_CONDITIONS)[number];

export function isEmptyWeather(w: RecordWeather | null | undefined): boolean {
  return !w || (w.temp_high === null && w.temp_low === null && w.condition === null);
}
