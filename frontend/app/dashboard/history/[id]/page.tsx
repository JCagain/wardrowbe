'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';
import { ChevronLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { RecordEditor } from '@/components/records/record-editor';
import { useRecord } from '@/lib/hooks/use-records';

export default function EditRecordPage() {
  const t = useTranslations('history');
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const { data: record, isLoading, isError } = useRecord(id);
  const today = format(new Date(), 'yyyy-MM-dd');

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/dashboard/history" aria-label={t('records.editTitle')}>
            <ChevronLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">{t('records.editTitle')}</h1>
      </div>
      {isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : isError || !record ? (
        <p className="text-red-500">{t('loadError')}</p>
      ) : (
        <RecordEditor
          key={record.id}
          record={record}
          today={today}
          onSaved={(r) => router.push(`/dashboard/history?date=${r.date}`)}
          onDeleted={() => router.push(`/dashboard/history?date=${record.date}`)}
        />
      )}
    </div>
  );
}
