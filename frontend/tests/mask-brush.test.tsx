import { fireEvent, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MaskBrushCanvas, { clampToImage, mapPointerToImage } from '@/components/mask-brush-canvas';

// R1：显示坐标 → 全分辨率 mask 像素，换算必须是纯函数（前端测试只钉它）。
// 三个用例各有钉子：H 钉比例换算、I 钉 rect 平移、J 钉两轴独立缩放。
describe('mapPointerToImage', () => {
  it('maps a 200x150 display box onto an 800x600 natural image', () => {
    const rect = { left: 0, top: 0, width: 200, height: 150 };
    expect(mapPointerToImage(rect, 100, 75, 800, 600)).toEqual({ x: 400, y: 300 });
  });

  it('subtracts the rect offset when the display box is not at the origin', () => {
    const rect = { left: 40, top: 30, width: 200, height: 150 };
    expect(mapPointerToImage(rect, 40, 30, 800, 600)).toEqual({ x: 0, y: 0 });
    // 同一指针位置在偏移 rect 里不能再映射到 (100, 75)
    expect(mapPointerToImage(rect, 140, 105, 800, 600)).toEqual({ x: 400, y: 300 });
  });

  it('scales each axis independently for a non-4:3 display box', () => {
    // 显示 200×200、原图 800×600：x×4、y×3，按「一套比例」算会错
    const rect = { left: 0, top: 0, width: 200, height: 200 };
    expect(mapPointerToImage(rect, 100, 100, 800, 600)).toEqual({ x: 400, y: 300 });
  });
});

// T7-A：setPointerCapture 下拖出画布会产生负坐标/超界坐标，不夹紧就会被
// MaskStrokeIn 的 ge=0 整批 422 回滚。边界作画是画笔最常见的手势。
describe('clampToImage', () => {
  it('returns boundary values for points dragged outside the canvas', () => {
    expect(clampToImage({ x: -10, y: 700 }, 800, 600)).toEqual({ x: 0, y: 600 });
    expect(clampToImage({ x: 900, y: -5 }, 800, 600)).toEqual({ x: 800, y: 0 });
    expect(clampToImage({ x: -1, y: -1 }, 800, 600)).toEqual({ x: 0, y: 0 });
  });

  it('leaves interior points alone', () => {
    expect(clampToImage({ x: 400, y: 300 }, 800, 600)).toEqual({ x: 400, y: 300 });
    expect(clampToImage({ x: 800, y: 600 }, 800, 600)).toEqual({ x: 800, y: 600 });
  });
});

// T7-B：每个 pointermove 一个 dab 会把长拖拽顶到 MaskEditIn.strokes 的
// max_length=2000，然后 422 整批回滚。只记距离 ≥ radius*0.3 的点，两端必记。
describe('MaskBrushCanvas dab thinning', () => {
  const NATURAL_W = 800;
  const NATURAL_H = 600;
  const RECT = { left: 0, top: 0, width: 200, height: 150 };

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      clearRect: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      beginPath: vi.fn(),
      getImageData: vi.fn(() => ({})),
      putImageData: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    HTMLCanvasElement.prototype.setPointerCapture = vi.fn();
    HTMLCanvasElement.prototype.releasePointerCapture = vi.fn();
  });

  it('records far fewer dabs than pointer events on a long drag, endpoints included', async () => {
    const fetchMock = vi.mocked(global.fetch);
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'item-1' }),
    } as Response);

    const { container } = render(<MaskBrushCanvas imageSrc="item.png" itemId="item-1" />);
    const img = container.querySelector('img') as HTMLImageElement;
    Object.defineProperty(img, 'naturalWidth', { value: NATURAL_W, configurable: true });
    Object.defineProperty(img, 'naturalHeight', { value: NATURAL_H, configurable: true });
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    canvas.getBoundingClientRect = () =>
      ({ ...RECT, right: RECT.width, bottom: RECT.height, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    fireEvent.load(img);

    // 一条 100 事件的水平直线：图像 (0,300) → (400,300)
    const start = { clientX: 0, clientY: 75 };
    const end = { clientX: 100, clientY: 75 };
    fireEvent.pointerDown(canvas, { pointerId: 1, ...start });
    for (let i = 1; i <= 99; i++) {
      fireEvent.pointerMove(canvas, { pointerId: 1, clientX: i, clientY: 75 });
    }
    fireEvent.pointerUp(canvas, { pointerId: 1, ...end });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    const strokes = body.strokes as Array<{ x: number; y: number }>;

    // 事件数 101（down + 99 move + up）；抽稀后 dab 数必须远少于它
    expect(strokes.length).toBeLessThan(50);
    expect(strokes[0]).toMatchObject({ x: 0, y: 300 });
    expect(strokes[strokes.length - 1]).toMatchObject({ x: 400, y: 300 });
  });
});
