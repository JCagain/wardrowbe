import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';

// Helper to set token if available (for NextAuth mode)
function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export interface ColorDistribution {
  color: string;
  count: number;
  percentage: number;
}

export interface TypeDistribution {
  type: string;
  count: number;
  percentage: number;
}

export interface StyleDistribution {
  style: string;
  count: number;
  percentage: number;
}

export type AnalyticsScope = 'all' | 'no_retired' | 'active_only';

export interface WearStats {
  id: string;
  name: string | null;
  type: string;
  primary_color: string | null;
  thumbnail_path: string | null;
  thumbnail_url: string | null;
  wear_count: number;
  last_worn_at: string | null;
}

export interface WardrobeStats {
  total_items: number;
  items_by_status: Record<string, number>;
  total_outfits: number;
  outfits_this_week: number;
  outfits_this_month: number;
  total_wears: number;
}

export interface AnalyticsData {
  wardrobe: WardrobeStats;
  color_distribution: ColorDistribution[];
  type_distribution: TypeDistribution[];
  style_distribution: StyleDistribution[];
  most_worn: WearStats[];
  least_worn: WearStats[];
  never_worn: WearStats[];
}

export function useAnalytics(scope: AnalyticsScope = 'all') {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['analytics', scope],
    queryFn: () => api.get<AnalyticsData>('/analytics', { params: { scope } }),
    enabled: status !== 'loading',
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
