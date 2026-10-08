'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken, ApiError } from '@/lib/api';

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export interface Weather {
  temperature: number;
  feels_like: number;
  humidity: number;
  precipitation_chance: number;
  precipitation_mm: number;
  wind_speed: number;
  condition: string;
  condition_code: number;
  is_day: boolean;
  uv_index: number;
  timestamp: string;
}

export function useWeather() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery<Weather | null>({
    queryKey: ['weather'],
    queryFn: async () => {
      try {
        return await api.get<Weather>('/weather/current');
      } catch (error) {
        // Location is optional, so "no coordinates" is an empty state rather
        // than a failure. The endpoint answers that with a 400, which the
        // global QueryCache handler would otherwise toast on every page load.
        // Swallow it and report null so consumers render their own empty UI.
        if (error instanceof ApiError && error.status === 400) return null;
        throw error;
      }
    },
    enabled: status !== 'loading',
    staleTime: 1000 * 60 * 15, // 15 minutes - weather doesn't change that fast
    retry: false, // Don't retry if location not set
  });
}
