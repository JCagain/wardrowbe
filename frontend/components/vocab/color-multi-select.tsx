'use client';

import type { ColorEntry } from '@/lib/types';
import { VocabAddChip, VocabManagedChip, type VocabEntryHandlers } from './vocab-managed-chip';

export function ColorMultiSelect({
  values,
  options,
  onChange,
  entryHandlers,
  onAddEntry,
}: {
  values: string[];
  options: ColorEntry[];
  onChange: (next: string[]) => void;
  entryHandlers?: VocabEntryHandlers;
  onAddEntry?: () => void;
}) {
  // Disabled entries stay selectable for items that already carry them.
  const visible = options.filter((c) => !c.disabled || values.includes(c.value));
  return (
    <div className="flex flex-wrap gap-2">
      {visible.map((c) => {
        const active = values.includes(c.value);
        return (
          <VocabManagedChip
            key={c.value}
            value={c.value}
            label={c.label}
            handlers={entryHandlers}
            active={active}
            onToggle={() =>
              onChange(
                active ? values.filter((v) => v !== c.value) : [...values, c.value],
              )
            }
          >
            <span className="block h-6 w-6 rounded" style={{ backgroundColor: c.hex }} />
            <span className="text-xs">{c.label}</span>
          </VocabManagedChip>
        );
      })}
      {onAddEntry && <VocabAddChip kind="color" onClick={onAddEntry} />}
    </div>
  );
}
