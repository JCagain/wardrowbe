'use client';

import { useMemo } from 'react';
import { useSession } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Shirt,
  Sparkles,
  Plus,
  TrendingUp,
  Cloud,
  Droplets,
  ThumbsUp,
  ThumbsDown,
  Clock,
  Bell,
  BellOff,
  Calendar,
  CheckCircle2,
  XCircle,
  Lightbulb,
  ChevronRight,
  HeartHandshake,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { useAnalytics } from '@/lib/hooks/use-analytics';
import { useWeather } from '@/lib/hooks/use-weather';
import { usePreferences } from '@/lib/hooks/use-preferences';
import { displayValue, tempSymbol, TempUnit } from '@/lib/temperature';
import { usePendingOutfits, useAcceptOutfit, useRejectOutfit } from '@/lib/hooks/use-outfits';
import { useSchedules, useNotificationSettings } from '@/lib/hooks/use-notifications';
import { useFamily } from '@/lib/hooks/use-family';
import { toast } from 'sonner';


// 摘不删档案（spec §7）：首页的产品壳卡片。入口已下线，组件在此备查。
// 守卫（tests/pruned-entry-guard.test.ts）豁免本目录。

function NextScheduledCard() {
  const { data: schedules, isLoading } = useSchedules();
  const t = useTranslations('dashboard');
  const tDays = useTranslations('notifications');

  const nextSchedule = useMemo(() => {
    if (!schedules || schedules.length === 0) return null;

    const enabledSchedules = schedules.filter((s) => s.enabled);
    if (enabledSchedules.length === 0) return null;

    const now = new Date();
    const currentDay = now.getDay();
    const currentTime = now.getHours() * 60 + now.getMinutes();

    // Find the next scheduled notification
    let closest: { schedule: typeof enabledSchedules[0]; daysUntil: number; minutesUntil: number } | null = null;

    for (const schedule of enabledSchedules) {
      const [hours, minutes] = schedule.notification_time.split(':').map(Number);
      const scheduleMinutes = hours * 60 + minutes;

      let daysUntil = schedule.day_of_week - currentDay;
      if (daysUntil < 0 || (daysUntil === 0 && scheduleMinutes <= currentTime)) {
        daysUntil += 7;
      }

      const minutesUntil = daysUntil === 0 ? scheduleMinutes - currentTime : scheduleMinutes;

      if (!closest || daysUntil < closest.daysUntil || (daysUntil === closest.daysUntil && minutesUntil < closest.minutesUntil)) {
        closest = { schedule, daysUntil, minutesUntil };
      }
    }

    return closest;
  }, [schedules]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            {t('nextScheduled.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-6 w-32 mb-1" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  if (!nextSchedule) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            {t('nextScheduled.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-2">{t('nextScheduled.noSchedules')}</p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/dashboard/notifications">{t('nextScheduled.setUpSchedule')}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { schedule, daysUntil } = nextSchedule;
  const timeStr = schedule.notification_time.slice(0, 5);
  const dayNames = [
    tDays('days.sunday'), tDays('days.monday'), tDays('days.tuesday'),
    tDays('days.wednesday'), tDays('days.thursday'), tDays('days.friday'),
    tDays('days.saturday'),
  ];
  const dayStr = daysUntil === 0 ? t('nextScheduled.today') : daysUntil === 1 ? t('nextScheduled.tomorrow') : dayNames[schedule.day_of_week];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          {t('nextScheduled.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-semibold">
          {t('nextScheduled.dayAtTime', { day: dayStr, time: timeStr })}
        </p>
        <p className="text-sm text-muted-foreground capitalize">
          {t('nextScheduled.occasionOutfit', { occasion: schedule.occasion })}
        </p>
        {daysUntil === 0 && (
          <Badge variant="secondary" className="mt-2">{t('nextScheduled.comingUp')}</Badge>
        )}
      </CardContent>
    </Card>
  );
}

// 摘不删（spec §7）：通知状态卡已从首页下线（/notifications/settings 已摘挂），组件保留备查。
function NotificationStatusCard() {
  const { data: settings, isLoading } = useNotificationSettings();
  const t = useTranslations('dashboard');

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Bell className="h-4 w-4" />
            {t('notifications.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-4 w-full mb-2" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  const channels = settings || [];
  const enabledChannels = channels.filter((c) => c.enabled);

  if (channels.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <BellOff className="h-4 w-4 text-muted-foreground" />
            {t('notifications.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-2">{t('notifications.noChannels')}</p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/dashboard/notifications">{t('notifications.addChannel')}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Bell className="h-4 w-4" />
            {t('notifications.title')}
          </CardTitle>
          <Link href="/dashboard/notifications" className="text-xs text-muted-foreground hover:text-foreground">
            {t('notifications.configure')}
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {channels.map((channel) => (
            <Badge
              key={channel.id}
              variant={channel.enabled ? 'default' : 'outline'}
              className={channel.enabled ? '' : 'text-muted-foreground'}
            >
              {channel.enabled ? (
                <CheckCircle2 className="h-3 w-3 mr-1" />
              ) : (
                <XCircle className="h-3 w-3 mr-1" />
              )}
              {channel.channel}
            </Badge>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          {t('notifications.activeCount', { active: enabledChannels.length, total: channels.length })}
        </p>
      </CardContent>
    </Card>
  );
}


function InsightsCard() {
  const { data: analytics, isLoading } = useAnalytics();
  const legacy = analytics as { insights?: string[] } | undefined;
  const t = useTranslations('dashboard');
  const tc = useTranslations('common');

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            {t('insights.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const insights = legacy?.insights || [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            {t('insights.title')}
          </CardTitle>
          {insights.length > 3 && (
            <Link href="/dashboard/analytics" className="text-sm text-muted-foreground hover:text-foreground flex items-center">
              {tc('viewAll')} <ChevronRight className="h-4 w-4" />
            </Link>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {insights.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {insights.slice(0, 3).map((insight, i) => (
              <li key={i} className="flex items-start gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                <span className="text-muted-foreground">{insight}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">
            {t('insights.empty')}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// 摘不删（spec §7）：家庭动态卡已从首页下线（/families/me 已摘挂），组件保留备查。
function FamilyFeedCard() {
  const { data: family, isLoading } = useFamily();
  const t = useTranslations('dashboard');

  if (isLoading) return null;

  // Don't show if user has no family
  if (!family) return null;

  const memberCount = family.members.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HeartHandshake className="h-5 w-5" />
          {t('familyFeed.title')}
        </CardTitle>
        <CardDescription>
          {t('familyFeed.description')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Users className="h-4 w-4" />
          <span>{t('familyFeed.memberCount', { count: memberCount, name: family.name })}</span>
        </div>
        <Button asChild className="w-full">
          <Link href="/dashboard/family/feed">
            {t('familyFeed.browse')}
            <ChevronRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

