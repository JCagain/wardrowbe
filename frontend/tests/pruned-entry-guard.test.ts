// 活源码不得进入休眠产品面：路由字符串与打已摘挂端点的 hooks 一样算入口。
// 摘不删档案（dormant 页面目录与组件文件）允许自我引用。
import { readdirSync, readFileSync, statSync } from 'fs';
import { join, sep } from 'path';
import { describe, expect, it } from 'vitest';

const FRONTEND = join(__dirname, '..');

// spec §7 摘不删档案——保留但不再可达的面。
const DORMANT_DIRS = [
  'app/dashboard/suggest',
  'app/dashboard/pairings',
  'app/dashboard/family',
  'app/dashboard/notifications',
  'app/dashboard/learning',
  'app/invite',
];
// 摘不删档案目录——保留但不再可达的组件整目录豁免。
const DORMANT_PREFIX = 'components/dormant/';

const FORBIDDEN = [
  '/dashboard/suggest',
  '/dashboard/pairings',
  '/dashboard/family',
  '/dashboard/notifications',
  '/dashboard/learning',
  'useFamily',
  'useSchedules',
  'useNotificationSettings',
  'useLogWash',
  'useWashHistory',
];

function stripComments(text: string): string {
  return text
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((line) => !line.trim().startsWith('//'))
    .join('\n');
}

function collect(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const rel = p.split(sep).join('/').replace(FRONTEND.split(sep).join('/') + '/', '');
    if (statSync(p).isDirectory()) {
      if (DORMANT_DIRS.some((d) => rel === d)) continue;
      collect(p, acc);
    } else if (/\.(ts|tsx)$/.test(name) && !p.includes(`${sep}tests${sep}`)) {
      if (!rel.startsWith(DORMANT_PREFIX)) acc.push(p);
    }
  }
  return acc;
}

describe('product-shell entries stay de-listed', () => {
  const sources = collect(join(FRONTEND, 'app')).concat(collect(join(FRONTEND, 'components')));

  it('scans a non-trivial surface', () => {
    expect(sources.length).toBeGreaterThan(30);
  });

  it('has no live source entering a dormant surface', () => {
    const offenders: string[] = [];
    for (const file of sources) {
      const code = stripComments(readFileSync(file, 'utf8'));
      const hits = FORBIDDEN.filter((needle) => code.includes(needle));
      if (hits.length) offenders.push(`${file}: ${hits.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });
});
