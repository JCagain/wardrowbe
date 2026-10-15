import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import constants from '@/messages/en/constants.json';
import * as generated from '@/lib/generated/garment-vocabulary';
import {
  FORMALITY_VALUES, MATERIAL_VALUES, BODY_PART_VALUES, BODY_PART_LABELS, SEASON_VALUES,
} from '@/lib/generated/garment-vocabulary';

const VOCABULARY_PATH = resolve(__dirname, '..', '..', 'backend', 'app', 'data', 'garment_vocabulary.json');
const vocabulary = JSON.parse(readFileSync(VOCABULARY_PATH, 'utf8')) as {
  body_parts: Array<{ value: string; label: string }>;
  types: Array<{ value: string; label: string; role: string; body_part: string }>;
  colors: {
    families: Array<{ value: string }>;
    values: Array<{ value: string; label: string; family: string; hex: string }>;
  };
  seasons: Array<{ value: string }>;
  styles: Array<{ value: string }>;
  materials: string[];
  formality: string[];
};

const sorted = (values: Iterable<string>) => Array.from(values).sort();

describe('garment vocabulary', () => {
  it('generates the fixed sets from the backend vocabulary file', () => {
    expect([...MATERIAL_VALUES]).toEqual(vocabulary.materials);
    expect([...FORMALITY_VALUES]).toEqual(vocabulary.formality);
    expect([...BODY_PART_VALUES]).toEqual(vocabulary.body_parts.map((p) => p.value));
    expect(BODY_PART_LABELS).toEqual(Object.fromEntries(vocabulary.body_parts.map((p) => [p.value, p.label])));
    expect([...SEASON_VALUES]).toEqual(vocabulary.seasons.map((s) => s.value));
  });

  it('has exact i18n keys for materials, formality and roles', () => {
    expect(sorted(Object.keys(constants.materials))).toEqual(sorted(vocabulary.materials));
    expect(sorted(Object.keys(constants.formalities))).toEqual(sorted(vocabulary.formality));
    expect(sorted(Object.keys(constants.roles))).toEqual(sorted(new Set(vocabulary.types.map((t) => t.role))));
  });

  it('does not compile the soft vocabulary into the bundle', () => {
    for (const name of ['CLOTHING_TYPE_VALUES', 'TYPE_ENTRIES', 'COLOR_VALUES', 'COLOR_FAMILY_VALUES', 'STYLE_VALUES', 'STYLE_LABELS', 'ITEM_ROLE']) {
      expect(generated).not.toHaveProperty(name);
    }
  });
});

describe('gen-garment-vocabulary --check', () => {
  const dir = mkdtempSync(join(tmpdir(), 'vocab-check-'));
  afterAll(() => rmSync(dir, { recursive: true, force: true }));

  const runCheck = (name: string, mutate: (v: typeof vocabulary) => void) => {
    const doc = structuredClone(vocabulary);
    mutate(doc);
    const file = join(dir, `${name}.json`);
    writeFileSync(file, JSON.stringify(doc));
    return spawnSync(process.execPath, ['scripts/gen-garment-vocabulary.mjs', '--check'], {
      cwd: resolve(__dirname, '..'),
      env: { ...process.env, VOCAB_SOURCE: file },
      encoding: 'utf8',
    });
  };

  it('accepts a runtime-added color', () => {
    const r = runCheck('ok', (v) => {
      v.colors.values.push({ value: 'teal-x', label: 'x', family: v.colors.families[0].value, hex: '#00aa99' });
    });
    expect(r.status).toBe(0);
  });

  it('rejects a color whose family is unknown', () => {
    const r = runCheck('bad-family', (v) => {
      v.colors.values.push({ value: 'ghost-color', label: 'x', family: 'nope', hex: '#00aa99' });
    });
    expect(r.status).toBe(1);
    expect(r.stderr).toContain('ghost-color');
  });

  it('rejects a type whose body part is unknown', () => {
    const r = runCheck('bad-part', (v) => {
      v.types[0].body_part = 'wings';
    });
    expect(r.status).toBe(1);
    expect(r.stderr).toContain(vocabulary.types[0].value);
  });
});
