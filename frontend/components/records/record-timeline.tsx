'use client';

import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { RecordCard } from '@/components/records/record-card';
import { useRecordTimeline } from '@/lib/hooks/use-records';
import type { OutfitRecord } from '@/lib/types';

function groupByDate(records: OutfitRecord[]): [string, OutfitRecord[]][] {
  const groups = new Map<string, OutfitRecord[]>();
  for (const r of records) {
    const list = groups.get(r.date);
    if (list) list.push(r);
    else groups.set(r.date, [r]);
  }
  return Array.from(groups.entries());
}

/** 记录时间线（fixes #47，Ruling 71）：全部记录日期倒序，按日分组，每页 30 条。 */
export function RecordTimeline({ empty }: { empty: React.ReactNode }) {
  const t = useTranslations('history');
  const { data, isLoading, isError, hasNextPage, isFetchingNextPage, fetchNextPage } = useRecordTimeline();
  const records = data?.pages.flatMap((p) => p.records) ?? [];

  if (isLoading) return null;
  if (isError) return <p className="py-8 text-center text-red-500">{t('loadError')}</p>;
  if (records.length === 0) return <>{empty}</>;

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t('timeline.count', { count: data?.pages[0]?.total ?? 0 })}</p>
      {groupByDate(records).map(([date, list]) => (
        <section key={date} className="space-y-3">
          <h3 className="border-b pb-1 text-sm font-semibold">{date}</h3>
          {list.map((r) => (
            <RecordCard key={r.id} record={r} />
          ))}
        </section>
      ))}
      {hasNextPage && (
        <div className="flex justify-center">
          <Button variant="outline" disabled={isFetchingNextPage} onClick={() => fetchNextPage()}>
            {t('timeline.loadMore')}
          </Button>
        </div>
      )}
    </div>
  );
}
