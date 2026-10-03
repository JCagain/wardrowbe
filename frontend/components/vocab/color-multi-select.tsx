'use client';

import type { ColorEntry } from '@/lib/types';

export function ColorMultiSelect({
  values,
  options,
  onChange,
}: {
  values: string[];
  options: ColorEntry[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((c) => {
        const active = values.includes(c.value);
        return (
          <button
            key={c.value}
            type="button"
            aria-pressed={active}
            onClick={() =>
              onChange(
                active ? values.filter((v) => v !== c.value) : [...values, c.value],
              )
            }
            className={`flex flex-col items-center rounded-md p-1 ${active ? 'ring-2 ring-primary' : ''}`}
          >
            <span className="block h-6 w-6 rounded" style={{ backgroundColor: c.hex }} />
            <span className="text-xs">{c.label}</span>
          </button>
        );
      })}
    </div>
  );
}
