import type { Dispatch, SetStateAction } from 'react';
import { formatPurchaseDate } from '@/lib/purchase-date';
import type { Item } from '@/lib/types';
import { TYPE_ENTRIES } from '@/lib/generated/garment-vocabulary';

// PartTypeSelect fires both callbacks in the same change event (picking a part
// resets the type). Value-form setters would both close over the same stale
// form and the second call would overwrite the first — so these must be
// functional updaters, each seeing the previous update's result.
export function partTypeChangeHandlers<T extends { body_part: string; type: string }>(
  setForm: Dispatch<SetStateAction<T>>,
) {
  return {
    onBodyPartChange: (bodyPart: string) =>
      setForm((prev) => ({ ...prev, body_part: bodyPart })),
    onTypeChange: (type: string) => setForm((prev) => ({ ...prev, type })),
  };
}

export interface EditForm {
  name: string;
  type: string;
  body_part: string;
  subtype: string;
  brand: string;
  primary_colors: string[];
  secondary_colors: string[];
  style: string[];
  temp_low: number | undefined;
  temp_high: number | undefined;
  purchase_date: string;
  purchase_price: number | undefined;
  lifecycle: 'active' | 'idle' | 'retired';
  is_archived: boolean;
  archive_reason: string;
  notes: string;
  favorite: boolean;
  wash_interval: number | undefined;
}

export function editFormFromItem(item: Item): EditForm {
  return {
    name: item.name || '',
    type: item.type,
    // Derive the part from the type when the item predates the body_part column.
    body_part:
      item.body_part || TYPE_ENTRIES.find((e) => e.value === item.type)?.body_part || '',
    // Pre-fill a rejected AI type as the subtype so picking the nearest
    // supported type doesn't lose what the model actually saw.
    subtype: item.subtype || (item.type === 'unknown' && item.ai_unrecognized_type) || '',
    brand: item.brand || '',
    primary_colors: item.primary_colors ?? [],
    secondary_colors: item.secondary_colors ?? [],
    style: item.tags.style ?? [],
    temp_low: item.temp_low ?? undefined,
    temp_high: item.temp_high ?? undefined,
    // Refill at the precision the user entered — the wire value is always
    // "YYYY-MM", and backing the raw value in rewrote year-only dates to
    // month precision on the first unrelated save.
    purchase_date: formatPurchaseDate(item.purchase_date, item.purchase_date_precision),
    purchase_price: item.purchase_price ?? undefined,
    // lifecycle is the authority; fall back to the compat view for older rows.
    lifecycle: item.lifecycle ?? (item.is_archived ? 'retired' : 'active'),
    is_archived: item.is_archived,
    archive_reason: item.archive_reason || '',
    notes: item.notes || '',
    favorite: item.favorite,
    wash_interval: item.wash_interval ?? undefined,
  };
}
