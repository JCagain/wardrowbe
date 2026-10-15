'use client';

import type { Dispatch, SetStateAction } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { type Item } from '@/lib/types';
import { partTypeChangeHandlers, type EditForm } from '@/lib/item-edit-form';
import { useVocabManagement } from '@/lib/hooks/use-vocabulary';
import {
  useBodyParts,
  useClothingColors,
  useClothingTypes,
  useSeasons,
  useStyles,
} from '@/lib/hooks/use-translated-constants';
import { StyleMultiSelect } from '@/components/vocab/style-multi-select';
import { PartTypeSelect } from '@/components/vocab/part-type-select';
import { ColorMultiSelect } from '@/components/vocab/color-multi-select';
import { ColorEyedropper } from '@/components/color-eyedropper';
import { useTranslations } from 'next-intl';

export interface ItemEditFormProps {
  item: Item;
  form: EditForm;
  setForm: Dispatch<SetStateAction<EditForm>>;
  bodyParts: ReturnType<typeof useBodyParts>;
  typeEntries: ReturnType<typeof useClothingTypes>;
  colorOptions: ReturnType<typeof useClothingColors>;
  styleOptions: ReturnType<typeof useStyles>;
  seasons: ReturnType<typeof useSeasons>;
  vocab: ReturnType<typeof useVocabManagement>;
  subtypeLabel: (value: string) => string;
  subtypeSuggestions: readonly string[];
  unrecognizedType: string | null | undefined;
  imageUrl: string;
  isSaving: boolean;
  onSave: () => void;
  onCancel: () => void;
}

export function ItemEditForm({
  item,
  form,
  setForm,
  bodyParts,
  typeEntries,
  colorOptions,
  styleOptions,
  seasons,
  vocab,
  subtypeLabel,
  subtypeSuggestions,
  unrecognizedType,
  imageUrl,
  isSaving,
  onSave,
  onCancel,
}: ItemEditFormProps) {
  const t = useTranslations('wardrobe.itemDetail');
  const tc = useTranslations('common');

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label>{t('name')}</Label>
        <Input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder={t('placeholders.itemName')}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('type')}</Label>
        {unrecognizedType && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            {t('unrecognizedType', { value: unrecognizedType })}
          </p>
        )}
        <PartTypeSelect
          parts={bodyParts}
          entries={typeEntries}
          bodyPart={form.body_part}
          type={form.type}
          {...partTypeChangeHandlers(setForm)}
          entryHandlers={vocab.handlersFor('types')}
          onAddEntry={() => vocab.openAdd('types')}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="item-subtype">{t('subtype')}</Label>
        <Input
          id="item-subtype"
          list="item-subtype-suggestions"
          maxLength={50}
          value={form.subtype}
          onChange={(e) => setForm({ ...form, subtype: e.target.value })}
          placeholder={t('placeholders.subtype')}
        />
        <datalist id="item-subtype-suggestions">
          {subtypeSuggestions.map((st) => (
            <option key={st} value={st}>{subtypeLabel(st)}</option>
          ))}
        </datalist>
      </div>
      <div className="space-y-2">
        <Label>{t('brand')}</Label>
        <Input
          value={form.brand}
          onChange={(e) => setForm({ ...form, brand: e.target.value })}
          placeholder={t('placeholders.brandName')}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>{t('primaryColors')}</Label>
          <ColorEyedropper
            imageUrl={imageUrl}
            onColorSelect={(color) =>
              setForm({
                ...form,
                primary_colors: form.primary_colors.includes(color)
                  ? form.primary_colors
                  : [...form.primary_colors, color],
              })
            }
          />
        </div>
        <ColorMultiSelect
          values={form.primary_colors}
          options={colorOptions}
          onChange={(next) => setForm({ ...form, primary_colors: next })}
          entryHandlers={vocab.handlersFor('colors')}
          onAddEntry={() => vocab.openAdd('colors')}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('secondaryColors')}</Label>
        <ColorMultiSelect
          values={form.secondary_colors}
          options={colorOptions}
          onChange={(next) => setForm({ ...form, secondary_colors: next })}
          entryHandlers={vocab.handlersFor('colors')}
          onAddEntry={() => vocab.openAdd('colors')}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('style')}</Label>
        <StyleMultiSelect
          values={form.style}
          options={styleOptions}
          onChange={(next) => setForm({ ...form, style: next })}
          entryHandlers={vocab.handlersFor('styles')}
          onAddEntry={() => vocab.openAdd('styles')}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('season')}</Label>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('season')}>
          {seasons.map((s) => {
            const on = form.season.includes(s.value);
            return (
              <Button
                key={s.value}
                type="button"
                size="sm"
                variant={on ? 'default' : 'outline'}
                aria-pressed={on}
                className="h-7 text-xs"
                onClick={() =>
                  setForm((prev) => ({
                    ...prev,
                    season: on ? prev.season.filter((v) => v !== s.value) : [...prev.season, s.value],
                  }))
                }
              >
                {s.label}
              </Button>
            );
          })}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="item-temp-low">{t('tempLow')}</Label>
          <Input
            id="item-temp-low"
            type="number"
            value={form.temp_low ?? ''}
            onChange={(e) =>
              setForm({
                ...form,
                temp_low: e.target.value === '' ? undefined : Number(e.target.value),
              })
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="item-temp-high">{t('tempHigh')}</Label>
          <Input
            id="item-temp-high"
            type="number"
            value={form.temp_high ?? ''}
            onChange={(e) =>
              setForm({
                ...form,
                temp_high: e.target.value === '' ? undefined : Number(e.target.value),
              })
            }
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="item-purchase-date">{t('purchaseDate')}</Label>
          <Input
            id="item-purchase-date"
            value={form.purchase_date}
            onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
            placeholder={t('purchaseDatePlaceholder')}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="item-purchase-price">{t('purchasePrice')}</Label>
          <Input
            id="item-purchase-price"
            type="number"
            min={0}
            step="0.01"
            value={form.purchase_price ?? ''}
            onChange={(e) =>
              setForm({
                ...form,
                purchase_price: e.target.value === '' ? undefined : Number(e.target.value),
              })
            }
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label>{t('status')}</Label>
        <div className="flex gap-2">
          {([['active', t('statusActive')], ['idle', t('statusIdle')], ['retired', t('statusRetired')]] as const).map(
            ([value, label]) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={form.lifecycle === value ? 'default' : 'outline'}
                aria-pressed={form.lifecycle === value}
                onClick={() => setForm({ ...form, lifecycle: value })}
              >
                {label}
              </Button>
            ),
          )}
        </div>
      </div>
      {form.lifecycle === 'retired' && (
        <div className="space-y-2">
          <Label htmlFor="item-archive-reason">{t('archiveReason')}</Label>
          <Input
            id="item-archive-reason"
            value={form.archive_reason}
            onChange={(e) => setForm({ ...form, archive_reason: e.target.value })}
          />
        </div>
      )}
      <div className="space-y-2">
        <Label>{t('notes')}</Label>
        <Textarea
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          placeholder={t('placeholders.additionalNotes')}
          rows={3}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('washInterval')} ({t('view.wears')})</Label>
        <Input
          type="number"
          min={1}
          max={100}
          value={form.wash_interval ?? ''}
          onChange={(e) => setForm({ ...form, wash_interval: e.target.value ? parseInt(e.target.value) : undefined })}
          placeholder={t('placeholders.washIntervalDefault', { count: item.effective_wash_interval })}
        />
        <p className="text-xs text-muted-foreground">
          {t('view.washIntervalHint')}
        </p>
      </div>
      <div className="flex gap-2 pt-2">
        <Button
          variant="outline"
          className="flex-1"
          onClick={() => onCancel()}
        >
          {tc('cancel')}
        </Button>
        <Button
          className="flex-1"
          onClick={onSave}
          disabled={isSaving}
        >
          {isSaving ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : null}
          {tc('save')}
        </Button>
      </div>
    </div>
  );
}
