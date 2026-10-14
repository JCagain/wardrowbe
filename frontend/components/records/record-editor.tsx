'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { ItemPicker } from '@/components/shared/item-picker';
import { RecordPhotoStrip, type StripPhoto } from '@/components/records/record-photo-strip';
import { getErrorMessage } from '@/lib/api';
import { usePreferences } from '@/lib/hooks/use-preferences';
import {
  fetchRecordWeather,
  useAddRecordPhoto,
  useCreateRecord,
  useDeleteRecord,
  useDeleteRecordPhoto,
  useRotateRecordPhoto,
  useUpdateRecord,
} from '@/lib/hooks/use-records';
import { RECORD_SEASONS, seasonForDate } from '@/lib/records/season';
import { RECORD_CONDITIONS, isEmptyWeather } from '@/lib/records/weather';
import {
  OCCASIONS,
  type Item,
  type OutfitRecord,
  type RecordInput,
  type RecordItem,
  type RecordWeather,
} from '@/lib/types';

const NONE = '__none__';
const EMPTY_WEATHER: RecordWeather = { temp_high: null, temp_low: null, condition: null };

interface Props {
  record?: OutfitRecord;
  today: string;
  onSaved: (r: OutfitRecord) => void;
  onDeleted?: () => void;
}

let photoCounter = 0;
function newPhotoId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  photoCounter += 1;
  return `local-${photoCounter}`;
}

function numOrNull(v: string): number | null {
  if (v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function RecordEditor({ record, today, onSaved, onDeleted }: Props) {
  const t = useTranslations('history.records');
  const tc = useTranslations('constants');
  const tCommon = useTranslations('common');
  const isEdit = !!record;
  const { data: prefs } = usePreferences();

  const createRecord = useCreateRecord();
  const updateRecord = useUpdateRecord();
  const deleteRecord = useDeleteRecord();
  const addPhoto = useAddRecordPhoto();
  const deletePhoto = useDeleteRecordPhoto();
  const rotatePhoto = useRotateRecordPhoto();

  const [date, setDate] = useState(record?.date ?? today);
  const [season, setSeason] = useState<string | null>(record?.season ?? seasonForDate(record?.date ?? today));
  const [city, setCity] = useState<string | null>(record ? record.city : null);
  const [weather, setWeather] = useState<RecordWeather>(record?.weather ?? EMPTY_WEATHER);
  const [occasion, setOccasion] = useState<string | null>(record?.occasion ?? null);
  const [notes, setNotes] = useState(record?.notes ?? '');
  const [items, setItems] = useState<RecordItem[]>(record?.items ?? []);
  const [localPhotos, setLocalPhotos] = useState<Array<{ key: string; file: File; src: string }>>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const cityInitialized = useRef(isEdit);
  const lastWeatherKey = useRef(isEdit ? `${record!.city ?? ''}|${record!.date}` : '');
  const photoUrls = useRef(new Map<string, string>());

  // 新建：默认城市一到就选上（spec §3.1 默认城市）
  useEffect(() => {
    if (cityInitialized.current || !prefs) return;
    cityInitialized.current = true;
    setCity(prefs.default_city ?? null);
  }, [prefs]);

  // 城市或日期变 → 预填天气；以「上次取过的 城市|日期」去重，
  // 编辑页挂载（含 StrictMode 重跑）因 key 相同而不覆盖已存天气
  useEffect(() => {
    const key = `${city ?? ''}|${date}`;
    if (key === lastWeatherKey.current) return;
    lastWeatherKey.current = key;
    if (!city) {
      setWeatherLoading(false);
      return;
    }
    setWeatherLoading(true);
    fetchRecordWeather(city, date)
      .then((w) => {
        if (lastWeatherKey.current === key && w) setWeather(w);
      })
      .catch(() => {})
      .finally(() => {
        if (lastWeatherKey.current === key) setWeatherLoading(false);
      });
  }, [city, date]);

  // 本地照片的 blob URL：移除时单张回收，卸载时回收剩余
  useEffect(() => {
    const urls = photoUrls.current;
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
      urls.clear();
    };
  }, []);

  const cityOptions = useMemo(() => {
    const names = (prefs?.cities ?? []).map((c) => c.name);
    if (city && !names.includes(city)) names.push(city);
    return names;
  }, [prefs?.cities, city]);

  const stripPhotos: StripPhoto[] = isEdit
    ? record!.photos.map((p) => ({ key: p.id, src: p.thumbnail_url ?? p.image_url }))
    : localPhotos.map((p) => ({ key: p.key, src: p.src }));

  const photoCount = isEdit ? record!.photos.length : localPhotos.length;
  const busy = createRecord.isPending || updateRecord.isPending;
  const canSave = photoCount > 0 && !!date && !busy;

  const handleDateChange = (value: string) => {
    setDate(value);
    if (value) setSeason(seasonForDate(value));
  };

  const handleAddPhotos = async (files: File[]) => {
    if (!isEdit) {
      const added = files.map((file) => {
        const key = `${file.name}-${newPhotoId()}`;
        const src = URL.createObjectURL(file);
        photoUrls.current.set(key, src);
        return { key, file, src };
      });
      setLocalPhotos((prev) => [...prev, ...added]);
      return;
    }
    for (const file of files) {
      try {
        await addPhoto.mutateAsync({ id: record!.id, file });
      } catch (e) {
        toast.error(getErrorMessage(e, t('saveFailed')));
      }
    }
  };

  const handleRemovePhoto = async (key: string) => {
    if (!isEdit) {
      const url = photoUrls.current.get(key);
      if (url) {
        URL.revokeObjectURL(url);
        photoUrls.current.delete(key);
      }
      setLocalPhotos((prev) => prev.filter((p) => p.key !== key));
      return;
    }
    try {
      await deletePhoto.mutateAsync({ id: record!.id, photoId: key });
    } catch (e) {
      toast.error(getErrorMessage(e, t('saveFailed')));
    }
  };

  const handleRotate = async (key: string, direction: 'cw' | 'ccw') => {
    try {
      await rotatePhoto.mutateAsync({ id: record!.id, photoId: key, direction });
    } catch (e) {
      toast.error(getErrorMessage(e, t('saveFailed')));
    }
  };

  const toggleItem = (item: Item) => {
    setItems((prev) =>
      prev.some((i) => i.id === item.id)
        ? prev.filter((i) => i.id !== item.id)
        : [
            ...prev,
            {
              id: item.id,
              type: item.type,
              name: item.name ?? null,
              primary_colors: item.primary_colors,
              thumbnail_url: item.thumbnail_url ?? item.image_url ?? null,
            },
          ]
    );
  };

  const buildInput = (): RecordInput => ({
    date,
    season,
    city,
    weather: isEmptyWeather(weather) ? null : weather,
    occasion,
    notes: notes.trim() ? notes : null,
    item_ids: items.map((i) => i.id),
  });

  const handleSave = async () => {
    if (!canSave) return;
    try {
      const saved = isEdit
        ? await updateRecord.mutateAsync({ id: record!.id, input: buildInput() })
        : await createRecord.mutateAsync({ input: buildInput(), photos: localPhotos.map((p) => p.file) });
      toast.success(t('saved'));
      onSaved(saved);
    } catch (e) {
      toast.error(getErrorMessage(e, t('saveFailed')));
    }
  };

  const handleDelete = async () => {
    try {
      await deleteRecord.mutateAsync(record!.id);
      toast.success(t('deleted'));
      onDeleted?.();
    } catch (e) {
      toast.error(getErrorMessage(e, t('saveFailed')));
    }
  };

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <Label>{t('photos')}</Label>
        <RecordPhotoStrip
          photos={stripPhotos}
          onAdd={handleAddPhotos}
          onRemove={handleRemovePhoto}
          onRotate={isEdit ? handleRotate : undefined}
          canRemove={isEdit ? photoCount > 1 : true}
        />
        {photoCount === 0 && <p className="text-sm text-muted-foreground">{t('photoRequired')}</p>}
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="record-date">{t('date')}</Label>
          <Input
            id="record-date"
            data-testid="record-date"
            type="date"
            value={date}
            onChange={(e) => handleDateChange(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>{t('season')}</Label>
          <Select value={season ?? NONE} onValueChange={(v) => setSeason(v === NONE ? null : v)}>
            <SelectTrigger data-testid="record-season" data-value={season ?? ''}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RECORD_SEASONS.map((s) => (
                <SelectItem key={s} value={s}>
                  {t(`seasons.${s}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>{t('city')}</Label>
          <Select value={city ?? NONE} onValueChange={(v) => setCity(v === NONE ? null : v)}>
            <SelectTrigger data-testid="record-city" data-value={city ?? ''}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t('noCity')}</SelectItem>
              {cityOptions.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>{t('weather')}</Label>
          <div className="flex items-center gap-2">
            {weatherLoading && <span className="text-xs text-muted-foreground">{t('weatherLoading')}</span>}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid="record-clear-weather"
              onClick={() => setWeather(EMPTY_WEATHER)}
            >
              {t('clearWeather')}
            </Button>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Input
            data-testid="record-temp-high"
            type="number"
            aria-label={t('tempHigh')}
            placeholder={t('tempHigh')}
            value={weather.temp_high ?? ''}
            onChange={(e) => setWeather((w) => ({ ...w, temp_high: numOrNull(e.target.value) }))}
          />
          <Input
            data-testid="record-temp-low"
            type="number"
            aria-label={t('tempLow')}
            placeholder={t('tempLow')}
            value={weather.temp_low ?? ''}
            onChange={(e) => setWeather((w) => ({ ...w, temp_low: numOrNull(e.target.value) }))}
          />
          <Select
            value={weather.condition ?? NONE}
            onValueChange={(v) => setWeather((w) => ({ ...w, condition: v === NONE ? null : v }))}
          >
            <SelectTrigger data-testid="record-condition" data-value={weather.condition ?? ''}>
              <SelectValue placeholder={t('condition')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t('noCondition')}</SelectItem>
              {RECORD_CONDITIONS.map((c) => (
                <SelectItem key={c} value={c}>
                  {t(`conditions.${c}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>{t('items')}</Label>
          <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
            {t('pickItems')}
          </Button>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('noItems')}</p>
        ) : (
          <div className="flex flex-wrap gap-2" data-testid="record-items">
            {items.map((i) => (
              <div key={i.id} className="h-16 w-16 overflow-hidden rounded border bg-muted">
                {i.thumbnail_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={i.thumbnail_url} alt={i.name ?? i.type} className="h-full w-full object-cover" />
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>{t('occasion')}</Label>
          <Select value={occasion ?? NONE} onValueChange={(v) => setOccasion(v === NONE ? null : v)}>
            <SelectTrigger data-testid="record-occasion" data-value={occasion ?? ''}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t('noOccasion')}</SelectItem>
              {OCCASIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {tc(`occasions.${o.value}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="record-notes">{t('notes')}</Label>
          <Textarea id="record-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </section>

      <div className="flex justify-between">
        {isEdit ? (
          <Button type="button" variant="destructive" data-testid="record-delete" onClick={() => setConfirmDelete(true)}>
            {t('delete')}
          </Button>
        ) : (
          <span />
        )}
        <Button data-testid="record-save" disabled={!canSave} onClick={handleSave}>
          {t('save')}
        </Button>
      </div>

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t('pickItems')}</DialogTitle>
          </DialogHeader>
          <ItemPicker
            selectedIds={new Set(items.map((i) => i.id))}
            onToggle={toggleItem}
            hideNeedsWash={false}
          />
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteConfirmBody')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction data-testid="record-delete-confirm" onClick={handleDelete}>{t('delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
