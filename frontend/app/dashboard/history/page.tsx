'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Calendar, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { format, isSameDay, parseISO } from 'date-fns';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { OutfitCalendar } from '@/components/outfit-calendar';
import { RecordCard } from '@/components/records/record-card';
import { useRecords } from '@/lib/hooks/use-records';

function EmptyHistory({ t }: { t: (key: string) => string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="rounded-full bg-muted p-6 mb-4">
        <Calendar className="h-12 w-12 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold mb-2">{t('empty.title')}</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">
        {t('empty.description')}
      </p>
      <Button variant="outline" asChild>
        <Link href="/dashboard/history/new">{t('records.new')}</Link>
      </Button>
    </div>
  );
}

function EmptyDate({ date, t }: { date: Date; t: (key: string, params?: Record<string, string | number>) => string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <Calendar className="h-8 w-8 text-muted-foreground mb-2" />
      <p className="text-sm text-muted-foreground">
        {t('noOutfitsForDate', { date: format(date, 'MMMM d, yyyy') })}
      </p>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <Skeleton className="h-5 w-24 mb-2" />
                <Skeleton className="h-5 w-16" />
              </div>
              <Skeleton className="h-5 w-5" />
            </div>
            <div className="flex gap-2">
              {[1, 2, 3].map((j) => (
                <Skeleton key={j} className="w-16 h-16 rounded" />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-8 w-8" />
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-8 w-8" />
      </div>
      <div className="grid grid-cols-7 gap-1">
        {[...Array(35)].map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-md" />
        ))}
      </div>
    </div>
  );
}

function monthRange(year: number, month: number): [string, string] {
  const last = new Date(year, month, 0).getDate();
  const mm = String(month).padStart(2, '0');
  return [`${year}-${mm}-01`, `${year}-${mm}-${String(last).padStart(2, '0')}`];
}

export default function HistoryPage() {
  const t = useTranslations('history');
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selectedDate, setSelectedDate] = useState<Date | null>(now);

  const [from, to] = monthRange(year, month);
  const { data, isLoading, isError } = useRecords(from, to);
  const records = useMemo(() => data?.records ?? [], [data]);

  const markedDates = useMemo(() => new Set(records.map((r) => r.date)), [records]);
  const selectedRecords = useMemo(
    () => (selectedDate ? records.filter((r) => isSameDay(parseISO(r.date), selectedDate)) : []),
    [records, selectedDate]
  );

  if (isError) {
    return <div className="py-8 text-center text-red-500">{t('loadError')}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        <Button asChild>
          <Link href="/dashboard/history/new">
            <Plus className="mr-1 h-4 w-4" />
            {t('records.new')}
          </Link>
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[350px_1fr]">
        <Card className="order-2 h-fit lg:order-1">
          <CardContent className="p-4">
            {isLoading ? (
              <CalendarSkeleton />
            ) : (
              <OutfitCalendar
                year={year}
                month={month}
                outfits={[]}
                markedDates={markedDates}
                selectedDate={selectedDate}
                onSelectDate={setSelectedDate}
                onMonthChange={(y, m) => {
                  setYear(y);
                  setMonth(m);
                }}
              />
            )}
          </CardContent>
        </Card>

        <div className="order-1 space-y-4 lg:order-2">
          {selectedDate && (
            <div className="border-b pb-3">
              <h2 className="text-lg font-semibold">{format(selectedDate, 'yyyy-MM-dd')}</h2>
              <p className="text-sm text-muted-foreground">
                {t('outfitCount', { count: selectedRecords.length })}
              </p>
            </div>
          )}
          {isLoading ? (
            <LoadingSkeleton />
          ) : records.length === 0 ? (
            <EmptyHistory t={t} />
          ) : selectedDate && selectedRecords.length === 0 ? (
            <EmptyDate date={selectedDate} t={t} />
          ) : (
            selectedRecords.map((r) => <RecordCard key={r.id} record={r} />)
          )}
        </div>
      </div>
    </div>
  );
}
