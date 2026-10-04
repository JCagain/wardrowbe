'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { ColorEntry, TypeEntry, VocabEntry } from '@/lib/types';

export type { ColorEntry, TypeEntry, VocabEntry };

// The v2 runtime document shape (backend/app/data/garment_vocabulary.json).
export interface Vocabulary {
  body_parts: VocabEntry[];
  types: TypeEntry[];
  colors: { families: VocabEntry[]; values: ColorEntry[] };
  seasons: VocabEntry[];
  styles: VocabEntry[];
  materials: string[];
  formality: string[];
}

export function useVocabulary() {
  return useQuery({
    queryKey: ['vocabulary'],
    queryFn: () => api.get<Vocabulary>('/vocabulary'),
    staleTime: 5 * 60 * 1000,
  });
}

function useInvalidate() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ['vocabulary'] });
}

export function useAddStyle() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { value: string; label: string }) => api.post('/vocabulary/styles', body),
    onSuccess: invalidate,
  });
}

export function useAddColorValue() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { value: string; label: string; family: string; hex: string }) =>
      api.post('/vocabulary/colors/values', body),
    onSuccess: invalidate,
  });
}

export function useAddType() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { value: string; label: string; body_part: string }) =>
      api.post('/vocabulary/types', body),
    onSuccess: invalidate,
  });
}

export function usePatchVocabulary() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: {
      kind: 'styles' | 'types' | 'colors';
      value: string;
      label?: string;
      disabled?: boolean;
    }) => {
      const { kind, value, ...body } = args;
      return api.patch(`/vocabulary/${kind}/${value}`, body);
    },
    onSuccess: invalidate,
  });
}


export type VocabKind = 'styles' | 'types' | 'colors';

/** Picker-side rename/disable handlers plus the add-dialog state for one form. */
export function useVocabManagement() {
  const patch = usePatchVocabulary();
  const [addKind, setAddKind] = useState<VocabKind | null>(null);

  const handlersFor = (kind: VocabKind) => ({
    onRename: (value: string, label: string) => patch.mutateAsync({ kind, value, label }),
    onDisable: (value: string) => patch.mutateAsync({ kind, value, disabled: true }),
  });

  return {
    addKind,
    openAdd: (kind: VocabKind) => setAddKind(kind),
    closeAdd: () => setAddKind(null),
    handlersFor,
  };
}
