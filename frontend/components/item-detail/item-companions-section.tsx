'use client';

import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useItemCompanions } from '@/lib/hooks/use-items';
import { useClothingTypes } from '@/lib/hooks/use-translated-constants';

/** 常搭衣物（fixes #46，Ruling 70）：记录里共现次数 top 8，退役的标注。 */
export function ItemCompanionsSection({ itemId }: { itemId: string }) {
  const t = useTranslations('wardrobe.itemDetail');
  const types = useClothingTypes();
  const { data, isLoading, isError } = useItemCompanions(itemId);
  const typeLabel = (v: string) => types.find((e) => e.value === v)?.label ?? v;

  return (
    <div className="space-y-2 pt-2 border-t">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Users className="h-4 w-4 text-muted-foreground" />
        {t('companions.title')}
      </div>
      {isLoading ? null : isError ? (
        <p className="text-xs text-destructive">{t('companions.loadError')}</p>
      ) : !data || data.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('companions.empty')}</p>
      ) : (
        <ul className="grid grid-cols-2 gap-2">
          {data.map((c) => (
            <li key={c.id} className="flex items-center gap-2 rounded-md bg-muted/50 p-1.5 text-xs">
              <div className="h-8 w-8 flex-shrink-0 overflow-hidden rounded bg-muted">
                {c.thumbnail_url && (
                  <Image src={c.thumbnail_url} alt={c.name || typeLabel(c.type)} width={32} height={32} className="h-full w-full object-cover" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate">{c.name || typeLabel(c.type)}</p>
                <p className="text-muted-foreground">{t('companions.times', { count: c.count })}</p>
              </div>
              {c.lifecycle === 'retired' && (
                <Badge variant="outline" className="h-4 text-[10px]">{t('companions.retired')}</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
