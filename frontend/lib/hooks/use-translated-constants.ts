'use client';

import { useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  OCCASIONS,
  TypeEntry,
  VocabEntry,
} from '@/lib/types';
import {
  BODY_PART_LABELS,
  BODY_PART_VALUES,
  COLOR_VALUES,
  STYLE_LABELS,
  TYPE_ENTRIES,
} from '@/lib/generated/garment-vocabulary';
import { useVocabulary } from '@/lib/hooks/use-vocabulary';

const WEATHER_CONDITION_VALUES = ['clear', 'cloudy', 'rain', 'snow'] as const;

// Type/color/style labels come from the vocabulary itself (single source) and are
// never routed through constants.* translations. The runtime vocabulary wins;
// the generated export is the offline fallback while it loads.
export function useClothingTypes(): TypeEntry[] {
  const { data } = useVocabulary();
  return useMemo(() => data?.types ?? [...TYPE_ENTRIES], [data]);
}

export function useClothingColors() {
  const { data } = useVocabulary();
  // Full ColorEntry (pickers) plus a `name` alias for the older consumers.
  return useMemo(() => {
    const values = data?.colors.values ?? [...COLOR_VALUES];
    return values.map((c) => ({ ...c, name: c.label }));
  }, [data]);
}

// Body-part labels live in the vocabulary itself (single source), like type and color labels.
export function useBodyParts(): VocabEntry[] {
  return useMemo(() => BODY_PART_VALUES.map((value) => ({
    value,
    label: BODY_PART_LABELS[value],
  })), []);
}

export function useOccasions() {
  const t = useTranslations('constants.occasions');

  return useMemo(() => OCCASIONS.map((o) => ({
    ...o,
    label: t(o.value),
  })), [t]);
}

export function useStyles(): VocabEntry[] {
  const { data } = useVocabulary();
  return useMemo(() => {
    if (data) return data.styles;
    return Object.entries(STYLE_LABELS).map(([value, label]) => ({ value, label }));
  }, [data]);
}

export function useWeatherConditions() {
  const t = useTranslations('constants.weatherConditions');

  return useMemo(() => WEATHER_CONDITION_VALUES.map((value) => ({
    value,
    label: t(value),
  })), [t]);
}

type CatalogTranslator = ((key: string) => string) & { has: (key: string) => boolean };

// Subtypes, materials and formalities can hold values outside the catalog (free text, or rows
// tagged before the vocabulary changed), so an unknown value falls back to the raw value made
// readable ("slip-dress" -> "Slip dress") instead of a key path.
function useCatalogLabel(t: CatalogTranslator) {
  return useCallback((value: string) => {
    const key = value.toLowerCase();
    if (t.has(key)) return t(key);
    const spaced = value.replace(/[-_]+/g, ' ').trim();
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  }, [t]);
}

export function useSubtypeLabel() {
  return useCatalogLabel(useTranslations('constants.subtypes'));
}

export function useMaterialLabel() {
  return useCatalogLabel(useTranslations('constants.materials'));
}

export function useFormalityLabel() {
  return useCatalogLabel(useTranslations('constants.formalities'));
}

export function useRoleLabel() {
  return useCatalogLabel(useTranslations('constants.roles'));
}
