/**
 * 框几何（参考框编辑器与衣物框选器共用）：全分辨率图像像素，`r`/`b` **含右下**
 * （同后端 `box=(l,t,r,b)` 契约）。
 */
export type Box = { l: number; t: number; r: number; b: number };

export type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
export const HANDLES: readonly HandleId[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

export function handlePoint(box: Box, handle: HandleId): { x: number; y: number } {
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
export function applyHandle(
  box: Box,
  handle: HandleId,
  p: { x: number; y: number },
): Box {
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

export function containsPoint(box: Box, p: { x: number; y: number }): boolean {
  return p.x >= box.l && p.x <= box.r && p.y >= box.t && p.y <= box.b;
}

export function defaultNewBox(width: number, height: number): Box {
  const w = Math.round(width * 0.3);
  const h = Math.round(height * 0.3);
  const l = Math.round((width - w) / 2);
  const t = Math.round((height - h) / 2);
  return { l, t, r: l + w, b: t + h };
}
