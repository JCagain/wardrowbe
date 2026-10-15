import { mergeMessages } from './merge-messages';
import { getRequestConfig } from 'next-intl/server';
import {
  DEFAULT_LOCALE,
  NAMESPACES,
  type Namespace,
  type SupportedLocale,
} from '@/lib/i18n/locales';

type Messages = Record<string, Record<string, unknown>>;

// Template-literal import so webpack bundles every messages/<locale>/<ns>.json into the build.
// A runtime fs.readFileSync would not survive `output: 'standalone'`, which copies only the
// traced bundle plus .next/static.
async function loadNamespace(locale: string, namespace: Namespace): Promise<Record<string, unknown>> {
  return (await import(`../messages/${locale}/${namespace}.json`)).default;
}

async function loadMessages(locale: SupportedLocale): Promise<Messages> {
  const messages: Messages = {};

  for (const namespace of NAMESPACES) {
    const english = await loadNamespace(DEFAULT_LOCALE, namespace);

    if (locale === DEFAULT_LOCALE) {
      messages[namespace] = english;
      continue;
    }

    try {
      // English underlies every namespace so a key still awaiting translation renders its
      // English text rather than a raw key path.
      messages[namespace] = mergeMessages(english, await loadNamespace(locale, namespace));
    } catch {
      messages[namespace] = english;
    }
  }

  return messages;
}

// UI 锁 zh-CN（spec §7，fixes D4）：不读 cookie、不读 Accept-Language；其余语言文件冻结、不可达。
export const APP_LOCALE: SupportedLocale = DEFAULT_LOCALE;

export default getRequestConfig(async () => ({
  locale: APP_LOCALE,
  messages: await loadMessages(APP_LOCALE),
}));
