import type { Item } from '@/lib/types';

export type PipelineStage =
  | 'idle' // 没在跑，也没失败
  | 'calibrating' // processing_kind==='pipeline' 且 calibration_state==='none'
  | 'cutting' // pipeline（已校色/跳过）或单步抠图在跑，且无 mask
  | 'tagging' // status==='processing' 且 processing_kind==null
  | 'failed-image' // status==='error' 且 kind 属图片类（pipeline/background_removal/rotate）
  | 'failed-tag'; // status==='error' 且 kind==null 且未打标

/**
 * 条目当前处在管线的哪一段（AI 先录入，Task 4）。Ruling P2 补全其它图片类 kind：
 * background_removal 在跑 → cutting；rotate 在跑 → idle（旋转不属于三步）；
 * background_removal/rotate 出错 → failed-image。
 * pipeline 在跑且已校色且已有 mask → 视为 tagging（只剩打标段）。
 */
export function pipelineStage(
  item: Pick<Item, 'status' | 'processing_kind' | 'calibration_state' | 'mask_path' | 'tagging_status'>,
): PipelineStage {
  const kind = item.processing_kind ?? null;
  if (item.status === 'processing') {
    if (kind === 'pipeline') {
      if (item.calibration_state === 'none') return 'calibrating';
      return item.mask_path ? 'tagging' : 'cutting';
    }
    if (kind === 'background_removal') return 'cutting';
    if (kind === 'rotate') return 'idle';
    return 'tagging';
  }
  if (item.status === 'error') {
    if (kind === 'pipeline' || kind === 'background_removal' || kind === 'rotate') {
      return 'failed-image';
    }
    return item.tagging_status !== 'tagged' ? 'failed-tag' : 'idle';
  }
  return 'idle';
}

const RUNNING: ReadonlySet<PipelineStage> = new Set<PipelineStage>(['calibrating', 'cutting', 'tagging']);

/**
 * 录入模式下 AI 结果到达时怎么处理表单（AI 先录入，Task 6）。
 * - 未初始化：管线还在跑 → 'wait'；已停（idle/failed-*）→ 'init'
 * - 已初始化且刚打完标（idle + tagged）：表单没改过 → 'init'（自动刷新），改过 → 'offer-overwrite'
 * - 其他 → 'keep'：AI 结果永不静默覆盖用户改过的值
 * 「刚打完标」由调用方用 ref 记上一次的 stage / tagged_at 判断后经 justFinishedTagging 传入。
 */
export function entryFormSync(args: {
  initialized: boolean;
  dirty: boolean;
  stage: PipelineStage;
  taggingStatus: 'pending' | 'tagged';
  justFinishedTagging: boolean;
}): 'wait' | 'init' | 'offer-overwrite' | 'keep' {
  const { initialized, dirty, stage, taggingStatus, justFinishedTagging } = args;
  if (!initialized) return RUNNING.has(stage) ? 'wait' : 'init';
  if (justFinishedTagging && stage === 'idle' && taggingStatus === 'tagged') {
    return dirty ? 'offer-overwrite' : 'init';
  }
  return 'keep';
}
