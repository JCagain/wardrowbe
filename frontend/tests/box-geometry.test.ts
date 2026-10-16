import { describe, expect, it } from 'vitest';
import { applyHandle, containsPoint, defaultNewBox, handlePoint } from '@/lib/box-geometry';

describe('box geometry', () => {
  const box = { l: 10, t: 20, r: 110, b: 220 };
  it('handle points sit on corners and edge midpoints', () => {
    expect(handlePoint(box, 'nw')).toEqual({ x: 10, y: 20 });
    expect(handlePoint(box, 'e')).toEqual({ x: 110, y: 120 });
  });
  it('dragging a handle never flips the box', () => {
    expect(applyHandle(box, 'nw', { x: 500, y: 500 })).toEqual({ l: 110, t: 220, r: 110, b: 220 });
  });
  it('containsPoint is inclusive of edges', () => {
    expect(containsPoint(box, { x: 10, y: 220 })).toBe(true);
    expect(containsPoint(box, { x: 9, y: 100 })).toBe(false);
  });
  it('default new box is centred at 30% size', () => {
    expect(defaultNewBox(1000, 500)).toEqual({ l: 350, t: 175, r: 650, b: 325 });
  });
});
