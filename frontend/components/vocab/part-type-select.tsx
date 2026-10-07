'use client';

import { useState } from 'react';
import { MoreHorizontal } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { BODY_PART_LABELS } from '@/lib/generated/garment-vocabulary';
import type { TypeEntry, VocabEntry } from '@/lib/types';
import { runVocabAction, type VocabEntryHandlers } from './vocab-managed-chip';

const ADD_OPTION = '__vocab_add__';

export function PartTypeSelect({
  parts,
  entries,
  bodyPart,
  type,
  onBodyPartChange,
  onTypeChange,
  entryHandlers,
  onAddEntry,
}: {
  parts: VocabEntry[];
  entries: TypeEntry[];
  bodyPart: string;
  type: string;
  onBodyPartChange: (value: string) => void;
  onTypeChange: (value: string) => void;
  /** Soft vocabulary: rename/disable the selected type, add a new one. */
  entryHandlers?: VocabEntryHandlers;
  onAddEntry?: () => void;
}) {
  const t = useTranslations('wardrobe.partTypeSelect');
  const vm = useTranslations('wardrobe.vocabManage');
  const va = useTranslations('wardrobe.vocabAdd');
  const [renameOpen, setRenameOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const selected = entries.find((e) => e.value === type);
  // Disabled types stay selectable for items that already carry them.
  const visible = entries.filter(
    (entry) => entry.body_part === bodyPart && (!entry.disabled || entry.value === type),
  );

  return (
    <div className="flex items-center gap-2">
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
          <option key={p.value} value={p.value}>
            {BODY_PART_LABELS[p.value as keyof typeof BODY_PART_LABELS] ?? p.label}
          </option>
        ))}
      </select>
      <select
        className="border rounded px-2 py-1"
        value={type}
        onChange={(e) => {
          if (e.target.value === ADD_OPTION) {
            onAddEntry?.();
            return;
          }
          onTypeChange(e.target.value);
        }}
      >
        <option value="">{t('type')}</option>
        {visible.map((entry) => (
          <option key={entry.value} value={entry.value}>{entry.label}</option>
        ))}
        {onAddEntry && <option value={ADD_OPTION}>{va('title.types')}</option>}
      </select>
      {entryHandlers && selected && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" aria-label={vm('menu')} className="border rounded p-1">
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem
              onSelect={() => {
                setDraft(selected.label);
                setRenameOpen(true);
              }}
            >
              {vm('rename')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => void runVocabAction(vm, () => entryHandlers.onDisable(selected.value))}
            >
              {vm('disable')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {entryHandlers && (
        <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>{vm('rename')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="rename-type">{vm('label')}</Label>
              <Input id="rename-type" value={draft} onChange={(e) => setDraft(e.target.value)} />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRenameOpen(false)}>
                {vm('cancel')}
              </Button>
              <Button
                onClick={async () => {
                  const next = draft.trim();
                  if (!next || !selected) return;
                  if (await runVocabAction(vm, () => entryHandlers.onRename(selected.value, next))) {
                    setRenameOpen(false);
                  }
                }}
              >
                {vm('save')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
