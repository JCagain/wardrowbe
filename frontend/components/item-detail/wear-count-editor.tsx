'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUpdateItem } from '@/lib/hooks/use-items';
import type { Item } from '@/lib/types';

/**
 * 手改穿着次数（fixes #43，Ruling 68）。独立于编辑表单、只发 wear_count：
 * 表单里的旧值不会把记录刚加减过的次数写回去。
 */
export function WearCountEditor({ item }: { item: Pick<Item, 'id' | 'wear_count'> }) {
  const t = useTranslations('wardrobe.itemDetail');
  const updateItem = useUpdateItem();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const save = async () => {
    if (!/^\d+$/.test(draft.trim())) {
      toast.error(t('wearCount.invalid'));
      return;
    }
    try {
      await updateItem.mutateAsync({ id: item.id, data: { wear_count: Number(draft.trim()) } });
      toast.success(t('wearCount.saved'));
      setEditing(false);
    } catch {
      toast.error(t('wearCount.saveError'));
    }
  };

  if (!editing) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{t('wearCount.label')}</span>
        <span className="font-medium">{item.wear_count}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={() => {
            setDraft(String(item.wear_count));
            setEditing(true);
          }}
        >
          {t('wearCount.edit')}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Input
          aria-label={t('wearCount.label')}
          type="number"
          min={0}
          step={1}
          inputMode="numeric"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="h-8 w-24"
        />
        <Button size="sm" className="h-8" onClick={save} disabled={updateItem.isPending}>
          {t('wearCount.save')}
        </Button>
        <Button size="sm" variant="ghost" className="h-8" onClick={() => setEditing(false)}>
          {t('wearCount.cancel')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('wearCount.hint')}</p>
    </div>
  );
}
