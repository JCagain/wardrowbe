import { describe, expect, it } from 'vitest';

import { mapPointerToImage } from '@/components/mask-brush-canvas';

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
