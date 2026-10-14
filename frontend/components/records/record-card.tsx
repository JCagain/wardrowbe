'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { MapPin } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import type { OutfitRecord } from '@/lib/types';

export function RecordCard({ record }: { record: OutfitRecord }) {
  const t = useTranslations('history.records');
  const cover = record.photos[0];
  const w = record.weather;
  const hasTemps = !!w && (w.temp_low !== null || w.temp_high !== null);

  return (
    <Link href={`/dashboard/history/${record.id}`} className="block">
      <Card className="transition-colors hover:bg-muted/50">
        <CardContent className="flex gap-4 p-4">
          {cover && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              data-testid="record-card-cover"
              src={cover.thumbnail_url ?? cover.image_url}
              alt=""
              className="h-28 w-20 rounded object-cover"
            />
          )}
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {record.season && <span>{t(`seasons.${record.season}`)}</span>}
              {record.city && (
                <span data-testid="record-card-city" className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {record.city}
                </span>
              )}
              {hasTemps && (
                <span data-testid="record-card-temps">
                  {w!.temp_low ?? '–'}° / {w!.temp_high ?? '–'}°
                </span>
              )}
              {w?.condition && <span>{t(`conditions.${w.condition}`)}</span>}
            </div>
            {record.items.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {record.items.map((i) => (
                  <div
                    key={i.id}
                    data-testid="record-card-item"
                    className="h-10 w-10 overflow-hidden rounded border bg-muted"
                  >
                    {i.thumbnail_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={i.thumbnail_url} alt={i.name ?? i.type} className="h-full w-full object-cover" />
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">{t('noItems')}</p>
            )}
            {record.notes && <p className="truncate text-sm">{record.notes}</p>}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
