'use client';

import { useSession } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Shirt,
  Plus,
  TrendingUp,
  Cloud,
  Droplets,
  ThumbsUp,
  ThumbsDown,
  Clock,
  CheckCircle2,
} from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { useAnalytics } from '@/lib/hooks/use-analytics';
import { useWeather } from '@/lib/hooks/use-weather';
import { usePreferences } from '@/lib/hooks/use-preferences';
import { displayValue, tempSymbol, TempUnit } from '@/lib/temperature';
import { usePendingOutfits, useAcceptOutfit, useRejectOutfit } from '@/lib/hooks/use-outfits';
import { toast } from 'sonner';

function WeatherCard() {
  const { data: weather, isLoading, isError } = useWeather();
  const { data: prefs } = usePreferences();
  const t = useTranslations('dashboard');
  const unit: TempUnit = prefs?.temperature_unit === 'fahrenheit' ? 'fahrenheit' : 'celsius';

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Cloud className="h-4 w-4" />
            {t('weather.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-12 w-24 mb-2" />
          <Skeleton className="h-4 w-32" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !weather) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Cloud className="h-4 w-4" />
            {t('weather.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">
            {t('weather.locationNotSet')}
          </p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/dashboard/settings">{t('weather.setLocation')}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Cloud className="h-4 w-4" />
          {t('weather.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-3xl font-bold">{displayValue(weather.temperature, unit)}{tempSymbol(unit)}</span>
          <span className="text-muted-foreground text-sm">
            {t('weather.feelsLike', { temp: `${displayValue(weather.feels_like, unit)}°` })}
          </span>
        </div>
        <p className="text-sm text-muted-foreground capitalize mb-1">
          {weather.condition}
        </p>
        {weather.precipitation_chance > 0 && (
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <Droplets className="h-3 w-3" />
            {t('weather.rainChance', { percent: weather.precipitation_chance })}
          </p>
        )}
        {/* 摘不删（spec §7）：天气卡的「拿搭配建议」入口已下线——suggest 休眠。 */}
      </CardContent>
    </Card>
  );
}

function PendingOutfitsCard() {
  const { data, isLoading } = usePendingOutfits(2);
  const acceptOutfit = useAcceptOutfit();
  const rejectOutfit = useRejectOutfit();
  const t = useTranslations('dashboard');
  const tc = useTranslations('common');

  const handleAccept = async (id: string) => {
    try {
      await acceptOutfit.mutateAsync(id);
      toast.success(t('pendingOutfits.accepted'));
    } catch {
      toast.error(t('pendingOutfits.acceptFailed'));
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectOutfit.mutateAsync(id);
      toast.success(t('pendingOutfits.dismissed'));
    } catch {
      toast.error(t('pendingOutfits.dismissFailed'));
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Clock className="h-4 w-4" />
            {t('pendingOutfits.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full mb-2" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  const pendingOutfits = data?.outfits || [];

  if (pendingOutfits.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            {t('pendingOutfits.allCaughtUp')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {t('pendingOutfits.noPending')}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Clock className="h-4 w-4 text-orange-500" />
            {t('pendingOutfits.title')}
            <Badge variant="secondary" className="ml-1">{data?.total || pendingOutfits.length}</Badge>
          </CardTitle>
          {(data?.total ?? 0) > 2 && (
            <Link href="/dashboard/history" className="text-xs text-muted-foreground hover:text-foreground">
              {tc('viewAll')}
            </Link>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {pendingOutfits.map((outfit) => (
          <div key={outfit.id} className="flex items-center gap-3">
            <div className="flex -space-x-2">
              {outfit.items.slice(0, 3).map((item) => (
                <div
                  key={item.id}
                  className="w-10 h-10 rounded-full bg-muted overflow-hidden relative border-2 border-background"
                >
                  {item.thumbnail_url ? (
                    <Image
                      src={item.thumbnail_url}
                      alt={item.name || item.type}
                      fill
                      className="object-cover"
                      sizes="40px"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Shirt className="h-4 w-4 text-muted-foreground" />
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium capitalize truncate">{outfit.occasion}</p>
              <p className="text-xs text-muted-foreground">
                {outfit.scheduled_for ? new Date(outfit.scheduled_for).toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                }) : t('pendingOutfits.lookbook')}
              </p>
            </div>
            <div className="flex gap-1">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-red-500 hover:text-red-600 hover:bg-red-50"
                onClick={() => handleReject(outfit.id)}
                disabled={rejectOutfit.isPending}
                aria-label={t('pendingOutfits.dismissLabel')}
              >
                <ThumbsDown className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-green-500 hover:text-green-600 hover:bg-green-50"
                onClick={() => handleAccept(outfit.id)}
                disabled={acceptOutfit.isPending}
              >
                <ThumbsUp className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// 摘不删（spec §7）：通知排期卡已从首页下线（/notifications/schedules 已摘挂），组件保留备查。
      {/* 摘不删（spec §7）：NextScheduledCard / NotificationStatusCard 已下线（/notifications/* 已摘挂）——归档于 components/dormant/dashboard-cards.tsx */}

function WeeklySummaryCard() {
  const { data: analytics, isLoading } = useAnalytics();
  const t = useTranslations('dashboard');

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            {t('weeklySummary.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-16 mb-1" />
          <Skeleton className="h-4 w-32" />
        </CardContent>
      </Card>
    );
  }

  if (!analytics) {
    return null;
  }

  const { wardrobe } = analytics;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <TrendingUp className="h-4 w-4" />
          {t('weeklySummary.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div>
          <p className="text-2xl font-bold">{wardrobe.outfits_this_week}</p>
          <p className="text-xs text-muted-foreground">{t('weeklySummary.outfits')}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// 摘不删（spec §7）：insights 搭配建议卡已从首页下线，组件保留备查。
// 指标已随 insights 从 AnalyticsData 摘除，这里用本地旧契约类型以便重挂。
      {/* 摘不删（spec §7）：InsightsCard / FamilyFeedCard 已下线（insights 已摘、/families/me 已摘挂）——归档于 components/dormant/dashboard-cards.tsx */}

function QuickActionsCard() {
  const t = useTranslations('dashboard');

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('quickActions.title')}</CardTitle>
        <CardDescription>{t('quickActions.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button asChild className="w-full justify-start">
          <Link href="/dashboard/wardrobe">
            <Plus className="mr-2 h-4 w-4" />
            {t('quickActions.addNewItem')}
          </Link>
        </Button>
        {/* 摘不删（spec §7）：AI 推荐休眠不进导航，入口已下线。 */}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data: session } = useSession();
  const t = useTranslations('dashboard');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          {t('welcomeBack', { name: session?.user?.name?.split(' ')[0] || t('userFallback') })}
        </h1>
        <p className="text-muted-foreground">
          {t('subtitle')}
        </p>
      </div>

      {/* Top row - Weather + Pending（通知排期卡已下线，见 NextScheduledCard 注释） */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <WeatherCard />
        <PendingOutfitsCard />
      </div>

      {/* Second row - Weekly Summary（通知状态卡已下线，见 NotificationStatusCard 注释） */}
      <div className="grid gap-4 md:grid-cols-2">
        <WeeklySummaryCard />
      </div>

      {/* Third row - Quick Actions（insights 卡已下线，见 InsightsCard 注释） */}
      <div className="grid gap-4 md:grid-cols-2">
        <QuickActionsCard />
      </div>

      {/* 家庭动态卡已下线，见 FamilyFeedCard 注释 */}
    </div>
  );
}
