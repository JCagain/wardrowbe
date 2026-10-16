'use client';

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, ApiError, getAccessToken, NetworkError, setAccessToken } from '@/lib/api';
import type {
  GarmentRegion,
  GarmentRegionsResponse,
  OutfitRecord,
  RecordInput,
  RecordListResponse,
  RecordWeather,
} from '@/lib/types';

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

// multipart 不能走 api.post（它强制 JSON Content-Type），照 useCreateItem 的写法直连代理路径。
async function postMultipart<T>(url: string, body: FormData): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(url, { method: 'POST', body, credentials: 'include', headers });
  } catch {
    throw new NetworkError('Unable to connect to server. Please try again.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === 'string' ? data.detail : 'Request failed';
    throw new ApiError(message, response.status, data);
  }
  return response.json();
}

function useInvalidateRecords() {
  const queryClient = useQueryClient();
  return (id?: string) => {
    queryClient.invalidateQueries({ queryKey: ['records'] });
    if (id) queryClient.invalidateQueries({ queryKey: ['record', id] });
    queryClient.invalidateQueries({ queryKey: ['items'] });
    queryClient.invalidateQueries({ queryKey: ['item-companions'] });
    queryClient.invalidateQueries({ queryKey: ['analytics'] });
    queryClient.invalidateQueries({ queryKey: ['item'] });
    queryClient.invalidateQueries({ queryKey: ['wear-stats'] });
  };
}

export function useRecords(dateFrom: string, dateTo: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: ['records', dateFrom, dateTo],
    queryFn: () =>
      api.get<RecordListResponse>('/records', {
        params: { date_from: dateFrom, date_to: dateTo, page_size: '200' },
      }),
    enabled: status !== 'loading',
  });
}

function useRecordPages(key: unknown[], pageSize: number, extra: Record<string, string>, enabled = true) {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useInfiniteQuery({
    queryKey: key,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      api.get<RecordListResponse>('/records', {
        params: { ...extra, page: String(pageParam), page_size: String(pageSize) },
      }),
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
    enabled: status !== 'loading' && enabled,
  });
}

/** 反查（fixes #45，Ruling 69）：关联该衣物的全部记录，日期倒序，分页加载。 */
export function useItemRecords(itemId: string) {
  return useRecordPages(['records', 'item', itemId], 20, { item_id: itemId }, !!itemId);
}

/** 记录时间线（fixes #47，Ruling 71）。 */
export function useRecordTimeline() {
  return useRecordPages(['records', 'timeline'], 30, {});
}

export function useRecord(id?: string) {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: ['record', id],
    queryFn: () => api.get<OutfitRecord>(`/records/${id}`),
    enabled: status !== 'loading' && !!id,
  });
}

export function useCreateRecord() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ input, photos }: { input: RecordInput; photos: File[] }) => {
      const form = new FormData();
      form.append('data', JSON.stringify(input));
      photos.forEach((p) => form.append('photos', p));
      return postMultipart<OutfitRecord>('/api/v1/records', form);
    },
    onSuccess: (record) => invalidate(record?.id),
  });
}

export function useUpdateRecord() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<RecordInput> }) =>
      api.patch<OutfitRecord>(`/records/${id}`, input),
    onSuccess: (_r, vars) => invalidate(vars.id),
  });
}

export function useDeleteRecord() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/records/${id}`),
    onSuccess: (_r, id) => invalidate(id),
  });
}

export function useAddRecordPhoto() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const form = new FormData();
      form.append('photo', file);
      return postMultipart<OutfitRecord>(`/api/v1/records/${id}/photos`, form);
    },
    onSuccess: (_r, vars) => invalidate(vars.id),
  });
}

export function useDeleteRecordPhoto() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ id, photoId }: { id: string; photoId: string }) =>
      api.delete<OutfitRecord>(`/records/${id}/photos/${photoId}`),
    onSuccess: (_r, vars) => invalidate(vars.id),
  });
}

export function useRotateRecordPhoto() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ id, photoId, direction }: { id: string; photoId: string; direction: 'cw' | 'ccw' }) =>
      api.post<OutfitRecord>(`/records/${id}/photos/${photoId}/rotate`, { direction }),
    onSuccess: (_r, vars) => invalidate(vars.id),
  });
}

export function useDetectGarmentRegions() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ id, photoId, signal }: { id: string; photoId: string; signal?: AbortSignal }) =>
      api.post<GarmentRegionsResponse>(`/records/${id}/photos/${photoId}/garment-regions/detect`, undefined, { signal }),
    onSuccess: (_r, vars) => invalidate(vars.id),
  });
}

export function useSaveGarmentRegions() {
  useSetTokenIfAvailable();
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ id, photoId, regions }: { id: string; photoId: string; regions: GarmentRegion[] }) =>
      api.put<GarmentRegionsResponse>(`/records/${id}/photos/${photoId}/garment-regions`, { regions }),
    onSuccess: (_r, vars) => invalidate(vars.id),
  });
}

export async function fetchRecordWeather(city: string, date: string): Promise<RecordWeather | null> {
  const res = await api.get<{ weather: RecordWeather | null }>('/records/weather', {
    params: { city, date },
  });
  return res.weather ?? null;
}
