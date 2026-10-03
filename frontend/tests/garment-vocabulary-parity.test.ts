import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import constants from '@/messages/en/constants.json';
import {
  FORMALITY_VALUES, ITEM_ROLE, MATERIAL_VALUES,
  BODY_PART_VALUES, TYPE_ENTRIES, COLOR_FAMILY_VALUES, COLOR_VALUES, STYLE_VALUES, SEASON_VALUES,
} from '@/lib/generated/garment-vocabulary';
import { CLOTHING_TYPES } from '@/lib/types';

const VOCABULARY_PATH = resolve(__dirname, '..', '..', 'backend', 'app', 'data', 'garment_vocabulary.json');
const vocabulary = JSON.parse(readFileSync(VOCABULARY_PATH, 'utf8')) as {
  body_parts: Array<{ value: string }>;
  types: Array<{ value: string; label: string; role: string; body_part: string }>;
  colors: { families: Array<{ value: string }>; values: Array<{ value: string; family: string; hex: string }> };
  seasons: Array<{ value: string }>;
  styles: Array<{ value: string }>;
  materials: string[];
  formality: string[];
};

const sorted = (values: Iterable<string>) => Array.from(values).sort();

describe('garment vocabulary', () => {
  it('generates the picker, roles and scales from the backend vocabulary file', () => {
    expect(sorted(CLOTHING_TYPES.map((type) => type.value))).toEqual(sorted(vocabulary.types.map((t) => t.value)));
    expect(ITEM_ROLE).toEqual(Object.fromEntries(vocabulary.types.map((t) => [t.value, t.role])));
    expect([...MATERIAL_VALUES]).toEqual(vocabulary.materials);
    expect([...FORMALITY_VALUES]).toEqual(vocabulary.formality);
  });

  it('has labels for types in the vocabulary and exact i18n keys for materials, formality and roles', () => {
    // Type labels live in the vocabulary itself (single source; constants.types is
    // no longer required to enumerate them — Task 7/12 retire those lists).
    expect(vocabulary.types.every((t) => Boolean(t.label))).toBe(true);
    expect(sorted(Object.keys(constants.materials))).toEqual(sorted(vocabulary.materials));
    expect(sorted(Object.keys(constants.formalities))).toEqual(sorted(vocabulary.formality));
    expect(sorted(Object.keys(constants.roles))).toEqual(sorted(new Set(vocabulary.types.map((t) => t.role))));
  });

  it('exposes v2 sections matching the backend JSON', () => {
    expect(BODY_PART_VALUES).toEqual(vocabulary.body_parts.map((p: { value: string }) => p.value));
    expect(TYPE_ENTRIES.map((t) => t.value)).toEqual(vocabulary.types.map((t: { value: string }) => t.value));
    expect(COLOR_VALUES.map((c) => c.hex)).toEqual(vocabulary.colors.values.map((c: { hex: string }) => c.hex));
    expect(STYLE_VALUES).toEqual(vocabulary.styles.map((s: { value: string }) => s.value));
    expect(SEASON_VALUES).toEqual(vocabulary.seasons.map((s: { value: string }) => s.value));
  });
});
