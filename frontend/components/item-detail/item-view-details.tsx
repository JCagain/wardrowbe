'use client';

import {
  Calendar,
  Tag,
  Palette,
  Shirt,
  Sparkles,
  Droplets,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useItemWearStats } from '@/lib/hooks/use-items';
import { type Item } from '@/lib/types';
import {
  useClothingColors,
  useClothingTypes,
  useSeasons,
  useStyles,
} from '@/lib/hooks/use-translated-constants';
import { formatPurchaseDate } from '@/lib/purchase-date';
import { lifecycleBadgeProps, lifecycleLabelKey } from '@/lib/item-edit-form';
import { useTranslations } from 'next-intl';
import { WearCountEditor } from './wear-count-editor';
import { ItemRecordsSection } from './item-records-section';
import { ItemCompanionsSection } from './item-companions-section';

export interface ItemViewDetailsProps {
  item: Item;
  typeInfo: ReturnType<typeof useClothingTypes>[number] | undefined;
  colorOptions: ReturnType<typeof useClothingColors>;
  primaryColorInfo: (ReturnType<typeof useClothingColors>[number] | undefined)[];
  secondaryColorInfo: (ReturnType<typeof useClothingColors>[number] | undefined)[];
  unrecognizedType: string | null | undefined;
  styleOptions: ReturnType<typeof useStyles>;
  seasons: ReturnType<typeof useSeasons>;
  subtypeLabel: (value: string) => string;
  materialLabel: (value: string) => string;
  formalityLabel: (value: string) => string;
}

export function ItemViewDetails({
  item,
  typeInfo,
  colorOptions,
  primaryColorInfo,
  secondaryColorInfo,
  unrecognizedType,
  styleOptions,
  seasons,
  subtypeLabel,
  materialLabel,
  formalityLabel,
}: ItemViewDetailsProps) {
  const t = useTranslations('wardrobe.itemDetail');
  const { data: wearStats } = useItemWearStats(item.id);
  const colorLabel = (value: string) => colorOptions.find((c) => c.value === value);

  // AI-generated tags
  const tags = item.tags || {};
  const aiColors = [
    ...(tags.primary_colors ?? []),
    ...(tags.secondary_colors ?? []),
    ...(tags.primary_colors || tags.secondary_colors ? [] : tags.colors ?? []),
  ];
  const hasAiTags = !!(aiColors.length || tags.pattern || tags.material ||
                   tags.style?.length || tags.season?.length || tags.formality || tags.fit ||
                   tags.occasion?.length || tags.condition || tags.features?.length);

  return (
    <div className="space-y-4">
      {/* Basic info */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <Shirt className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium">{typeInfo ? typeInfo.label : item.type}</span>
          {item.subtype && (
            <span className="text-muted-foreground">• {subtypeLabel(item.subtype)}</span>
          )}
        </div>
        {unrecognizedType && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            {t('unrecognizedType', { value: unrecognizedType })}
          </p>
        )}
        {item.brand && (
          <div className="flex items-center gap-2 text-sm">
            <Tag className="h-4 w-4 text-muted-foreground" />
            <span>{item.brand}</span>
          </div>
        )}
        {(primaryColorInfo.length > 0 || secondaryColorInfo.length > 0) && (
          <div className="flex items-start gap-2 text-sm">
            <Palette className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div className="space-y-1">
              {primaryColorInfo.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground">{t('primaryColors')}</span>
                  {primaryColorInfo.map((c) =>
                    c ? (
                      <span key={c.value} className="flex items-center gap-1">
                        <span
                          className="w-4 h-4 rounded-full border"
                          style={{ backgroundColor: c.hex }}
                        />
                        <span>{c.label}</span>
                      </span>
                    ) : null,
                  )}
                </div>
              )}
              {secondaryColorInfo.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground">{t('secondaryColors')}</span>
                  {secondaryColorInfo.map((c) =>
                    c ? (
                      <span key={c.value} className="flex items-center gap-1">
                        <span
                          className="w-4 h-4 rounded-full border"
                          style={{ backgroundColor: c.hex }}
                        />
                        <span>{c.label}</span>
                      </span>
                    ) : null,
                  )}
                </div>
              )}
            </div>
          </div>
        )}
        {(item.tags.style?.length ?? 0) > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <Tag className="h-4 w-4 text-muted-foreground" />
            <div className="flex flex-wrap gap-1.5">
              {item.tags.style.map((s) => (
                <Badge key={s} variant="secondary" className="text-xs">
                  {styleOptions.find((o) => o.value === s)?.label ?? s}
                </Badge>
              ))}
            </div>
          </div>
        )}
        {(item.season?.length ?? 0) > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="text-muted-foreground">{t('season')}</span>
            {item.season!.map((s) => (
              <Badge key={s} variant="secondary" className="text-xs">
                {seasons.find((e) => e.value === s)?.label ?? s}
              </Badge>
            ))}
          </div>
        )}
        {(item.temp_low != null || item.temp_high != null) && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t('tempRange')}</span>
            <span>
              {item.temp_low ?? '—'}~{item.temp_high ?? '—'}℃
            </span>
          </div>
        )}
        {(item.purchase_date || item.purchase_price != null) && (
          <div className="flex items-center gap-2 text-sm">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="flex flex-wrap gap-x-3">
              {item.purchase_date && (
                <span>
                  {t('purchaseDate')}: {formatPurchaseDate(item.purchase_date, item.purchase_date_precision)}
                </span>
              )}
              {item.purchase_price != null && (
                <span>
                  {t('purchasePrice')}: {item.purchase_price}
                </span>
              )}
            </span>
          </div>
        )}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">{t('status')}</span>
          <Badge {...lifecycleBadgeProps(item)}>
            {t(lifecycleLabelKey(item))}
          </Badge>
          {item.is_archived && item.archive_reason && (
            <span className="text-muted-foreground truncate">{item.archive_reason}</span>
          )}
        </div>
        {item.wear_count > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span>
              {t('view.wornCount', { count: item.wear_count })}
              {item.last_worn_at && (
                <span className="text-muted-foreground">
                  {' '}{t('view.lastWornDate', { date: new Date(item.last_worn_at).toLocaleDateString() })}
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Wash Status */}
      <div className="space-y-2 pt-2 border-t">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Droplets className={`h-4 w-4 ${item.needs_wash ? 'text-amber-500' : 'text-muted-foreground'}`} />
            {t('view.washStatus')}
          </div>
          {/* 摘不删（spec §7）：「标记已洗」按钮已下线，后端端点已摘挂。 */}
        </div>
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{t('view.wearsSinceWash', { current: item.wears_since_wash, max: item.effective_wash_interval })}</span>
            {item.needs_wash && (
              <span className="text-amber-500 font-medium">{t('view.needsWashing')}</span>
            )}
          </div>
          <Progress
            value={Math.min((item.wears_since_wash / item.effective_wash_interval) * 100, 100)}
            className={`h-2 ${item.needs_wash ? '[&>div]:bg-amber-500' : ''}`}
          />
          {item.last_washed_at && (
            <p className="text-xs text-muted-foreground">
              {t('view.lastWashed', { date: new Date(item.last_washed_at).toLocaleDateString() })}
            </p>
          )}
        </div>

        {/* 摘不删（spec §7）：洗护历史折叠区已下线，端点已摘挂。 */}
      </div>

      <div className="pt-2 border-t">
        <WearCountEditor item={item} />
      </div>

      {/* Wear History */}
      {item.wear_count > 0 && wearStats && (
        <div className="space-y-2 pt-2 border-t">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            {t('view.wearHistory')}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-muted/50 rounded-md p-2">
              <p className="text-muted-foreground">{t('view.totalWears')}</p>
              <p className="font-medium text-sm">{wearStats.total_wears}</p>
            </div>
            <div className="bg-muted/50 rounded-md p-2">
              <p className="text-muted-foreground">{t('view.lastWorn')}</p>
              <p className="font-medium text-sm">
                {wearStats.days_since_last_worn === null
                  ? t('view.never')
                  : wearStats.days_since_last_worn === 0
                  ? t('view.today')
                  : t('view.daysAgo', { count: wearStats.days_since_last_worn })}
              </p>
            </div>
            <div className="bg-muted/50 rounded-md p-2">
              <p className="text-muted-foreground">{t('view.avgPerMonth')}</p>
              <p className="font-medium text-sm">{wearStats.average_wears_per_month}</p>
            </div>
            {wearStats.most_common_occasion && (
              <div className="bg-muted/50 rounded-md p-2">
                <p className="text-muted-foreground">{t('view.usualOccasion')}</p>
                <p className="font-medium text-sm capitalize">{wearStats.most_common_occasion}</p>
              </div>
            )}
          </div>

          {/* Mini bar chart - wear by month */}
          {Object.keys(wearStats.wear_by_month).length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">{t('view.last6Months')}</p>
              <div className="flex items-end gap-1 h-12">
                {Object.entries(wearStats.wear_by_month).map(([month, count]) => {
                  const maxCount = Math.max(...Object.values(wearStats.wear_by_month), 1);
                  const height = (count / maxCount) * 100;
                  return (
                    <div key={month} className="flex-1 flex flex-col items-center gap-0.5" title={t('view.monthWears', { month, count })}>
                      <div
                        className="w-full bg-primary/70 rounded-t-sm min-h-[2px]"
                        style={{ height: `${Math.max(height, 4)}%` }}
                      />
                      <span className="text-[9px] text-muted-foreground">{month.split('-')[1]}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      <ItemRecordsSection itemId={item.id} />
      <ItemCompanionsSection itemId={item.id} />

      {/* AI Analysis */}
      {(hasAiTags || item.ai_description) && item.status === 'ready' && (
        <div className="space-y-2 pt-2 border-t">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="h-4 w-4 text-primary" />
            {t('view.aiAnalysis')}
            {item.ai_confidence !== undefined && item.ai_confidence > 0 && (
              <Badge variant="secondary" className="text-xs">
                {t('view.complete', { percent: Math.round(item.ai_confidence * 100) })}
              </Badge>
            )}
            {item.tags?.logprobs_confidence != null && (
              <Badge variant="outline" className="text-xs">
                {t('view.confident', { percent: Math.round(item.tags.logprobs_confidence * 100) })}
              </Badge>
            )}
          </div>
          {item.ai_description && (
            <p className="text-sm text-muted-foreground italic">
              &ldquo;{item.ai_description}&rdquo;
            </p>
          )}
          {hasAiTags && <div className="flex flex-wrap gap-1.5">
            {aiColors.map((color) => (
              <Badge key={color} variant="outline" className="text-xs">
                {colorLabel(color)?.label ?? color}
              </Badge>
            ))}
            {tags.pattern && (
              <Badge variant="outline" className="text-xs">
                {tags.pattern}
              </Badge>
            )}
            {tags.material && (
              <Badge variant="outline" className="text-xs">
                {materialLabel(tags.material)}
              </Badge>
            )}
            {tags.style?.map((s) => (
              <Badge key={s} variant="outline" className="text-xs">
                {s}
              </Badge>
            ))}
            {tags.season?.map((s) => (
              <Badge key={s} variant="outline" className="text-xs">
                {s}
              </Badge>
            ))}
            {tags.formality && (
              <Badge variant="outline" className="text-xs">
                {formalityLabel(tags.formality)}
              </Badge>
            )}
            {tags.fit && (
              <Badge variant="outline" className="text-xs">
                {tags.fit ? t('view.fitBadge', { fit: tags.fit }) : null}
              </Badge>
            )}
            {tags.occasion?.map((o: string) => (
              <Badge key={o} variant="outline" className="text-xs">
                {o}
              </Badge>
            ))}
            {tags.condition && (
              <Badge variant="outline" className="text-xs">
                {tags.condition}
              </Badge>
            )}
            {tags.features?.map((f: string) => (
              <Badge key={f} variant="outline" className="text-xs">
                {f}
              </Badge>
            ))}
          </div>}
        </div>
      )}

      {/* Notes */}
      {item.notes && (
        <div className="space-y-1 pt-2 border-t">
          <p className="text-sm font-medium">{t('notes')}</p>
          <p className="text-sm text-muted-foreground">{item.notes}</p>
        </div>
      )}

      {/* Metadata */}
      <div className="text-xs text-muted-foreground pt-2 border-t">
        {t('view.addedDate', { date: new Date(item.created_at).toLocaleDateString() })}
      </div>
    </div>
  );
}
