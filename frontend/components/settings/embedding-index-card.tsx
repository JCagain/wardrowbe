'use client';

import { useTranslations } from 'next-intl';
import { Database } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getErrorMessage } from '@/lib/api';
import { useEmbeddingStatus, useSyncEmbeddings } from '@/lib/hooks/use-embeddings';

export function EmbeddingIndexCard() {
  const t = useTranslations('settings.embeddings');
  const { data } = useEmbeddingStatus();
  const sync = useSyncEmbeddings();

  const run = async (rebuild: boolean) => {
    if (rebuild && !window.confirm(t('rebuildConfirm'))) return;
    try {
      await sync.mutateAsync({ rebuild });
    } catch (e) {
      toast.error(getErrorMessage(e, t('syncFailed')));
    }
  };

  const busy = sync.isPending || (data?.job ?? 'idle') !== 'idle';
  const disabled = !data?.available || busy;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-5 w-5" />
          {t('title')}
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {data && !data.configured && (
          <p data-testid="embedding-unconfigured" className="text-sm text-muted-foreground">{t('unconfigured')}</p>
        )}
        {data?.configured && (
          <>
            <p data-testid="embedding-counts" className="text-sm">
              {t('counts', { embedded: data.embedded, total: data.total, stale: data.stale })}
            </p>
            {!data.available && (
              <p data-testid="embedding-unavailable" className="text-sm text-destructive">{t('unavailable')}</p>
            )}
            <p data-testid="embedding-job" className="text-xs text-muted-foreground">{t(`job.${data.job}`)}</p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" data-testid="embedding-sync" disabled={disabled} onClick={() => run(false)}>
                {t('sync')}
              </Button>
              <Button size="sm" variant="outline" data-testid="embedding-rebuild" disabled={disabled} onClick={() => run(true)}>
                {t('rebuild')}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
