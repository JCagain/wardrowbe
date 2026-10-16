'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { GarmentRegionEditor } from '@/components/records/garment-region-editor';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useDetectGarmentRegions, useSaveGarmentRegions } from '@/lib/hooks/use-records';
import { useBodyParts } from '@/lib/hooks/use-translated-constants';
import type { GarmentRegion, RecordPhoto } from '@/lib/types';

interface Props {
  recordId: string;
  photo: RecordPhoto;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ApiError.message 已是后端 detail（见 lib/api.ts fetchApi）；网络错误是 NetworkError.message
function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function GarmentRegionsDialog({ recordId, photo, open, onOpenChange }: Props) {
  const t = useTranslations('history.records.regions');
  const bodyParts = useBodyParts();
  const detect = useDetectGarmentRegions();
  const save = useSaveGarmentRegions();
  const [regions, setRegions] = useState<GarmentRegion[]>(photo.garment_regions ?? []);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 签名 URL 含时间，refetch 会换 URL 导致 <img> 重载；对话框生命周期内冻结
  const [imageSrc] = useState(photo.image_url);
  const abortRef = useRef<AbortController | null>(null);

  const handleDetect = async () => {
    // 检出会整体替换，手改过的框会被冲掉——已有框时先确认
    if (regions.length > 0 && !window.confirm(t('replaceConfirm'))) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setDetecting(true);
    try {
      const res = await detect.mutateAsync({ id: recordId, photoId: photo.id, signal: controller.signal });
      if (!controller.signal.aborted) setRegions(res.regions);
    } catch (err) {
      if (!controller.signal.aborted) setError(errorText(err));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setDetecting(false);
      }
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setDetecting(false);
  };

  const handleSave = async () => {
    setError(null);
    try {
      await save.mutateAsync({ id: recordId, photoId: photo.id, regions });
      onOpenChange(false);
    } catch (err) {
      setError(errorText(err));
    }
  };

  // 框坐标是原图像素，所以用原图（image_url）而不是缩略/中图
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) handleCancel();
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="regions-detect"
              disabled={detecting}
              onClick={handleDetect}
            >
              {detecting ? t('detecting') : t('detect')}
            </Button>
            {detecting && (
              <Button type="button" variant="ghost" size="sm" data-testid="regions-cancel" onClick={handleCancel}>
                {t('cancel')}
              </Button>
            )}
          </div>
          {detecting && <p className="text-xs text-muted-foreground">{t('slowHint')}</p>}
          <GarmentRegionEditor
            imageSrc={imageSrc}
            regions={regions}
            bodyParts={bodyParts}
            onChange={setRegions}
          />
          {error && (
            <p role="alert" data-testid="regions-error" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-end">
            <Button type="button" data-testid="regions-save" disabled={save.isPending || detecting} onClick={handleSave}>
              {t('save')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
