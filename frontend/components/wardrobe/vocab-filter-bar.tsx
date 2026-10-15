'use client';

import { useTranslations } from 'next-intl';
import {
  useBodyParts,
  useClothingColors,
  useClothingTypes,
  useColorFamilies,
  useSeasons,
  useStyles,
} from '@/lib/hooks/use-translated-constants';
import {
  colorOptionsFor,
  setBodyPart,
  setColorFamily,
  typeOptionsFor,
  type VocabFilterState,
} from '@/lib/wardrobe-filters';
import type { ColorScope, VocabEntry } from '@/lib/types';

interface Props {
  value: VocabFilterState;
  onChange: (next: VocabFilterState) => void;
}

// 原生 <select>：六个维度挤在一行，Radix Select 的弹层在手机上更难点；也便于测试。
function FilterSelect({
  label,
  allLabel,
  value,
  options,
  onChange,
  disabledLabel,
}: {
  label: string;
  allLabel: string;
  value: string;
  options: VocabEntry[];
  onChange: (v: string) => void;
  disabledLabel: (label: string) => string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 rounded-md border bg-background px-2 text-xs"
    >
      <option value="">{allLabel}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.disabled ? disabledLabel(o.label) : o.label}
        </option>
      ))}
    </select>
  );
}

export function VocabFilterBar({ value, onChange }: Props) {
  const t = useTranslations('wardrobe.vocabFilters');
  const bodyParts = useBodyParts();
  const types = useClothingTypes();
  const families = useColorFamilies();
  const colors = useClothingColors();
  const styles = useStyles();
  const seasons = useSeasons();
  const disabledLabel = (label: string) => t('disabled', { label });

  return (
    <>
      <FilterSelect
        label={t('bodyPart')}
        allLabel={t('allBodyParts')}
        value={value.bodyPart}
        options={bodyParts}
        onChange={(v) => onChange(setBodyPart(value, v, types))}
        disabledLabel={disabledLabel}
      />
      <FilterSelect
        label={t('type')}
        allLabel={t('allTypes')}
        value={value.type}
        options={typeOptionsFor(value.bodyPart, types)}
        onChange={(v) => onChange({ ...value, type: v })}
        disabledLabel={disabledLabel}
      />
      <FilterSelect
        label={t('colorFamily')}
        allLabel={t('allColorFamilies')}
        value={value.colorFamily}
        options={families}
        onChange={(v) => onChange(setColorFamily(value, v, colors))}
        disabledLabel={disabledLabel}
      />
      <FilterSelect
        label={t('color')}
        allLabel={t('allColors')}
        value={value.color}
        options={colorOptionsFor(value.colorFamily, colors)}
        onChange={(v) => onChange({ ...value, color: v })}
        disabledLabel={disabledLabel}
      />
      <select
        aria-label={t('colorScope')}
        value={value.colorScope}
        onChange={(e) => onChange({ ...value, colorScope: e.target.value as ColorScope })}
        className="h-8 rounded-md border bg-background px-2 text-xs"
      >
        <option value="primary">{t('scopePrimary')}</option>
        <option value="secondary">{t('scopeSecondary')}</option>
        <option value="any">{t('scopeAny')}</option>
      </select>
      <FilterSelect
        label={t('style')}
        allLabel={t('allStyles')}
        value={value.style}
        options={styles}
        onChange={(v) => onChange({ ...value, style: v })}
        disabledLabel={disabledLabel}
      />
      <FilterSelect
        label={t('season')}
        allLabel={t('allSeasons')}
        value={value.season}
        options={seasons}
        onChange={(v) => onChange({ ...value, season: v })}
        disabledLabel={disabledLabel}
      />
    </>
  );
}
