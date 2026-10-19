import { describe, expect, it } from 'vitest';
import { entryFormSync, pipelineStage } from '@/lib/item-pipeline';

type In = Parameters<typeof pipelineStage>[0];
const base: In = {
  status: 'ready',
  processing_kind: null,
  calibration_state: 'none',
  mask_path: null,
  tagging_status: 'pending',
};
const s = (o: Partial<In>) => pipelineStage({ ...base, ...o });

describe('pipelineStage', () => {
  it('idle when ready and not processing', () => {
    expect(s({})).toBe('idle');
  });
  it('calibrating: pipeline job, not yet calibrated', () => {
    expect(s({ status: 'processing', processing_kind: 'pipeline' })).toBe('calibrating');
  });
  it('cutting: pipeline job, calibrated, no mask', () => {
    expect(
      s({ status: 'processing', processing_kind: 'pipeline', calibration_state: 'done' }),
    ).toBe('cutting');
    expect(
      s({ status: 'processing', processing_kind: 'pipeline', calibration_state: 'skipped' }),
    ).toBe('cutting');
  });
  // T4a：pipeline 在跑、已校色/跳过且已有 mask → 只剩打标段
  it('tagging: pipeline job, calibrated or skipped, mask present (T4a)', () => {
    for (const calibration_state of ['done', 'skipped'] as const) {
      expect(
        s({ status: 'processing', processing_kind: 'pipeline', calibration_state, mask_path: 'm.png' }),
      ).toBe('tagging');
    }
  });
  it('tagging: processing without a kind', () => {
    expect(s({ status: 'processing' })).toBe('tagging');
  });
  it('failed-image: error during pipeline', () => {
    expect(s({ status: 'error', processing_kind: 'pipeline' })).toBe('failed-image');
  });
  it('failed-tag: error, no image kind, not tagged', () => {
    expect(s({ status: 'error' })).toBe('failed-tag');
  });
  it('error on an already tagged item is not failed-tag', () => {
    expect(s({ status: 'error', tagging_status: 'tagged' })).toBe('idle');
  });
  // Ruling P2：其它图片类 kind
  it('maps background_removal and rotate kinds (Ruling P2)', () => {
    expect(s({ status: 'processing', processing_kind: 'background_removal' })).toBe('cutting');
    expect(s({ status: 'processing', processing_kind: 'rotate' })).toBe('idle');
    expect(s({ status: 'error', processing_kind: 'background_removal' })).toBe('failed-image');
    expect(s({ status: 'error', processing_kind: 'rotate' })).toBe('failed-image');
  });
});

describe('entryFormSync', () => {
  type A = Parameters<typeof entryFormSync>[0];
  const a: A = {
    initialized: false,
    dirty: false,
    stage: 'idle',
    taggingStatus: 'pending',
    justFinishedTagging: false,
  };
  const f = (o: Partial<A>) => entryFormSync({ ...a, ...o });

  it('waits while a running stage has not produced results yet', () => {
    for (const stage of ['calibrating', 'cutting', 'tagging'] as const) {
      expect(f({ stage })).toBe('wait');
    }
  });
  it('initializes once idle or failed when not yet initialized', () => {
    for (const stage of ['idle', 'failed-image', 'failed-tag'] as const) {
      expect(f({ stage })).toBe('init');
    }
  });
  it('re-initializes a clean form when tagging just finished', () => {
    expect(
      f({ initialized: true, stage: 'idle', taggingStatus: 'tagged', justFinishedTagging: true }),
    ).toBe('init');
  });
  it('offers to overwrite a dirty form when tagging just finished', () => {
    expect(
      f({
        initialized: true,
        dirty: true,
        stage: 'idle',
        taggingStatus: 'tagged',
        justFinishedTagging: true,
      }),
    ).toBe('offer-overwrite');
  });
  it('keeps the form otherwise', () => {
    expect(f({ initialized: true, stage: 'tagging' })).toBe('keep');
    expect(f({ initialized: true, dirty: true, stage: 'idle', taggingStatus: 'tagged' })).toBe('keep');
    expect(
      f({ initialized: true, stage: 'idle', taggingStatus: 'pending', justFinishedTagging: true }),
    ).toBe('keep');
  });
});
