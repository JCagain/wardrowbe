'use client';

import { useState } from 'react';
import {
  Shirt,
  Calendar,
  TrendingUp,
  Activity,
  PieChart,
  BarChart,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { useClothingColors, useStyles, useClothingTypes } from '@/lib/hooks/use-translated-constants';
import { useAnalytics, type AnalyticsScope } from '@/lib/hooks/use-analytics';
import Image from 'next/image';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

function StatCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
}: {
  title: string;
  value: string | number;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: 'up' | 'down' | 'neutral';
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          {trend === 'up' && <TrendingUp className="h-3 w-3 text-green-500" />}
          {trend === 'down' && <TrendingUp className="h-3 w-3 text-red-500 rotate-180" />}
          {description}
        </p>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16 mb-1" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ColorBar({
  label,
  hex,
  percentage,
  count,
}: {
  label: string;
  hex?: string;
  percentage: number;
  count: number;
}) {
  const t = useTranslations('analytics');
  return (
    <div className="flex items-center gap-3">
      <div
        className="w-4 h-4 rounded border flex-shrink-0"
        style={{ backgroundColor: hex ?? 'transparent' }}
      />
      <div className="flex-1">
        <div className="flex justify-between text-sm mb-1">
          <span>{label}</span>
          <span className="text-muted-foreground">
            {t('pieces', { count })} · {t('percent', { value: percentage.toFixed(1) })}
          </span>
        </div>
        <Progress value={percentage} className="h-2" />
      </div>
    </div>
  );
}

function ItemCard({ item }: { item: { id: string; name: string | null; type: string; thumbnail_url: string | null; wear_count: number } }) {
  const t = useTranslations('analytics');
  return (
    <Link
      href={`/dashboard/wardrobe?item=${item.id}`}
      className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted transition-colors"
    >
      <div className="w-12 h-12 rounded bg-muted overflow-hidden relative flex-shrink-0">
        {item.thumbnail_url ? (
          <Image
            src={item.thumbnail_url}
            alt={item.name || item.type}
            fill
            className="object-cover"
            sizes="48px"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Shirt className="h-6 w-6 text-muted-foreground" />
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{item.name || item.type}</p>
        <p className="text-sm text-muted-foreground capitalize">{item.type}</p>
      </div>
      <Badge variant="secondary">{t('wearCount', { count: item.wear_count })}</Badge>
    </Link>
  );
}

function AcceptanceTrendChart({ data }: { data: { period: string; rate: number; total: number }[] }) {
  const t = useTranslations('analytics');
  const maxTotal = Math.max(...data.map((d) => d.total), 1);

  return (
    <div className="space-y-2">
      {data.map((week, i) => (
        <div key={i} className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-16 flex-shrink-0">{week.period}</span>
          <div className="flex-1 flex items-center gap-2">
            <div
              className="h-4 bg-primary/20 rounded relative overflow-hidden"
              style={{ width: `${(week.total / maxTotal) * 100}%`, minWidth: week.total > 0 ? '20px' : '0' }}
            >
              <div
                className="absolute inset-y-0 left-0 bg-primary rounded"
                style={{ width: `${week.rate}%` }}
              />
            </div>
            {week.total > 0 && (
              <span className="text-xs text-muted-foreground">{t('percent', { value: week.rate.toFixed(0) })}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// 摘不删（spec §7）：AI 接受趋势图已从统计页下线，组件保留备查。

export default function AnalyticsPage() {
  const t = useTranslations('analytics');
  const [scope, setScope] = useState<AnalyticsScope>('all');
  const { data, isLoading, isError } = useAnalytics(scope);
  const colorOptions = useClothingColors();
  const styles = useStyles();
  const types = useClothingTypes();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        <LoadingSkeleton />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-8 text-red-500">
        {t('loadError')}
      </div>
    );
  }

  const { wardrobe, color_distribution, type_distribution, style_distribution, most_worn, least_worn, never_worn } = data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('title')}</h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>

      {/* Lifecycle scope（spec §10.16 三档口径） */}
      <div className="flex items-center gap-2" role="group" aria-label={t('statsScope.all')}>
        {(['all', 'no_retired', 'active_only'] as const).map((value) => (
          <Button
            key={value}
            size="sm"
            variant={scope === value ? 'default' : 'outline'}
            onClick={() => setScope(value)}
          >
            {t(`statsScope.${value === 'no_retired' ? 'noRetired' : value === 'active_only' ? 'activeOnly' : 'all'}`)}
          </Button>
        ))}
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <StatCard
          title={t('stats.totalItems.title')}
          value={wardrobe.total_items}
          description={t('stats.totalItems.description', { count: wardrobe.items_by_status.ready })}
          icon={Shirt}
        />
        <StatCard
          title={t('stats.records.title')}
          value={wardrobe.total_records}
          description={t('stats.records.description', { month: wardrobe.records_this_month })}
          icon={Calendar}
        />
        <StatCard
          title={t('stats.totalWears.title')}
          value={wardrobe.total_wears}
          description={t('stats.totalWears.description')}
          icon={Activity}
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('pipeline.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {(['ready', 'processing', 'archived', 'error'] as const).map((k) => (
              <div key={k} className="rounded-md bg-muted/50 p-2">
                <dt className="text-xs text-muted-foreground">{t(`pipeline.${k}`)}</dt>
                <dd className="font-medium">{wardrobe.items_by_status[k] ?? 0}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Color Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PieChart className="h-5 w-5" />
              {t('insights.colorDistribution.title')}
            </CardTitle>
            <CardDescription>{t('insights.colorDistribution.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            {color_distribution.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('insights.colorDistribution.noData')}</p>
            ) : (
              <div className="space-y-3">
                {color_distribution.slice(0, 8).map((c) => {
                  const entry = colorOptions.find((o) => o.value === c.color);
                  return (
                    <ColorBar
                      key={c.color}
                      label={entry?.label ?? c.color}
                      hex={entry?.hex}
                      percentage={c.percentage}
                      count={c.count}
                    />
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Style Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart className="h-5 w-5" />
              {t('insights.styleDistribution.title')}
            </CardTitle>
            <CardDescription>{t('insights.styleDistribution.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            {style_distribution.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('insights.styleDistribution.noData')}</p>
            ) : (
              <div className="space-y-3">
                {style_distribution.map((style) => (
                  <div key={style.style} className="flex items-center justify-between">
                    <span>{styles.find((s) => s.value === style.style)?.label ?? style.style}</span>
                    <div className="flex items-center gap-2">
                      <Progress value={style.percentage} className="w-24 h-2" />
                      <span className="text-sm text-muted-foreground w-20 text-right">
                        {t('pieces', { count: style.count })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Type Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart className="h-5 w-5" />
              {t('insights.itemTypes.title')}
            </CardTitle>
            <CardDescription>{t('insights.itemTypes.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            {type_distribution.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('insights.itemTypes.noData')}</p>
            ) : (
              <div className="space-y-3">
                {type_distribution.map((type) => (
                  <div key={type.type} className="flex items-center justify-between">
                    <span>{types.find((e) => e.value === type.type)?.label ?? type.type}</span>
                    <div className="flex items-center gap-2">
                      <Progress value={type.percentage} className="w-24 h-2" />
                      <span className="text-sm text-muted-foreground w-12 text-right">
                        {type.count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {/* Most Worn */}
        <Card>
          <CardHeader>
            <CardTitle>{t('insights.mostWorn.title')}</CardTitle>
            <CardDescription>{t('insights.mostWorn.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            {most_worn.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('insights.mostWorn.noData')}</p>
            ) : (
              <div className="space-y-1">
                {most_worn.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Least Worn */}
        <Card>
          <CardHeader>
            <CardTitle>{t('insights.leastWorn.title')}</CardTitle>
            <CardDescription>{t('insights.leastWorn.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            {least_worn.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('insights.leastWorn.noData')}</p>
            ) : (
              <div className="space-y-1">
                {least_worn.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Never Worn */}
        <Card>
          <CardHeader>
            <CardTitle>{t('insights.neverWorn.title')}</CardTitle>
            <CardDescription>{t('insights.neverWorn.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            {never_worn.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('insights.neverWorn.noData')}</p>
            ) : (
              <div className="space-y-1">
                {never_worn.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
