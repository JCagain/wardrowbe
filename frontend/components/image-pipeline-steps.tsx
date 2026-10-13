'use client';

import { useTranslations } from 'next-intl';

export type CalibrationState = 'none' | 'pending' | 'done' | 'skipped';

/**
 * 三步状态条：校色 → 抠图 → 打标（spec §1.4 严格顺序；D2：抠图没做完不给打标）。
 *
 * `calibration` 是**会话态**（Ruling 38），由父组件的 React state 持有，不落库：
 * `ClothingItem` 上没有校色状态列——`calibration_original_path` 只是校色前副本
 * （Task 1 起每个主图都有，与「校过色」无关），而拿工作图与副本的字节/像素比对
 * 当「是否校过色」是假信号（`_save_all_sizes` 每次重编码，抠图后还变 PNG）。
 * 刷新页面后归 'none'；「重置回原图」本来就可重来，按钮一直可点，不影响正确性。
 * 将来若加落库列，只改父组件的初始化处。
 */
export function ImagePipelineSteps({
  calibration,
  hasMask,
  tagged,
  onCalibrate,
  onCutout,
  onTag,
  interactive = true,
}: {
  calibration: CalibrationState;
  hasMask: boolean;
  tagged: boolean;
  onCalibrate?: () => void;
  onCutout?: () => void;
  onTag?: () => void;
  /** false：只显示三步顺序与状态，不渲染动作按钮（Ruling 42：录入页还没有 item）。 */
  interactive?: boolean;
}) {
  const t = useTranslations('wardrobe.pipeline');
  // D2：严格顺序 校色 → 抠图 → 打标，抠图没做完不给打标。
  const tagEnabled = hasMask;

  const step = (testId: string, label: string, onClick: (() => void) | undefined, disabled: boolean) =>
    interactive ? (
      <button type="button" data-testid={testId} onClick={onClick} disabled={disabled}>
        {label}
      </button>
    ) : (
      <span data-testid={testId}>{label}</span>
    );

  return (
    <ol className="flex items-center gap-3">
      <li>
        {step('pipeline-calibrate', `${t('calibrate')} · ${t(`state.${calibration}`)}`,
              onCalibrate, calibration === 'done')}
      </li>
      <li>
        {step('pipeline-cutout', `${t('cutout')} · ${t(hasMask ? 'state.done' : 'state.none')}`,
              onCutout, hasMask)}
      </li>
      <li>
        {step('pipeline-tag', `${t('tag')} · ${t(tagged ? 'state.done' : 'state.none')}`,
              onTag, !tagEnabled)}
      </li>
    </ol>
  );
}
