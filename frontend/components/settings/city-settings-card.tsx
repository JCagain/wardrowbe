'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { MapPin, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ApiError } from '@/lib/api';
import {
  useAddCity,
  usePreferences,
  useRemoveCity,
  useUpdatePreferences,
} from '@/lib/hooks/use-preferences';

const NO_DEFAULT = '__none__';

export function CitySettingsCard() {
  const t = useTranslations('settings.cities');
  const { data: prefs } = usePreferences();
  const update = useUpdatePreferences();
  const addCity = useAddCity();
  const removeCity = useRemoveCity();
  const [name, setName] = useState('');

  const cities = prefs?.cities ?? [];

  const handleAdd = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      await addCity.mutateAsync(trimmed);
      setName('');
      toast.success(t('added'));
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 0;
      toast.error(status === 409 ? t('duplicate') : status === 422 ? t('notFound') : t('unavailable'));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="h-5 w-5" />
          {t('title')}
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="flex flex-wrap gap-2">
          {cities.map((c) => (
            <li
              key={c.name}
              data-testid="city-row"
              className="flex items-center gap-1 rounded-full border px-3 py-1 text-sm"
            >
              {c.name}
              <button
                type="button"
                data-testid="city-remove"
                aria-label={t('remove', { name: c.name })}
                className="text-muted-foreground hover:text-foreground"
                onClick={() =>
                  removeCity.mutate(c.name, { onSuccess: () => toast.success(t('removed')) })
                }
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>

        <div className="flex gap-2">
          <Input
            data-testid="city-add-input"
            value={name}
            placeholder={t('addPlaceholder')}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd();
            }}
          />
          <Button data-testid="city-add-button" onClick={handleAdd} disabled={addCity.isPending}>
            {t('add')}
          </Button>
        </div>

        <div className="space-y-2">
          <Label>{t('default')}</Label>
          <Select
            value={prefs?.default_city ?? NO_DEFAULT}
            onValueChange={(v) => update.mutate({ default_city: v === NO_DEFAULT ? null : v })}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_DEFAULT}>{t('noDefault')}</SelectItem>
              {cities.map((c) => (
                <SelectItem key={c.name} value={c.name}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
