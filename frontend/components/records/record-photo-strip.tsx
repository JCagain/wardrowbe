'use client';

import { useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ImagePlus, RotateCcw, RotateCw, ScanSearch, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

export interface StripPhoto {
  key: string;
  src: string;
  regionCount?: number;
}

interface Props {
  photos: StripPhoto[];
  onAdd: (files: File[]) => void;
  onRemove: (key: string) => void;
  onRotate?: (key: string, dir: 'cw' | 'ccw') => void;
  onFrame?: (key: string) => void;
  canRemove: boolean;
}

export function RecordPhotoStrip({ photos, onAdd, onRemove, onRotate, onFrame, canRemove }: Props) {
  const t = useTranslations('history.records');
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex flex-wrap gap-3">
      {photos.map((p) => (
        <div key={p.key} className="relative h-32 w-24 overflow-hidden rounded-md border bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={p.src} alt="" className="h-full w-full object-cover" />
          {p.regionCount !== undefined && p.regionCount > 0 && (
            <span
              data-testid="record-photo-region-count"
              role="img"
              aria-label={t('regions.count', { count: p.regionCount })}
              className="absolute right-1 top-1 rounded-full bg-green-600 px-1.5 text-xs font-medium text-white"
            >
              {p.regionCount}
            </span>
          )}
          <div className="absolute inset-x-0 bottom-0 flex justify-between bg-black/40 p-1">
            {onRotate ? (
              <>
                <button type="button" aria-label={t('rotateLeft')} onClick={() => onRotate(p.key, 'ccw')}>
                  <RotateCcw className="h-4 w-4 text-white" />
                </button>
                <button type="button" aria-label={t('rotateRight')} onClick={() => onRotate(p.key, 'cw')}>
                  <RotateCw className="h-4 w-4 text-white" />
                </button>
              </>
            ) : (
              <span />
            )}
            {onFrame && (
              <button
                type="button"
                data-testid="record-photo-frame"
                aria-label={t('regions.open')}
                onClick={() => onFrame(p.key)}
              >
                <ScanSearch className="h-4 w-4 text-white" />
              </button>
            )}
            <button
              type="button"
              data-testid="record-photo-remove"
              aria-label={t('removePhoto')}
              disabled={!canRemove}
              onClick={() => onRemove(p.key)}
              className="disabled:opacity-40"
            >
              <X className="h-4 w-4 text-white" />
            </button>
          </div>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        className="h-32 w-24 flex-col gap-1"
        onClick={() => inputRef.current?.click()}
      >
        <ImagePlus className="h-5 w-5" />
        <span className="text-xs">{t('addPhotos')}</span>
      </Button>
      <input
        ref={inputRef}
        data-testid="record-photo-input"
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onAdd(files);
          e.target.value = '';
        }}
      />
    </div>
  );
}
