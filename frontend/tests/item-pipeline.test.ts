import { describe, expect, it } from 'vitest';
import { pipelineStage } from '@/lib/item-pipeline';

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
