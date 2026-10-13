'use client';

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { api, getErrorMessage, type MaskStroke } from '@/lib/api';
import type { Item } from '@/lib/types';

/**
 * 显示坐标 → 全分辨率 mask 像素（R1）。纯函数，前端测试只钉它。
 *
 * x/y/radius 一律是全分辨率 mask 像素；比例换算只在这里发生，
 * 后端 apply_strokes 不做任何缩放。
 */
export function mapPointerToImage(
  rect: { left: number; top: number; width: number; height: number },
  clientX: number,
  clientY: number,
  naturalWidth: number,
  naturalHeight: number,
): { x: number; y: number } {
  return {
    x: (clientX - rect.left) * (naturalWidth / rect.width),
    y: (clientY - rect.top) * (naturalHeight / rect.height),
  };
}

/** 显示空间的画笔半径（CSS 像素）；POST 前按 naturalWidth / rect.width 缩放。 */
const BRUSH_RADIUS_DISPLAY = 12;

interface MaskBrushCanvasProps {
  imageSrc: string;
  itemId: string;
  onSaved?: (item: Item) => void;
}

export default function MaskBrushCanvas({ imageSrc, itemId, onSaved }: MaskBrushCanvasProps) {
  const t = useTranslations('common');
  const [mode, setMode] = useState<MaskStroke['mode']>('add');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // 一笔拖动 = 一串 dab；松手才整串 POST
  const strokeRef = useRef<{
    strokes: MaskStroke[];
    snapshot: ImageData | null;
    dragging: boolean;
  }>({ strokes: [], snapshot: null, dragging: false });

  const handleImageLoad = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (img && canvas) {
      // canvas 以原生分辨率落笔，CSS 拉到显示尺寸：预览与落盘同一坐标空间
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
  }, []);

  const pointFromEvent = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>): MaskStroke | null => {
      const img = imgRef.current;
      const canvas = canvasRef.current;
      if (!img || !canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const { x, y } = mapPointerToImage(
        rect,
        e.clientX,
        e.clientY,
        img.naturalWidth,
        img.naturalHeight,
      );
      // radius 同样按 naturalWidth / rect.width 缩放，取整、下限 1（R1）
      const radius = Math.max(
        1,
        Math.round((BRUSH_RADIUS_DISPLAY * img.naturalWidth) / rect.width),
      );
      return { x: Math.round(x), y: Math.round(y), radius, mode };
    },
    [mode],
  );

  const drawDab = useCallback((dab: MaskStroke) => {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    ctx.beginPath();
    ctx.arc(dab.x, dab.y, dab.radius, 0, Math.PI * 2);
    ctx.fillStyle = dab.mode === 'add' ? 'rgba(255, 255, 255, 0.45)' : 'rgba(0, 0, 0, 0.45)';
    ctx.fill();
  }, []);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (saving) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      e.preventDefault();
      canvas.setPointerCapture(e.pointerId);
      const ctx = canvas.getContext('2d');
      strokeRef.current = {
        strokes: [],
        snapshot: ctx ? ctx.getImageData(0, 0, canvas.width, canvas.height) : null,
        dragging: true,
      };
      const dab = pointFromEvent(e);
      if (dab) {
        strokeRef.current.strokes.push(dab);
        drawDab(dab);
      }
    },
    [drawDab, pointFromEvent, saving],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (!strokeRef.current.dragging) return;
      const dab = pointFromEvent(e);
      if (dab) {
        strokeRef.current.strokes.push(dab);
        drawDab(dab);
      }
    },
    [drawDab, pointFromEvent],
  );

  const handlePointerUp = useCallback(
    async (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (!strokeRef.current.dragging) return;
      strokeRef.current.dragging = false;
      const dab = pointFromEvent(e);
      if (dab) {
        strokeRef.current.strokes.push(dab);
        drawDab(dab);
      }
      const strokes = strokeRef.current.strokes;
      const snapshot = strokeRef.current.snapshot;
      strokeRef.current = { strokes: [], snapshot: null, dragging: false };
      if (strokes.length === 0) return;

      setSaving(true);
      setError(null);
      try {
        const item = await api.editItemMask<Item>(itemId, strokes);
        onSaved?.(item);
      } catch (err) {
        // 失败时回滚这一笔的预览：服务端没认，画面不能装作认了
        const ctx = canvasRef.current?.getContext('2d');
        if (ctx && snapshot) ctx.putImageData(snapshot, 0, 0);
        setError(getErrorMessage(err, t('somethingWentWrong')));
      } finally {
        setSaving(false);
      }
    },
    [drawDab, itemId, onSaved, pointFromEvent, t],
  );

  return (
    <div>
      <div style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}>
        <img
          ref={imgRef}
          src={imageSrc}
          alt=""
          onLoad={handleImageLoad}
          style={{ display: 'block', maxWidth: '100%' }}
        />
        <canvas
          ref={canvasRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            cursor: 'crosshair',
            touchAction: 'none',
          }}
        />
      </div>
      <div>
        <button
          type="button"
          onClick={() => setMode('add')}
          aria-pressed={mode === 'add'}
          disabled={saving}
        >
          {t('add')}
        </button>
        <button
          type="button"
          onClick={() => setMode('subtract')}
          aria-pressed={mode === 'subtract'}
          disabled={saving}
        >
          {t('remove')}
        </button>
      </div>
      {error ? <p>{error}</p> : null}
    </div>
  );
}
