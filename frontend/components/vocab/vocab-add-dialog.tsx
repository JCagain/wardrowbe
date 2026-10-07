'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useAddColorValue,
  useAddStyle,
  useAddType,
  useVocabulary,
  type VocabKind,
} from '@/lib/hooks/use-vocabulary';
import { BODY_PART_LABELS, BODY_PART_VALUES } from '@/lib/generated/garment-vocabulary';

const SLUG_PATTERN = /^[a-z0-9-]+$/;

export interface VocabAddDialogProps {
  kind: VocabKind;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** colors: the family to file under; types: the body part. Selectable when omitted. */
  family?: string;
}

export function VocabAddDialog({ kind, open, onOpenChange, family }: VocabAddDialogProps) {
  const t = useTranslations('wardrobe.vocabAdd');
  const { data: vocabulary } = useVocabulary();
  const addStyle = useAddStyle();
  const addType = useAddType();
  const addColor = useAddColorValue();

  const [label, setLabel] = useState('');
  const [slug, setSlug] = useState('');
  const [hex, setHex] = useState('#8fa9bf');
  const [familyValue, setFamilyValue] = useState('');
  const [partValue, setPartValue] = useState('');

  // Re-seed every time the dialog opens: the parent's `family` prop changes
  // between opens (body-part switch in the item form), and submit reads the
  // prop while the select shows state — a mount-only seed left the two
  // disagreeing (and the footer Cancel bypasses reset() entirely).
  useEffect(() => {
    if (open) {
      setFamilyValue(family ?? '');
      setPartValue(family ?? '');
    }
  }, [open, family]);

  const reset = () => {
    setLabel('');
    setSlug('');
    setHex('#8fa9bf');
  };

  const submit = async () => {
    const value = slug.trim().toLowerCase();
    if (!label.trim() || !SLUG_PATTERN.test(value)) {
      toast.error(t('invalid'));
      return;
    }
    try {
      if (kind === 'styles') {
        await addStyle.mutateAsync({ value, label: label.trim() });
      } else if (kind === 'types') {
        const body_part = family ?? partValue;
        if (!body_part) {
          toast.error(t('invalid'));
          return;
        }
        await addType.mutateAsync({ value, label: label.trim(), body_part });
      } else {
        const fam = family ?? familyValue;
        if (!fam || !/^#[0-9a-fA-F]{6}$/.test(hex)) {
          toast.error(t('invalid'));
          return;
        }
        await addColor.mutateAsync({ value, label: label.trim(), family: fam, hex });
      }
      reset();
      onOpenChange(false);
    } catch (error) {
      const status = (error as { status?: number })?.status;
      toast.error(status === 409 ? t('slugExists') : t('failed'));
    }
  };

  const families = vocabulary?.colors.families ?? [];

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t(`title.${kind}`)}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {kind === 'colors' && !family && (
            <div className="space-y-2">
              <Label htmlFor="vocab-family">{t('family')}</Label>
              <Select value={familyValue} onValueChange={setFamilyValue}>
                <SelectTrigger id="vocab-family">
                  <SelectValue placeholder={t('familyPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {families.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {kind === 'types' && !family && (
            <div className="space-y-2">
              <Label htmlFor="vocab-body-part">{t('bodyPart')}</Label>
              <Select value={partValue} onValueChange={setPartValue}>
                <SelectTrigger id="vocab-body-part">
                  <SelectValue placeholder={t('bodyPartPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {BODY_PART_VALUES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {BODY_PART_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="vocab-label">{t('label')}</Label>
            <Input id="vocab-label" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="vocab-slug">{t('slug')}</Label>
            <Input
              id="vocab-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder={t('slugPlaceholder')}
            />
          </div>
          {kind === 'colors' && (
            <div className="space-y-2">
              <Label htmlFor="vocab-hex">{t('hex')}</Label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  aria-label={t('hex')}
                  value={hex}
                  onChange={(e) => setHex(e.target.value)}
                  className="h-9 w-12 rounded border bg-transparent p-1"
                />
                <Input
                  id="vocab-hex"
                  value={hex}
                  onChange={(e) => setHex(e.target.value)}
                  placeholder="#8fa9bf"
                />
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={submit}>{t('submit')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
