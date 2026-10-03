'use client';

import { useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  CLOTHING_TYPES,
  CLOTHING_COLORS,
  OCCASIONS,
  VocabEntry,
} from '@/lib/types';
import { BODY_PART_VALUES, TYPE_ENTRIES } from '@/lib/generated/garment-vocabulary';

const STYLE_VALUES = ['bold', 'casual', 'formal', 'minimalist', 'sporty'] as const;
const WEATHER_CONDITION_VALUES = ['clear', 'cloudy', 'rain', 'snow'] as const;

// Type and color labels come from the vocabulary itself (single source), so they are
// no longer routed through constants.types / constants.colors translations.
export function useClothingTypes() {
  return useMemo(() => CLOTHING_TYPES.map((ct) => {
    const entry = TYPE_ENTRIES.find((e) => e.value === ct.value);
    return {
      ...ct,
      label: entry?.label ?? ct.value,
    };
  }), []);
}

export function useClothingColors() {
  return useMemo(() => CLOTHING_COLORS, []);
}

// Body-part values come from the vocabulary; their display names live in the message
// catalog until the runtime vocabulary hook (use-vocabulary) ships them with labels.
export function useBodyParts(): VocabEntry[] {
  const t = useTranslations('constants.bodyParts');

  return useMemo(() => BODY_PART_VALUES.map((value) => ({
    value,
    label: t(value),
  })), [t]);
}

export function useOccasions() {
  const t = useTranslations('constants.occasions');

  return useMemo(() => OCCASIONS.map((o) => ({
    ...o,
    label: t(o.value),
  })), [t]);
}

export function useStyles() {
  const t = useTranslations('constants.styles');

  return useMemo(() => STYLE_VALUES.map((value) => ({
    value,
    label: t(value),
  })), [t]);
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
