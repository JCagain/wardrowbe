import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ReferenceBoxEditor,
  type Detection,
  type ReferenceBox,
} from '@/components/reference-box-editor';

// 框选器坐标契约（R35 / R1 同一条）：ReferenceBox 是全分辨率图像像素，
// r/b **含右下**（同后端 box=(l,t,r,b)；消费方喂 PIL 时才 +1）。
// 测试统一：800×600 原图，显示 rect 200×150 于 (0,0)，比例 ×4。
const NATURAL_W = 800;
const NATURAL_H = 600;
const RECT = { left: 0, top: 0, width: 200, height: 150 };

const BOX: ReferenceBox = { l: 100, t: 100, r: 300, b: 200 };

const SINGLE: Detection = { kind: 'gray', box: BOX };

const STRIP: Detection = {
  kind: 'gray',
  box: BOX,
  cards: {
    white: { l: 40, t: 40, r: 90, b: 90 },
    gray: BOX,
    black: { l: 400, t: 300, r: 500, b: 400 },
  },
};

type FakeCtx = {
  clearRect: ReturnType<typeof vi.fn>;
  strokeRect: ReturnType<typeof vi.fn>;
  fillRect: ReturnType<typeof vi.fn>;
  beginPath: ReturnType<typeof vi.fn>;
  arc: ReturnType<typeof vi.fn>;
  fill: ReturnType<typeof vi.fn>;
  stroke: ReturnType<typeof vi.fn>;
  save: ReturnType<typeof vi.fn>;
  restore: ReturnType<typeof vi.fn>;
  lineWidth: number;
};

function fakeCtx(): FakeCtx {
  return {
    clearRect: vi.fn(),
    strokeRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    lineWidth: 1,
  };
}

function setupDom(container: HTMLElement) {
  const img = container.querySelector('img') as HTMLImageElement;
  Object.defineProperty(img, 'naturalWidth', { value: NATURAL_W, configurable: true });
  Object.defineProperty(img, 'naturalHeight', { value: NATURAL_H, configurable: true });
  const canvas = container.querySelector('canvas') as HTMLCanvasElement;
  canvas.getBoundingClientRect = () =>
    ({ ...RECT, right: RECT.width, bottom: RECT.height, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
  fireEvent.load(img);
  return { img, canvas };
}

// 显示坐标 = 图像坐标 ÷ 4
function toClient(p: { x: number; y: number }) {
  return { clientX: p.x / 4, clientY: p.y / 4 };
}

function dragHandle(canvas: HTMLCanvasElement, from: { x: number; y: number }, to: { x: number; y: number }) {
  fireEvent.pointerDown(canvas, { pointerId: 1, ...toClient(from) });
  fireEvent.pointerMove(canvas, { pointerId: 1, ...toClient(to) });
  fireEvent.pointerUp(canvas, { pointerId: 1, ...toClient(to) });
}

let ctx: FakeCtx;

beforeEach(() => {
  ctx = fakeCtx();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  // jsdom 没有 pointer capture；组件按下时会调用
  HTMLCanvasElement.prototype.setPointerCapture = vi.fn();
  HTMLCanvasElement.prototype.releasePointerCapture = vi.fn();
});

describe('ReferenceBoxEditor', () => {
  // 画布是原图分辨率、被 CSS 缩小显示：线宽/手柄要乘 naturalWidth / rect.width，
  // 否则大图上约 0.1~0.5 CSS 像素，肉眼不可见。
  it('scales line width and handle size by natural/display ratio', () => {
    const scale = NATURAL_W / RECT.width;
    const widths: number[] = [];
    ctx.strokeRect.mockImplementation(() => widths.push(ctx.lineWidth));
    const { container } = render(
      <ReferenceBoxEditor imageSrc="item.png" detection={SINGLE} onApply={vi.fn()} onManual={vi.fn()} />,
    );
    setupDom(container);
    expect(widths.length).toBeGreaterThan(0);
    for (const w of widths) expect(w).toBeCloseTo(2 * scale);
    const [, , w, h] = ctx.fillRect.mock.calls[0] as number[];
    expect(w).toBeCloseTo(8 * scale);
    expect(h).toBeCloseTo(8 * scale);
  });

  // 钉子 5：detection.cards 三框都画到 canvas 上（三趟 stroke/rect）。
  it('draws all three card boxes from detection.cards', () => {
    const { container } = render(
      <ReferenceBoxEditor imageSrc="item.png" detection={STRIP} onApply={vi.fn()} onManual={vi.fn()} />,
    );
    setupDom(container);
    expect(ctx.strokeRect).toHaveBeenCalledTimes(3);
  });

  // 钉子 6：拖右下角改框 → onApply 收到的 r/b 变了、l/t 不变。
  it('lets the bottom-right corner drag change only r/b', () => {
    const onApply = vi.fn();
    const { container } = render(
      <ReferenceBoxEditor imageSrc="item.png" detection={SINGLE} onApply={onApply} onManual={vi.fn()} />,
    );
    const { canvas } = setupDom(container);

    // 右下角手柄在图像 (300,200) → client (75,50)；拖到图像 (400,320) → client (100,80)
    dragHandle(canvas, { x: 300, y: 200 }, { x: 400, y: 320 });
    fireEvent.click(screen.getByTestId('box-apply'));

    expect(onApply).toHaveBeenCalledTimes(1);
    const [box] = onApply.mock.calls[0] as [ReferenceBox];
    expect(box.r).not.toBe(BOX.r);
    expect(box.b).not.toBe(BOX.b);
    expect(box.l).toBe(BOX.l);
    expect(box.t).toBe(BOX.t);
  });

  // 钉子 7：含右下契约——换算成 PIL 开区间（+1）会在这里变红。
  it('reports the dragged corner as inclusive bottom-right image pixels', () => {
    const onApply = vi.fn();
    const { container } = render(
      <ReferenceBoxEditor imageSrc="item.png" detection={SINGLE} onApply={onApply} onManual={vi.fn()} />,
    );
    const { canvas } = setupDom(container);

    dragHandle(canvas, { x: 300, y: 200 }, { x: 400, y: 320 });
    fireEvent.click(screen.getByTestId('box-apply'));

    // 拖到 (400,320) 就该报 (400,320)，不是开区间的 (401,321)
    expect(onApply.mock.calls[0][0]).toEqual({ l: 100, t: 100, r: 400, b: 320 });
  });

  // 钉子 8（T7-A）：拖出边界 → 框夹在 [0, naturalWidth]×[0, naturalHeight]。
  it('clamps a dragged box to the image bounds', () => {
    const onApply = vi.fn();
    const { container } = render(
      <ReferenceBoxEditor imageSrc="item.png" detection={SINGLE} onApply={onApply} onManual={vi.fn()} />,
    );
    const { canvas } = setupDom(container);

    // 右下角拖到图外（映射到 (8000,8000)）
    dragHandle(canvas, { x: 300, y: 200 }, { x: 2000, y: 2000 });
    // 左上角拖到负坐标
    dragHandle(canvas, { x: 100, y: 100 }, { x: -200, y: -200 });
    fireEvent.click(screen.getByTestId('box-apply'));

    const [box] = onApply.mock.calls[0] as [ReferenceBox];
    expect(box).toEqual({ l: 0, t: 0, r: NATURAL_W, b: NATURAL_H });
  });

  // 钉子 9：baseline 切到白纸 → onApply 第二参是 'white'。
  it('passes the selected baseline through to onApply', () => {
    const onApply = vi.fn();
    render(
      <ReferenceBoxEditor imageSrc="item.png" detection={SINGLE} onApply={onApply} onManual={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('box-baseline-white'));
    fireEvent.click(screen.getByTestId('box-apply'));
    expect(onApply).toHaveBeenCalledWith(expect.anything(), 'white');
  });

  // 钉子 10：「不用参考框」触发 onManual。
  it('fires onManual from the no-reference action', () => {
    const onManual = vi.fn();
    render(
      <ReferenceBoxEditor imageSrc="item.png" detection={SINGLE} onApply={vi.fn()} onManual={onManual} />,
    );
    fireEvent.click(screen.getByTestId('box-manual'));
    expect(onManual).toHaveBeenCalledTimes(1);
  });
});
