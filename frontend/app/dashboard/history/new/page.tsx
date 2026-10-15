'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';
import { ChevronLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { RecordEditor } from '@/components/records/record-editor';

export default function NewRecordPage() {
  const t = useTranslations('history.records');
  const router = useRouter();
  const today = format(new Date(), 'yyyy-MM-dd');

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/dashboard/history" aria-label={t('newTitle')}>
            <ChevronLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">{t('newTitle')}</h1>
      </div>
      <RecordEditor today={today} onSaved={(r) => router.push(`/dashboard/history?date=${r.date}`)} />
    </div>
  );
}
