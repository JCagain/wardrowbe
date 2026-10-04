'use client';

import type { VocabEntry } from '@/lib/types';
import { VocabAddChip, VocabManagedChip, type VocabEntryHandlers } from './vocab-managed-chip';

export function StyleMultiSelect({
  values,
  options,
  onChange,
  entryHandlers,
  onAddEntry,
}: {
  values: string[];
  options: VocabEntry[];
  onChange: (next: string[]) => void;
  entryHandlers?: VocabEntryHandlers;
  onAddEntry?: () => void;
}) {
  // Disabled entries stay selectable for items that already carry them.
  const visible = options.filter((o) => !o.disabled || values.includes(o.value));
  return (
    <div className="flex flex-wrap gap-2">
      {visible.map((s) => {
        const active = values.includes(s.value);
        return (
          <VocabManagedChip
            key={s.value}
            value={s.value}
            label={s.label}
            handlers={entryHandlers}
            active={active}
            onToggle={() =>
              onChange(
                active ? values.filter((v) => v !== s.value) : [...values, s.value],
              )
            }
          >
            <span className="px-2 py-1 text-sm">{s.label}</span>
          </VocabManagedChip>
        );
      })}
      {onAddEntry && <VocabAddChip kindLabel="style" onClick={onAddEntry} />}
    </div>
  );
}
