'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { clampToImage, mapPointerToImage } from '@/components/mask-brush-canvas';

/**
 * 参考框坐标契约（与 Task 6 R1 同一条）：全分辨率图像像素，`r`/`b` **含右下**
 * （同后端 `box=(l,t,r,b)` 契约——消费方喂 PIL 时才 +1）。拖拽换算复用
 * `mapPointerToImage`，越界 clamp 复用 `clampToImage`，不重写第二份。
 */
export type ReferenceBox = { l: number; t: number; r: number; b: number };
export type Baseline = 'gray' | 'white';

export type Detection = {
  kind: 'gray' | 'white';
  box: ReferenceBox;
  cards?: Partial<Record<'white' | 'gray' | 'black', ReferenceBox>>;
};

type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
const HANDLES: readonly HandleId[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

function handlePoint(box: ReferenceBox, handle: HandleId): { x: number; y: number } {
  const cx = (box.l + box.r) / 2;
  const cy = (box.t + box.b) / 2;
  switch (handle) {
    case 'nw': return { x: box.l, y: box.t };
    case 'n': return { x: cx, y: box.t };
    case 'ne': return { x: box.r, y: box.t };
    case 'e': return { x: box.r, y: cy };
    case 'se': return { x: box.r, y: box.b };
    case 's': return { x: cx, y: box.b };
    case 'sw': return { x: box.l, y: box.b };
    case 'w': return { x: box.l, y: cy };
  }
}

/**
 * 把拖到的点折进框：坐标就是含右下的图像像素——**不做 ±1 的开区间换算**，
 * 唯一的 +1 在后端 `calibrate` 内部。同时保证框不翻转（对边不许交叉）。
 */
function applyHandle(
  box: ReferenceBox,
  handle: HandleId,
  p: { x: number; y: number },
): ReferenceBox {
  const x = Math.round(p.x);
  const y = Math.round(p.y);
  switch (handle) {
    case 'nw': return { ...box, l: Math.min(x, box.r), t: Math.min(y, box.b) };
    case 'n': return { ...box, t: Math.min(y, box.b) };
    case 'ne': return { ...box, r: Math.max(x, box.l), t: Math.min(y, box.b) };
    case 'e': return { ...box, r: Math.max(x, box.l) };
    case 'se': return { ...box, r: Math.max(x, box.l), b: Math.max(y, box.t) };
    case 's': return { ...box, b: Math.max(y, box.t) };
    case 'sw': return { ...box, l: Math.min(x, box.r), b: Math.max(y, box.t) };
    case 'w': return { ...box, l: Math.min(x, box.r) };
  }
}

/**
 * 参考框框选器（R35）：显示 `detect` 端点返回的参考框，让用户看得见并改。
 *
 * - `<img>` 上覆一层 `<canvas>`：`detection.cards` 三框（白/灰/黑）都画，主参考
 *   （`detection.kind`）高亮且是可拖的那一框；只检出一块时只画 `detection.box`
 * - 四角 + 四边中点可拖，拖出图像边界 clamp 到 [0, naturalWidth]×[0, naturalHeight]
 * - 基准可切 灰卡 / 白纸（决定 `onApply` 的 `baseline`）
 * - 「应用」→ `onApply(box, baseline)`；「不用参考框」→ `onManual()`（改走色温/色调
 *   滑块，spec §1.2 兜底）
 */
const LINE_CSS_PX = 2;
const HANDLE_CSS_PX = 8;

// 1 个 CSS 像素对应多少图像像素（naturalWidth / 显示宽度）；未布局时按 1 兜底
function imageUnitsPerCssPx(canvas: HTMLCanvasElement, naturalWidth: number): number {
  const width = canvas.getBoundingClientRect().width;
  return width > 0 ? naturalWidth / width : 1;
}

export function ReferenceBoxEditor({
  imageSrc,
  detection,
  onApply,
  onManual,
}: {
  imageSrc: string;
  detection: Detection;
  onApply: (box: ReferenceBox, baseline: Baseline) => void;
  onManual: () => void;
}) {
  const t = useTranslations('wardrobe.pipeline');
  const [box, setBox] = useState<ReferenceBox>(detection.box);
  const [baseline, setBaseline] = useState<Baseline>(detection.kind);
  const [loaded, setLoaded] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragHandleRef = useRef<HandleId | null>(null);

  // 检出结果一变就回到新的主框（重新检测 = 重新开始）
  useEffect(() => {
    setBox(detection.box);
    setBaseline(detection.kind);
  }, [detection]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // 画布是原图分辨率、被 CSS 缩小：线宽/手柄按 CSS 像素定义再换算到图像空间
    const scale = imageUnitsPerCssPx(canvas, canvas.width);
    ctx.lineWidth = LINE_CSS_PX * scale;
    const handleSize = HANDLE_CSS_PX * scale;
    // 三联检出：三框都画，主参考高亮且是活的可拖框；单卡只画主框。
    const cards = detection.cards;
    const entries: Array<{ box: ReferenceBox; main: boolean }> = cards
      ? (['white', 'gray', 'black'] as const).flatMap((k) => {
          const cardBox = k === detection.kind ? box : cards[k];
          return cardBox ? [{ box: cardBox, main: k === detection.kind }] : [];
        })
      : [{ box, main: true }];
    for (const entry of entries) {
      ctx.strokeStyle = entry.main ? '#22c55e' : '#94a3b8';
      // strokeRect 的宽高 = r-l / b-t（含右下是取值契约，不是绘制单位）
      ctx.strokeRect(
        entry.box.l,
        entry.box.t,
        entry.box.r - entry.box.l,
        entry.box.b - entry.box.t,
      );
    }
    // 拖拽手柄（四角 + 四边中点）
    for (const handle of HANDLES) {
      const p = handlePoint(box, handle);
      ctx.fillRect(p.x - handleSize / 2, p.y - handleSize / 2, handleSize, handleSize);
    }
  }, [box, detection]);

  useEffect(() => {
    if (loaded) draw();
  }, [draw, loaded]);

  const handleImageLoad = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (img && canvas) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      setLoaded(true);
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
      // 手柄命中容差 ≈ 12 CSS 像素（换算到图像坐标空间）
      const tolerance = 12 * imageUnitsPerCssPx(canvas, img.naturalWidth);
      let hit: HandleId | null = null;
      let best = tolerance;
      for (const handle of HANDLES) {
        const hp = handlePoint(box, handle);
        const d = Math.hypot(hp.x - p.x, hp.y - p.y);
        if (d <= best) {
          best = d;
          hit = handle;
        }
      }
      if (!hit) return;
      dragHandleRef.current = hit;
      canvas.setPointerCapture(e.pointerId);
    },
    [box, pointFromEvent],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const handle = dragHandleRef.current;
      if (!handle) return;
      const p = pointFromEvent(e);
      if (!p) return;
      setBox((prev) => applyHandle(prev, handle, p));
    },
    [pointFromEvent],
  );

  const handlePointerUp = useCallback(() => {
    dragHandleRef.current = null;
  }, []);

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
          data-testid="box-baseline-gray"
          onClick={() => setBaseline('gray')}
          aria-pressed={baseline === 'gray'}
        >
          {t('grayCard')}
        </button>
        <button
          type="button"
          data-testid="box-baseline-white"
          onClick={() => setBaseline('white')}
          aria-pressed={baseline === 'white'}
        >
          {t('whitePaper')}
        </button>
      </div>
      <div>
        <button
          type="button"
          data-testid="box-apply"
          onClick={() => onApply(box, baseline)}
        >
          {t('apply')}
        </button>
        <button type="button" data-testid="box-manual" onClick={onManual}>
          {t('noReference')}
        </button>
      </div>
    </div>
  );
}
