'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { clampToImage, mapPointerToImage } from '@/components/mask-brush-canvas';
import { applyHandle, containsPoint, defaultNewBox, handlePoint, HANDLES, type HandleId } from '@/lib/box-geometry';
import type { GarmentRegion } from '@/lib/types';

/**
 * 穿搭照衣物框选器（D7）：受控组件，框数据来自 props。坐标契约同参考框——全分辨率
 * 图像像素、`r`/`b` 含右下；换算复用 `mapPointerToImage` / `clampToImage`。
 *
 * 点框内选中（从后往前，后画的在上），拖选中框的手柄改尺寸。图下方的框标签按钮
 * 是等价的选择入口（无鼠标 / jsdom 下也能操作）。
 */
const LINE_CSS_PX = 2;
const HANDLE_CSS_PX = 8;
const LABEL_CSS_PX = 12;
// 与后端 GarmentRegionsUpdate.max_length 一致
const MAX_REGIONS = 12;
const SELECTED_COLOR = '#22c55e';
const OTHER_COLOR = '#94a3b8';
// 图片尚未加载（naturalWidth 为 0）时新增框的兜底尺寸
const FALLBACK_SIZE = 1000;

function imageUnitsPerCssPx(canvas: HTMLCanvasElement, naturalWidth: number): number {
  const width = canvas.getBoundingClientRect().width;
  return width > 0 ? naturalWidth / width : 1;
}

export function GarmentRegionEditor({
  imageSrc,
  regions,
  bodyParts,
  onChange,
  onSelectedChange,
}: {
  imageSrc: string;
  regions: GarmentRegion[];
  bodyParts: { value: string; label: string }[];
  onChange: (regions: GarmentRegion[]) => void;
  onSelectedChange?: (index: number | null) => void;
}) {
  const t = useTranslations('history.records.regions');
  const [selectedRaw, setSelected] = useState<number | null>(null);
  const [loadCount, setLoadCount] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragHandleRef = useRef<HandleId | null>(null);

  // 框列表被整体替换（重新检出）后，越界的选中项视为未选
  const selected = selectedRaw !== null && selectedRaw < regions.length ? selectedRaw : null;
  // 用 ref 持有回调：父组件每次渲染传新函数也不会重复触发
  const onSelectedChangeRef = useRef(onSelectedChange);
  onSelectedChangeRef.current = onSelectedChange;
  useEffect(() => {
    onSelectedChangeRef.current?.(selected);
  }, [selected]);
  const labelOf = useCallback(
    (part: string) => bodyParts.find((b) => b.value === part)?.label ?? part,
    [bodyParts],
  );

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const scale = imageUnitsPerCssPx(canvas, canvas.width);
    ctx.lineWidth = LINE_CSS_PX * scale;
    const handleSize = HANDLE_CSS_PX * scale;
    ctx.font = `${LABEL_CSS_PX * scale}px sans-serif`;
    regions.forEach((r, i) => {
      const color = i === selected ? SELECTED_COLOR : OTHER_COLOR;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.strokeRect(r.box.l, r.box.t, r.box.r - r.box.l, r.box.b - r.box.t);
      ctx.fillText(labelOf(r.body_part), r.box.l + 2 * scale, r.box.t + LABEL_CSS_PX * scale);
    });
    if (selected !== null) {
      ctx.fillStyle = SELECTED_COLOR;
      for (const handle of HANDLES) {
        const p = handlePoint(regions[selected].box, handle);
        ctx.fillRect(p.x - handleSize / 2, p.y - handleSize / 2, handleSize, handleSize);
      }
    }
  }, [regions, selected, labelOf]);

  // 每次图片 load 都重画：设置 canvas.width/height 会清空画布，且 load 可能重复触发
  useEffect(() => {
    if (loadCount > 0) draw();
  }, [draw, loadCount]);

  const handleImageLoad = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (img && canvas) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      setLoadCount((n) => n + 1);
    }
  }, []);

  const pointFromEvent = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>): { x: number; y: number } | null => {
      const img = imgRef.current;
      const canvas = canvasRef.current;
      if (!img || !canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const raw = mapPointerToImage(rect, e.clientX, e.clientY, img.naturalWidth, img.naturalHeight);
      return clampToImage(raw, img.naturalWidth, img.naturalHeight);
    },
    [],
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      const img = imgRef.current;
      const p = pointFromEvent(e);
      if (!canvas || !img || !p) return;
      e.preventDefault();
      // 先测选中框的手柄（≈12 CSS 像素容差），没命中再按从后往前找包含该点的框
      if (selected !== null) {
        const tolerance = 12 * imageUnitsPerCssPx(canvas, img.naturalWidth);
        let hit: HandleId | null = null;
        let best = tolerance;
        for (const handle of HANDLES) {
          const hp = handlePoint(regions[selected].box, handle);
          const d = Math.hypot(hp.x - p.x, hp.y - p.y);
          if (d <= best) {
            best = d;
            hit = handle;
          }
        }
        if (hit) {
          dragHandleRef.current = hit;
          canvas.setPointerCapture(e.pointerId);
          return;
        }
      }
      for (let i = regions.length - 1; i >= 0; i--) {
        if (containsPoint(regions[i].box, p)) {
          setSelected(i);
          return;
        }
      }
    },
    [regions, selected, pointFromEvent],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const handle = dragHandleRef.current;
      if (!handle || selected === null) return;
      const p = pointFromEvent(e);
      if (!p) return;
      onChange(
        regions.map((r, i) =>
          i === selected ? { ...r, box: applyHandle(r.box, handle, p), source: 'manual' } : r,
        ),
      );
    },
    [regions, selected, pointFromEvent, onChange],
  );

  const handlePointerUp = useCallback(() => {
    dragHandleRef.current = null;
  }, []);

  const handleAdd = () => {
    const img = imgRef.current;
    const w = img && img.naturalWidth > 0 ? img.naturalWidth : FALLBACK_SIZE;
    const h = img && img.naturalHeight > 0 ? img.naturalHeight : FALLBACK_SIZE;
    const part = bodyParts[0]?.value ?? 'tops';
    onChange([...regions, { body_part: part, box: defaultNewBox(w, h), source: 'manual' }]);
    setSelected(regions.length);
  };

  const handleDelete = () => {
    if (selected === null) return;
    onChange(regions.filter((_, i) => i !== selected));
    setSelected(null);
  };

  const handlePart = (value: string) => {
    if (selected === null) return;
    onChange(regions.map((r, i) => (i === selected ? { ...r, body_part: value, source: 'manual' } : r)));
  };

  return (
    <div className="space-y-3">
      <div style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imgRef}
          src={imageSrc}
          alt=""
          onLoad={handleImageLoad}
          style={{ display: 'block', maxWidth: '100%' }}
        />
        <canvas
          ref={canvasRef}
          data-testid="regions-canvas"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
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
      {regions.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('empty')}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {regions.map((r, i) => (
            <button
              key={i}
              type="button"
              data-testid={`region-chip-${i}`}
              aria-pressed={i === selected}
              onClick={() => setSelected(i)}
              className={`rounded border px-2 py-1 text-xs ${i === selected ? 'border-green-500 bg-green-500/10' : ''}`}
            >
              {labelOf(r.body_part)} {i + 1}
            </button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" data-testid="regions-add" disabled={regions.length >= MAX_REGIONS} className="rounded border px-2 py-1 text-sm disabled:opacity-40" onClick={handleAdd}>
          {t('add')}
        </button>
        <button
          type="button"
          data-testid="regions-delete"
          className="rounded border px-2 py-1 text-sm disabled:opacity-40"
          disabled={selected === null}
          onClick={handleDelete}
        >
          {t('delete')}
        </button>
        {selected !== null && (
          <select
            data-testid="regions-part"
            aria-label={t('part')}
            className="rounded border bg-background px-2 py-1 text-sm"
            value={regions[selected].body_part}
            onChange={(e) => handlePart(e.target.value)}
          >
            {bodyParts.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}
