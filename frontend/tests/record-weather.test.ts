import { describe, expect, it } from 'vitest';
import { RECORD_CONDITIONS, isEmptyWeather } from '@/lib/records/weather';

describe('record weather helpers', () => {
  it('mirrors backend closed condition set', () => {
    expect(RECORD_CONDITIONS).toEqual([
      'sunny', 'partly_cloudy', 'cloudy', 'foggy', 'drizzle',
      'rain', 'heavy_rain', 'sleet', 'snow', 'thunderstorm',
    ]);
  });

  it('isEmptyWeather', () => {
    expect(isEmptyWeather(null)).toBe(true);
    expect(isEmptyWeather({ temp_high: null, temp_low: null, condition: null })).toBe(true);
    expect(isEmptyWeather({ temp_high: 0, temp_low: null, condition: null })).toBe(false);
  });
});
