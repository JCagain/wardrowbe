'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { Button } from '@/components/ui/button';
import { useEmbeddingStatus } from '@/lib/hooks/use-embeddings';
import { useSuggestForRegion } from '@/lib/hooks/use-records';
import type { GarmentRegion, RecordItem, SuggestCandidate, SuggestResponse } from '@/lib/types';

interface Props {
  recordId: string;
  photoId: string;
  region: GarmentRegion | null;
  linkedIds: Set<string>;
  onToggle: (item: RecordItem) => void;
}

function toRecordItem(c: SuggestCandidate): RecordItem {
  return { id: c.id, type: c.type, name: c.name ?? null, primary_colors: c.primary_colors, thumbnail_url: c.thumbnail_url ?? null };
}

export function SuggestPanel({ recordId, photoId, region, linkedIds, onToggle }: Props) {
  const t = useTranslations('history.records.suggest');
  const { data: status } = useEmbeddingStatus();
  const suggest = useSuggestForRegion();
  const [result, setResult] = useState<SuggestResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const regionKey = region ? JSON.stringify(region) : null;

  // 框变了（换选中 / 改框 / 改部位）→ 旧结果不再对应，清掉并取消在途请求
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setResult(null);
    setError(null);
  }, [regionKey]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const available = !!status?.available;

  const run = async () => {
    if (!region) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await suggest.mutateAsync({ id: recordId, photoId, region, signal: controller.signal });
      if (!controller.signal.aborted) setResult(res);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setRunning(false);
      }
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
  };

  return (
    <div className="space-y-2 rounded border p-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="secondary" data-testid="suggest-run"
          disabled={!region || !available || running} onClick={run}>
          {t('run')}
        </Button>
        {running && (
          <Button type="button" size="sm" variant="ghost" data-testid="suggest-cancel" onClick={cancel}>
            {t('cancel')}
          </Button>
        )}
        {status && !available && (
          <span data-testid="suggest-unavailable" className="text-xs text-muted-foreground">{t('unavailable')}</span>
        )}
        {!region && available && <span className="text-xs text-muted-foreground">{t('pickBox')}</span>}
      </div>
      {running && <p data-testid="suggest-running" className="text-xs text-muted-foreground">{t('running')}</p>}
      {error && <p role="alert" data-testid="suggest-error" className="text-sm text-destructive">{error}</p>}
      {result && result.candidates.length === 0 && (
        <p data-testid="suggest-empty" className="text-sm text-muted-foreground">{t('empty')}</p>
      )}
      {result && !result.reranked && result.candidates.length > 0 && (
        <p data-testid="suggest-not-reranked" className="text-xs text-muted-foreground">{t('notReranked')}</p>
      )}
      {result && result.candidates.length > 0 && (
        <ul data-testid="suggest-results" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {result.candidates.map((c) => {
            const linked = linkedIds.has(c.id);
            return (
              <li key={c.id}>
                <button type="button" data-testid={`suggest-candidate-${c.id}`} aria-pressed={linked}
                  onClick={() => onToggle(toRecordItem(c))}
                  className={`w-full rounded border p-1 text-left text-xs ${linked ? 'border-green-500 bg-green-500/10' : ''}`}>
                  {c.thumbnail_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={c.thumbnail_url} alt="" className="aspect-square w-full rounded object-cover" />
                  )}
                  <span className="block truncate">{c.name ?? c.type}</span>
                  {c.verdict && (
                    <span data-testid={`suggest-verdict-${c.id}`} className="text-muted-foreground">{t(`verdict.${c.verdict}`)}</span>
                  )}
                  {c.lifecycle === 'retired' && <span className="ml-1 text-muted-foreground">{t('retired')}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{t('pickHint')}</p>
    </div>
  );
}
