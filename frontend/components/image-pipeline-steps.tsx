'use client';

import { Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';

export type CalibrationState = 'none' | 'pending' | 'done' | 'skipped';

/**
 * 三步状态条：校色 → 抠图 → 打标（spec §1.4 严格顺序；D2：抠图没做完不给打标）。
 *
 * `calibration` 由调用方传入：落库值取 `item.calibration_state`（Task 1），'pending' 仅表示
 * 框编辑器打开中（调用方的会话态）。
 */
export function ImagePipelineSteps({
  calibration,
  hasMask,
  tagged,
  onCalibrate,
  onCutout,
  onTag,
  interactive = true,
  running = null,
  failed = null,
}: {
  calibration: CalibrationState;
  hasMask: boolean;
  tagged: boolean;
  onCalibrate?: () => void;
  onCutout?: () => void;
  onTag?: () => void;
  /** false：只显示三步顺序与状态，不渲染动作按钮（Ruling 42：录入页还没有 item）。 */
  interactive?: boolean;
  /** 正在跑的那一步：转圈并禁用。 */
  running?: 'calibrate' | 'cutout' | 'tag' | null;
  /** 失败的阶段：image → 抠图步（图片段失败），tag → 打标步；红色但仍可点（重试）。 */
  failed?: 'image' | 'tag' | null;
}) {
  const t = useTranslations('wardrobe.pipeline');
  // D2：严格顺序 校色 → 抠图 → 打标，抠图没做完不给打标。
  const tagEnabled = hasMask;

  const step = (
    key: 'calibrate' | 'cutout' | 'tag',
    label: string,
    onClick: (() => void) | undefined,
    done: boolean,
    disabled: boolean,
  ) => {
    const testId = `pipeline-${key}`;
    if (!interactive) return <span data-testid={testId}>{label}</span>;
    const isRunning = running === key;
    const isFailed = (failed === 'image' && key === 'cutout') || (failed === 'tag' && key === 'tag');
    return (
      <Button
        type="button"
        size="sm"
        data-testid={testId}
        variant={isFailed ? 'destructive' : done ? 'outline' : 'default'}
        onClick={onClick}
        disabled={disabled || isRunning}
        title={isFailed ? t('failed') : isRunning ? t('running') : undefined}
      >
        {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-label={t('running')} />}
        {label}
      </Button>
    );
  };

  return (
    <ol className="flex items-center gap-3">
      <li>
        {step('calibrate', `${t('calibrate')} · ${t(`state.${calibration}`)}`,
              onCalibrate, calibration === 'done', calibration === 'done')}
      </li>
      <li>
        {step('cutout', `${t('cutout')} · ${t(hasMask ? 'state.done' : 'state.none')}`,
              onCutout, hasMask, hasMask)}
      </li>
      <li>
        {step('tag', `${t('tag')} · ${t(tagged ? 'state.done' : 'state.none')}`,
              onTag, tagged, !tagEnabled)}
      </li>
    </ol>
  );
}
