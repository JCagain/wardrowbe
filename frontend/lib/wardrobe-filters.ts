import type { ColorEntry, ColorScope, ItemFilter, TypeEntry } from '@/lib/types';

type SingleKey = 'bodyPart' | 'type' | 'colorFamily' | 'color' | 'style' | 'season';

/** 衣橱网格的词表筛选维度（spec §4，fixes #40/#41，Ruling 66）。每维单值，'' = 不筛。 */
export interface VocabFilterState extends Record<SingleKey, string> {
  /** 色系/具体色按主色、辅色还是两者匹配；默认主色。 */
  colorScope: ColorScope;
}

export const EMPTY_VOCAB_FILTERS: VocabFilterState = {
  bodyPart: '',
  type: '',
  colorFamily: '',
  color: '',
  colorScope: 'primary',
  style: '',
  season: '',
};

const URL_KEYS: Record<SingleKey, string> = {
  bodyPart: 'part',
  type: 'type',
  colorFamily: 'family',
  color: 'color',
  style: 'style',
  season: 'season',
};
const SINGLE_KEYS = Object.keys(URL_KEYS) as SingleKey[];
const SCOPES: readonly ColorScope[] = ['primary', 'secondary', 'any'];

export function readVocabFilters(params: URLSearchParams): VocabFilterState {
  const out = { ...EMPTY_VOCAB_FILTERS };
  for (const key of SINGLE_KEYS) out[key] = params.get(URL_KEYS[key]) ?? '';
  // 旧书签：类别下拉曾用 'all' 哨兵值。
  if (out.type === 'all') out.type = '';
  const scope = params.get('colorScope') as ColorScope | null;
  out.colorScope = scope && SCOPES.includes(scope) ? scope : 'primary';
  return out;
}

export function writeVocabFilters(params: URLSearchParams, state: VocabFilterState): void {
  for (const key of SINGLE_KEYS) {
    if (state[key]) params.set(URL_KEYS[key], state[key]);
    else params.delete(URL_KEYS[key]);
  }
  if (state.colorScope !== 'primary') params.set('colorScope', state.colorScope);
  else params.delete('colorScope');
}

type VocabItemFilter = Pick<
  ItemFilter,
  'body_part' | 'type' | 'color_family' | 'colors' | 'color_scope' | 'style' | 'season'
>;

/** 网格查询与批量全选共用（Ruling 67）：两边同一份映射，全选不越过屏幕上的筛选。 */
export function vocabFiltersToItemFilter(state: VocabFilterState): VocabItemFilter {
  const out: VocabItemFilter = {};
  if (state.bodyPart) out.body_part = state.bodyPart;
  if (state.type) out.type = state.type;
  if (state.colorFamily) out.color_family = state.colorFamily;
  if (state.color) out.colors = [state.color];
  if ((state.colorFamily || state.color) && state.colorScope !== 'primary') {
    out.color_scope = state.colorScope;
  }
  if (state.style) out.style = state.style;
  if (state.season) out.season = state.season;
  return out;
}

/** 匹配范围是颜色维度的修饰，不单独计数。 */
export function countVocabFilters(state: VocabFilterState): number {
  return SINGLE_KEYS.filter((key) => state[key]).length;
}

/** 选项含停用词条：停用只是不进录入选择器，旧衣物仍带着它们（Ruling 66）。 */
export function typeOptionsFor(bodyPart: string, types: readonly TypeEntry[]): TypeEntry[] {
  return bodyPart ? types.filter((t) => t.body_part === bodyPart) : [...types];
}

export function colorOptionsFor(family: string, colors: readonly ColorEntry[]): ColorEntry[] {
  return family ? colors.filter((c) => c.family === family) : [...colors];
}

export function setBodyPart(
  state: VocabFilterState,
  bodyPart: string,
  types: readonly TypeEntry[],
): VocabFilterState {
  const keepType = !bodyPart || !state.type || types.some((t) => t.value === state.type && t.body_part === bodyPart);
  return { ...state, bodyPart, type: keepType ? state.type : '' };
}

export function setColorFamily(
  state: VocabFilterState,
  colorFamily: string,
  colors: readonly ColorEntry[],
): VocabFilterState {
  const keepColor =
    !colorFamily || !state.color || colors.some((c) => c.value === state.color && c.family === colorFamily);
  return { ...state, colorFamily, color: keepColor ? state.color : '' };
}
