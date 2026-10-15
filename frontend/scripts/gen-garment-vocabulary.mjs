#!/usr/bin/env node
// Writes lib/generated/garment-vocabulary.ts from the backend vocabulary file. Generated scope: the
// fixed sets (body parts, seasons, materials, formality) and their types. The soft lists (garment
// types, colors, styles, roles) are read at runtime via GET /vocabulary (spec section 2, fixes #51);
// --check validates their structure instead of mirroring them. Run with --check to fail when the
// committed output is stale or the soft lists are malformed. VOCAB_SOURCE overrides the JSON path
// (tests only). It reads ../backend, which is outside the frontend Docker build context, so it must
// never run from build or prebuild.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE = process.env.VOCAB_SOURCE
  ? resolve(process.env.VOCAB_SOURCE)
  : resolve(ROOT, '..', 'backend', 'app', 'data', 'garment_vocabulary.json');
const OUTPUT = resolve(ROOT, 'lib', 'generated', 'garment-vocabulary.ts');

const quote = (value) => `'${value}'`;
const key = (value) => (/^[A-Za-z_][A-Za-z0-9_]*$/.test(value) ? value : quote(value));
const list = (values) => `[${values.map(quote).join(', ')}] as const`;

function render({ body_parts, seasons, materials, formality }) {
  const json = (value) => JSON.stringify(value);
  return [
    '// Generated from backend/app/data/garment_vocabulary.json by scripts/gen-garment-vocabulary.mjs.',
    '// Do not edit by hand; run `npm run vocab:gen`.',
    `export const BODY_PART_VALUES = ${list(body_parts.map((p) => p.value))};`,
    `export const BODY_PART_LABELS = ${json(Object.fromEntries(body_parts.map((p) => [p.value, p.label])))} as const;`,
    `export const SEASON_VALUES = ${list(seasons.map((s) => s.value))};`,
    `export const MATERIAL_VALUES = ${list(materials)};`,
    `export const FORMALITY_VALUES = ${list(formality)};`,
    '',
    'export type BodyPart = (typeof BODY_PART_VALUES)[number];',
    'export type Season = (typeof SEASON_VALUES)[number];',
    'export type Material = (typeof MATERIAL_VALUES)[number];',
    'export type Formality = (typeof FORMALITY_VALUES)[number];',
    '',
  ].join('\n');
}

const SLUG = /^[a-z0-9-]+$/;
const HEX = /^#[0-9a-fA-F]{6}$/;

function validate(vocab) {
  const errors = [];
  const checkList = (name, entries) => {
    if (!Array.isArray(entries)) {
      errors.push(`${name}: expected an array`);
      return;
    }
    const seen = new Set();
    for (const entry of entries) {
      const slug = entry?.value;
      if (typeof slug !== 'string' || !SLUG.test(slug)) errors.push(`${name}: invalid slug ${JSON.stringify(slug)}`);
      else if (seen.has(slug)) errors.push(`${name}: duplicate slug ${slug}`);
      else seen.add(slug);
      if (typeof entry?.label !== 'string' || !entry.label.trim()) errors.push(`${name}: empty label for ${slug}`);
    }
  };
  checkList('types', vocab.types);
  checkList('colors.values', vocab.colors?.values);
  checkList('colors.families', vocab.colors?.families);
  checkList('styles', vocab.styles);

  const parts = new Set((vocab.body_parts ?? []).map((p) => p.value));
  for (const t of vocab.types ?? []) {
    if (!parts.has(t.body_part)) errors.push(`types: ${t.value} has unknown body_part ${JSON.stringify(t.body_part)}`);
    if (typeof t.role !== 'string' || !t.role.trim()) errors.push(`types: ${t.value} has empty role`);
  }
  const families = new Set((vocab.colors?.families ?? []).map((f) => f.value));
  for (const c of vocab.colors?.values ?? []) {
    if (!families.has(c.family)) errors.push(`colors.values: ${c.value} has unknown family ${JSON.stringify(c.family)}`);
    if (typeof c.hex !== 'string' || !HEX.test(c.hex)) errors.push(`colors.values: ${c.value} has invalid hex ${JSON.stringify(c.hex)}`);
  }
  return errors;
}

const vocab = JSON.parse(readFileSync(SOURCE, 'utf8'));
const errors = validate(vocab);
if (errors.length) {
  for (const message of errors) console.error(`vocab: ${message}`);
  process.exit(1);
}
const expected = render(vocab);

if (process.argv.includes('--check')) {
  const current = existsSync(OUTPUT) ? readFileSync(OUTPUT, 'utf8') : null;
  if (current !== expected) {
    console.error('garment-vocabulary.ts is out of date with backend/app/data/garment_vocabulary.json; run `npm run vocab:gen`.');
    process.exit(1);
  }
  console.log('vocab-check: OK');
} else {
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, expected);
  console.log(`Wrote ${OUTPUT}`);
}
