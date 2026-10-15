'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useItemRecords } from '@/lib/hooks/use-records';

/** 反查（fixes #45，Ruling 69）：关联该衣物的全部记录，日期倒序，分页加载。 */
export function ItemRecordsSection({ itemId }: { itemId: string }) {
  const t = useTranslations('wardrobe.itemDetail');
  const { data, isLoading, isError, hasNextPage, isFetchingNextPage, fetchNextPage } = useItemRecords(itemId);
  const records = data?.pages.flatMap((p) => p.records) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  return (
    <div className="space-y-2 pt-2 border-t">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Calendar className="h-4 w-4 text-muted-foreground" />
        {t('records.title')}
        {total > 0 && <span className="text-xs text-muted-foreground">{t('records.count', { count: total })}</span>}
      </div>
      {isLoading ? null : isError ? (
        <p className="text-xs text-destructive">{t('records.loadError')}</p>
      ) : records.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('records.empty')}</p>
      ) : (
        <ul className="space-y-1.5">
          {records.map((r) => (
            <li key={r.id}>
              <Link
                href={`/dashboard/history/${r.id}`}
                className="flex items-center gap-2 rounded-md p-1 text-xs hover:bg-muted/50"
              >
                <div className="h-8 w-8 flex-shrink-0 overflow-hidden rounded bg-muted">
                  {r.photos[0]?.thumbnail_url && (
                    <Image src={r.photos[0].thumbnail_url} alt={r.date} width={32} height={32} className="h-full w-full object-cover" />
                  )}
                </div>
                <span className="whitespace-nowrap">{r.date}</span>
                {r.occasion && <span className="text-muted-foreground">{r.occasion}</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {hasNextPage && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          disabled={isFetchingNextPage}
          onClick={() => fetchNextPage()}
        >
          {t('records.loadMore')}
        </Button>
      )}
    </div>
  );
}
