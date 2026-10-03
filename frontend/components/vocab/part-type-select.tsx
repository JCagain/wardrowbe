'use client';

import { useTranslations } from 'next-intl';
import type { TypeEntry, VocabEntry } from '@/lib/types';

export function PartTypeSelect({
  parts,
  entries,
  bodyPart,
  type,
  onBodyPartChange,
  onTypeChange,
}: {
  parts: VocabEntry[];
  entries: TypeEntry[];
  bodyPart: string;
  type: string;
  onBodyPartChange: (value: string) => void;
  onTypeChange: (value: string) => void;
}) {
  const t = useTranslations('wardrobe.partTypeSelect');
  return (
    <div className="flex gap-2">
      <select
        className="border rounded px-2 py-1"
        value={bodyPart}
        onChange={(e) => {
          onBodyPartChange(e.target.value);
          onTypeChange('');
        }}
      >
        <option value="">{t('bodyPart')}</option>
        {parts.map((p) => (
          <option key={p.value} value={p.value}>{p.label}</option>
        ))}
      </select>
      <select
        className="border rounded px-2 py-1"
        value={type}
        onChange={(e) => onTypeChange(e.target.value)}
      >
        <option value="">{t('type')}</option>
        {entries
          .filter((entry) => entry.body_part === bodyPart)
          .map((entry) => (
            <option key={entry.value} value={entry.value}>{entry.label}</option>
          ))}
      </select>
    </div>
  );
}
