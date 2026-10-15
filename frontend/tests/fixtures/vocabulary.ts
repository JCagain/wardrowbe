import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Vocabulary } from '@/lib/hooks/use-vocabulary';

// The shipped vocabulary document, read the same way the parity test does, so
// component tests can stand in for GET /vocabulary without a compiled copy.
const VOCABULARY_PATH = resolve(__dirname, '..', '..', '..', 'backend', 'app', 'data', 'garment_vocabulary.json');

export const VOCABULARY: Vocabulary = JSON.parse(readFileSync(VOCABULARY_PATH, 'utf8')) as Vocabulary;
