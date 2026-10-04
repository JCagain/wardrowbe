'use client';

import { useState } from 'react';
import { MoreHorizontal, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface VocabEntryHandlers {
  onRename: (value: string, label: string) => void | Promise<unknown>;
  onDisable: (value: string) => void | Promise<unknown>;
}

/** One picker chip with a hover ⋯ menu for rename/disable (soft vocabulary: never delete). */
export function VocabManagedChip({
  value,
  label,
  handlers,
  active,
  onToggle,
  children,
}: {
  value: string;
  label: string;
  handlers?: VocabEntryHandlers;
  active?: boolean;
  onToggle?: () => void;
  children: React.ReactNode;
}) {
  const t = useTranslations('wardrobe.vocabManage');
  const [renameOpen, setRenameOpen] = useState(false);
  const [draft, setDraft] = useState(label);

  return (
    <span className="relative group inline-flex items-start">
      <button
        type="button"
        aria-pressed={active}
        onClick={onToggle}
        className={`flex flex-col items-center rounded-md p-1 ${active ? 'ring-2 ring-primary' : ''}`}
      >
        {children}
      </button>
      {handlers && (
        <span className="absolute -right-1 -top-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={t('menu')}
                className="rounded-full bg-background/90 p-0.5 shadow"
              >
                <MoreHorizontal className="h-3 w-3" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem
                onSelect={() => {
                  setDraft(label);
                  setRenameOpen(true);
                }}
              >
                {t('rename')}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => handlers.onDisable(value)}>
                {t('disable')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </span>
      )}
      {handlers && (
        <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>{t('rename')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor={`rename-${value}`}>{t('label')}</Label>
              <Input id={`rename-${value}`} value={draft} onChange={(e) => setDraft(e.target.value)} />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRenameOpen(false)}>
                {t('cancel')}
              </Button>
              <Button
                onClick={async () => {
                  const next = draft.trim();
                  if (!next) {
                    toast.error(t('invalid'));
                    return;
                  }
                  await handlers.onRename(value, next);
                  setRenameOpen(false);
                }}
              >
                {t('save')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </span>
  );
}

/** Trailing chip that opens the add dialog for this picker. */
export function VocabAddChip({ kindLabel, onClick }: { kindLabel: string; onClick: () => void }) {
  const t = useTranslations('wardrobe.vocabManage');
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col items-center rounded-md border border-dashed p-1 text-muted-foreground hover:text-foreground"
    >
      <span className="flex h-6 w-6 items-center justify-center">
        <Plus className="h-4 w-4" />
      </span>
      <span className="text-xs">{t('addEntry', { kind: kindLabel })}</span>
    </button>
  );
}
