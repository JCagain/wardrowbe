import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ImagePipelineSteps } from '@/components/image-pipeline-steps';

// tests/setup.ts stubs next-intl globally; pin 4 needs real catalog resolution, so
// this file runs against the real module and wraps every render in a provider
// (same pattern as subtype-label.test.tsx).
vi.unmock('next-intl');

const en = JSON.parse(
  readFileSync(resolve(__dirname, '..', 'messages', 'en', 'wardrobe.json'), 'utf8'),
);

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="en" messages={{ wardrobe: en }}>
      {children}
    </NextIntlClientProvider>
  );
}

const handlers = () => ({
  onCalibrate: vi.fn(),
  onCutout: vi.fn(),
  onTag: vi.fn(),
});

describe('ImagePipelineSteps', () => {
  // R36 钉子 1：三步顺序就是 spec 顺序（校色 → 抠图 → 打标）。结构化断言，
  // 不钉中文串——next-intl 的 en 源是英文，stub 下也拿不到中文。
  it('renders the three steps in spec order: calibrate, cutout, tag', () => {
    render(
      <ImagePipelineSteps
        calibration="none"
        hasMask={false}
        tagged={false}
        {...handlers()}
      />,
      { wrapper: Wrapper },
    );
    const steps = screen.getAllByRole('listitem');
    expect(steps).toHaveLength(3);
    expect(within(steps[0]).getByTestId('pipeline-calibrate')).toBeInTheDocument();
    expect(within(steps[1]).getByTestId('pipeline-cutout')).toBeInTheDocument();
    expect(within(steps[2]).getByTestId('pipeline-tag')).toBeInTheDocument();
  });

  // R36 钉子 2 —— D2 门禁：抠图没做完不给打标。
  it('gates tagging on the cutout mask (D2)', () => {
    const { rerender } = render(
      <ImagePipelineSteps
        calibration="none"
        hasMask={false}
        tagged={false}
        {...handlers()}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('pipeline-tag')).toBeDisabled();

    rerender(
      <ImagePipelineSteps
        calibration="none"
        hasMask
        tagged={false}
        {...handlers()}
      />,
    );
    expect(screen.getByTestId('pipeline-tag')).toBeEnabled();
  });

  // 钉子 3：只有「已校色」才锁校色按钮，其余状态都可点。
  it('disables the calibrate step only once calibration is done', () => {
    const { rerender } = render(
      <ImagePipelineSteps
        calibration="done"
        hasMask={false}
        tagged={false}
        {...handlers()}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('pipeline-calibrate')).toBeDisabled();

    for (const state of ['none', 'pending', 'skipped'] as const) {
      rerender(
        <ImagePipelineSteps
          calibration={state}
          hasMask={false}
          tagged={false}
          {...handlers()}
        />,
      );
      expect(screen.getByTestId('pipeline-calibrate')).toBeEnabled();
    }
  });

  // R36 钉子 4：灌真实 en messages 时按钮文案必须解析出来，不是原始 key。
  it('resolves button labels from the en catalog instead of leaking raw keys', () => {
    render(
      <ImagePipelineSteps
        calibration="none"
        hasMask={false}
        tagged={false}
        {...handlers()}
      />,
      { wrapper: Wrapper },
    );
    const calibrate = screen.getByTestId('pipeline-calibrate');
    const cutout = screen.getByTestId('pipeline-cutout');
    const tag = screen.getByTestId('pipeline-tag');
    expect(calibrate.textContent).toContain(en.pipeline.calibrate);
    expect(cutout.textContent).toContain(en.pipeline.cutout);
    expect(tag.textContent).toContain(en.pipeline.tag);
    for (const btn of [calibrate, cutout, tag]) {
      // 翻译真解析了：渲染里不许残留 key 路径
      expect(btn.textContent).not.toContain('state.');
      expect(btn.textContent).not.toContain('pipeline.');
    }
  });

  // Ruling 42：录入页还没有 item，三个动作无处可派——点了没反应比不给点更糟。
  it('shows step order and state without any buttons when not interactive', () => {
    render(
      <ImagePipelineSteps interactive={false} calibration="none" hasMask={false} tagged={false} />,
      { wrapper: Wrapper },
    );
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    const steps = screen.getAllByRole('listitem');
    expect(steps).toHaveLength(3);
    expect(within(steps[0]).getByTestId('pipeline-calibrate')).toHaveTextContent(/\S/);
    expect(within(steps[1]).getByTestId('pipeline-cutout')).toBeInTheDocument();
    expect(within(steps[2]).getByTestId('pipeline-tag')).toBeInTheDocument();
  });
});
