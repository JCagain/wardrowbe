# Reconciliation & Prune Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gaps the foundation work left behind — four live entry points into the de-listed product shell, a regression guard so no entry can creep back, and the write-back conventions that exist only in commit messages.

**Architecture:** Three small tasks on the current tree (`docs/personal-wardrobe-spec` @ `c6a50a1`): (1) de-list the leaked entries exactly the way the wash button was de-listed (comment markers, code kept); (2) add a source-scanning guard test — the i18n:scan idea applied to product-shell entries; (3) write the ruled conventions into the documents people actually read (vocabulary.md header, spec §10, plan errata). Nothing here changes backend behavior.

**Tech Stack:** React/TSX de-listing, vitest with fs-based scanning (same pattern as `tests/garment-vocabulary-parity.test.ts`), markdown docs.

**Spec:** `docs/specs/personal-wardrobe-spec.md` (§4 统计页、§7 裁剪清单、§10 解读) + the ledger rulings in `.superpowers/sdd/2026-10-02-wardrobe-foundation/progress.md`.

## Global Constraints

- 摘不删：产品壳（families/notifications/learning/wash）只摘导航/入口/路由挂载/worker 注册，**代码与表结构保留**；suggest/pairings **休眠**（不进导航，后端路由不动）。入口 = 一切可达面：导航、卡片、**工具栏按钮、空态 CTA、对话框触发器**。
- 部署/跑法变体与产品壳同批裁剪：本项目单机本地，只支持 `docker-compose.yml`(+`.dev`)；`docker-compose.prod.yml` 已下线（摘不删）。
- UI 语言 **zh-CN**；i18n parity 只查 zh-CN。
- 软词表写回双面：JSON + `vocabulary.md` 同步；禁用标记 = 行尾「已停用」；新条目插入位：类别=拼音位（兜底垫底）、风格=拼音位、颜色=渐变位（hex 明度亮→暗；黑白灰/金属保持表序追加尾部）。
- 运行时词表改动对 **worker/AI 校验集** 需重启进程生效（进程内快照）；词表写回是**单写者**不变量（单 uvicorn 进程）。
- 测试命令：后端 `docker compose exec backend python -m pytest tests/<file> -q`；前端 `docker compose exec frontend npm test -- --run`（node_modules 只在容器里）；`docker compose exec frontend npx tsc --noEmit`；`docker compose exec frontend npm run i18n:check`。
- 每步提交用 Conventional Commits，结尾带 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

## Review Focus

1. **入口面比导航大**：工具栏图标按钮（详情页 Layers/Sparkles）、空态 CTA（history）、对话框内部跳转都能把用户送进休眠面——Task 1 摘除，Task 2 用扫描测试锁死。
2. **死端点调用留在活组件里**：`outfit-preview-dialog` 的 `useFamily()` 每次打开穿搭预览都打已摘挂的 `/families/me`——Task 1 连调用带 UI 一起摘。
3. **摘不删注释本身误触守卫**：注释里若含 `/dashboard/suggest` 字样，扫描测试会当违规——Task 2 的扫描必须剥掉行注释与 JSX 注释块再匹配。
4. **约定只活在提交信息里**：「已停用」标记、渐变插入位、重启生效、单写者——用户手改 vocabulary.md 时看不见这些约定就会破坏 compile --check——Task 3 写进文档面。
5. **旧计划文稿当真**：`2026-10-02-wardrobe-foundation.md` 的代码片段被账本裁决超越（路径锚定、拼音 vs 明度、role 推导），照抄会退化——Task 3 追加勘误段（不改正文）。

---

### Task 1: 摘除残留入口（4 处）

**Files:**
- Modify: `frontend/components/item-detail-dialog.tsx`（工具栏 suggest/pairings 两按钮 + GeneratePairingsDialog 触发状态/渲染）
- Modify: `frontend/app/dashboard/history/page.tsx`（空态 CTA）
- Modify: `frontend/components/outfit-preview-dialog.tsx`（useFamily + 家庭评分块）

**Interfaces:**
- Consumes: 既有摘不删写法（见 item-detail-dialog 的洗护注释块：`// 摘不删（spec §7）：…已下线，…保留备查。`）
- Produces: 活组件对休眠面的引用清零（Task 2 的扫描断言以此为准）；`outfit-preview-dialog` 不再 import `useFamily`/`family-ratings`。

- [ ] **Step 1: 写失败的守卫断言（先于实现，见 Task 2 的测试文件）**

把 Task 2 的 `frontend/tests/pruned-entry-guard.test.ts` 先写好并运行：

Run: `docker compose exec frontend npx vitest run tests/pruned-entry-guard.test.ts`
Expected: FAIL——列出 4 个违规文件（item-detail-dialog、history/page、outfit-preview-dialog，及其命中片段）。

- [ ] **Step 2: 详情页两个按钮摘除**

`frontend/components/item-detail-dialog.tsx` 工具栏（`setShowPairingsDialog(true)` 的 Layers 按钮、`router.push('/dashboard/suggest?item=')` 的 Sparkles 按钮），整块替换为一行注释（与洗护按钮同款）：

```tsx
{/* 摘不删（spec §7）：「找搭配 / 建议搭配」入口已下线——suggest/pairings 休眠，组件保留备查。 */}
```

同文件里的配搭对话框接线一并摘（状态与渲染块换成 // 注释，import 的 `GeneratePairingsDialog` 改为注释行）：

```tsx
// 摘不删（spec §7）：GeneratePairingsDialog 触发器已下线，对话框组件保留在 components/ 备查。
// const [showPairingsDialog, setShowPairingsDialog] = useState(false);
```

- [ ] **Step 3: history 空态 CTA 摘除**

`frontend/app/dashboard/history/page.tsx` 的 `<a href="/dashboard/suggest">…</a>`（空态「去拿第一个建议」）替换为：

```tsx
{/* 摘不删（spec §7）：指向休眠 suggest 的空态 CTA 已下线。 */}
```

- [ ] **Step 4: outfit-preview 的家庭评分摘除**

`frontend/components/outfit-preview-dialog.tsx`：删除 `useFamily` 与 `family-ratings` 两个 import、`family/currentMember/isInFamily/canRate/myRating` 接线（换成 // 摘不删注释）、渲染里的 `<FamilyRatingForm>`/`<FamilyRatingsDisplay>` 块（换成 `{/* 摘不删（spec §7）：家庭评分 UI 已下线，组件保留在 components/family-ratings.tsx 备查。 */}`）。`family-ratings.tsx` 文件本身不动。

- [ ] **Step 5: 跑守卫与门禁确认转绿**

Run: `docker compose exec frontend npx vitest run tests/pruned-entry-guard.test.ts tests/item-edit-form.test.tsx && docker compose exec frontend npx tsc --noEmit && docker compose exec frontend npm run lint`
Expected: 守卫 PASS、tsc OK、lint 0 错（i18n 孤儿键保留属正常，摘不删）。

- [ ] **Step 6: 提交**

```bash
git add frontend/components/item-detail-dialog.tsx frontend/app/dashboard/history/page.tsx frontend/components/outfit-preview-dialog.tsx
git commit -m "refactor(ui): de-list the remaining product-shell entries

Toolbar buttons into suggest/pairings, the history empty-state CTA, and the
family-rating block in the outfit preview (which also fired the unmounted
/families/me call on every open). Code kept with 摘不删 markers, same as the
wash button.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 入口守卫测试（休眠面引用扫描）

**Files:**
- Create: `frontend/tests/pruned-entry-guard.test.ts`

**Interfaces:**
- Consumes: Task 1 后的源码状态（本任务的 Step 1 在 Task 1 里已先行跑红）
- Produces: `npm test` 内的常驻门禁——活源码（app/ 与 components/，除摘不删档案名单外）不得出现休眠路由字符串或死端点 hooks。

- [ ] **Step 1: 测试文件（完整代码）**

```ts
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
];
const DORMANT_COMPONENTS = [
  'components/family-ratings.tsx',
  'components/generate-pairings-dialog.tsx',
  'components/pairing-card.tsx',
];

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
      if (!DORMANT_COMPONENTS.includes(rel)) acc.push(p);
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
```

- [ ] **Step 2: 跑测试确认绿（Task 1 之后）**

Run: `docker compose exec frontend npx vitest run tests/pruned-entry-guard.test.ts`
Expected: PASS ×2。若再把任一按钮改回去，第二条立刻红——守卫咬人验证过关。

- [ ] **Step 3: 提交**

```bash
git add frontend/tests/pruned-entry-guard.test.ts
git commit -m "test(ui): guard against product-shell entries creeping back

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 口径入文档（词表约定 + spec §5/§10 + 旧计划勘误）

**Files:**
- Modify: `docs/specs/vocabulary.md`（头部说明区）
- Modify: `docs/specs/personal-wardrobe-spec.md`（§5 状态语义改三态 + §10 解读追加声明）
- Modify: `docs/superpowers/plans/2026-10-02-wardrobe-foundation.md`（**只追加**文末勘误段，不改正文）

**Interfaces:**
- Consumes: 账本裁决（`.superpowers/sdd/2026-10-02-wardrobe-foundation/progress.md` 的 T11/T12/收尾轮 Rulings）
- Produces: 用户手改 vocabulary.md 时可见的写回约定；spec §10 的四条口径声明；旧计划文末指向账本的勘误。

- [ ] **Step 1: vocabulary.md 头部说明区追加约定块**

在 `docs/specs/vocabulary.md` 现有说明段（选色规则/排序规则一带）后追加：

```markdown
> **运行时写回约定**（UI 里的「添加/改名/停用」会自动写回本表与 `garment_vocabulary.json`，两面必须一致）：
> 停用 = 行尾备注格写「已停用」（**不删行**，恢复=去掉该标记）；改名只动「中文名」格，备注/hex 格保留。
> 新行插入位：类别=中文名拼音位（其他xx 兜底永远垫底）、风格=拼音位、颜色=**渐变位**（hex 明度亮→暗；黑白灰/金属保持表序、新行追加在尾部）。
> 新增色系会自动在本表「二、颜色」末尾建段。手改本表后跑
> `docker compose exec backend python scripts/compile_vocabulary.py --check` 验证两面一致。
```

- [ ] **Step 2: spec §5 状态语义改三态、§10 追加声明**

`docs/specs/personal-wardrobe-spec.md` §5 中 `is_archived`（状态）行改为：

```markdown
- **状态三态**：新列 `lifecycle`（'active'=在役 / 'idle'=闲置 / 'retired'=已退役）；`is_archived` 保留为兼容视图（= lifecycle=='retired'），`archive_reason`/`archived_at` 仅退役时填。列表默认隐藏已退役（闲置默认可见）。旧数据迁移：is_archived=True→retired、False→active。
```

§10 追加四条声明**（含状态口径）**：

`docs/specs/personal-wardrobe-spec.md` §10 末尾追加：

```markdown
16. **状态三态**：在役/闲置/已退役（`lifecycle` 枚举）；闲置默认可见、已退役默认隐藏；统计三档口径：全部 / 排除退役（在役+闲置）/ 仅在役，默认全部。
17. **软词表写回细节**：禁用标记 = vocabulary.md 行尾「已停用」+ JSON `"disabled": true`（恢复即两处撤销）；新条目插入位见 vocabulary.md 头部约定（类别/风格=拼音位，颜色=渐变位）；运行时新增类型的 role/wash_interval 按部位推导（`ROLE_BY_PART`/`WASH_BY_PART`）。
18. **词表进程内快照**：backend/worker 的 AI 校验集与提示词在进程启动时快照，运行时增改**重启容器后**对打标签生效（前端选择器即时生效）。
19. **词表写回单写者**：JSON+markdown 写回在单 uvicorn 进程内加锁串行，JSON 面原子写（临时文件+rename）；多 worker 部署需换文件锁，本项目按单进程不变量运行。
20. **部署面**：本项目是单机本地工具，只维护 `docker-compose.yml`(+`.dev`)；上游 `docker-compose.prod.yml`（生产/Pi 变体）按摘不删下线。
```

- [ ] **Step 3: 旧计划文末追加勘误段（不改正文）**

`docs/superpowers/plans/2026-10-02-wardrobe-foundation.md` 末尾追加：

```markdown
---

## Errata（执行后与实现的差异，2026-10-04）

正文是开工时的文稿；以下裁决改变了实现细节，以 `.superpowers/sdd/2026-10-02-wardrobe-foundation/progress.md` 为准：

- **T11 路径**：不再按仓库根推导（`parents[3]` 在容器布局即断）；JSON 路径取 `garment_vocabulary.VOCABULARY_PATH`，markdown 走 `<backend根>/../docs`（compose 挂 `./docs:/docs`）。
- **T11 插入位**：颜色不是拼音位，是**渐变位**（hex 明度亮→暗；黑白灰/金属表序垫尾）——spec「颜色插渐变位」优先于本计划片段。
- **T11 禁用语义**：`"disabled"` 键仅禁用时存在（重编译字节相等）；改名保留备注/hex 格。
- **T11/T13 类型元数据**：运行时新增类型的 role/wash_interval 按部位推导（`ROLE_BY_PART`/`WASH_BY_PART`，`garment_vocabulary.py` 单源），非 FALLBACK_META 一律 3。
- **T11 并发**：写回全程锁 + markdown 先写 + JSON 原子写；单进程不变量。
- **T12**：样式芯片抽 `StyleMultiSelect`；select 型选择器的管理入口=「添加…」选项+选中项旁 ⋯（原生 select 无 hover 位）；`useStyles` 从旧硬编码 5 风格改词表单源。
- **T9**：`test_notification_workers` 的 registry 用例改钉裁剪后契约（非搬 pruned）。
- **测试命令**：前端测试/门禁在容器内跑（宿主无 node_modules）：`docker compose exec frontend npm test -- --run` 等。
- **计划未覆盖项（待用户裁决）**：spec §4 统计页的「风格分布」与「含已退役」开关，本轮未建。
```

- [ ] **Step 4: 校验文档与门禁**

Run: `docker compose exec backend python scripts/compile_vocabulary.py --check`
Expected: `vocabulary-compile: OK`（文档注记不进表格行，编译无感）。
Run: `docker compose exec frontend npm run i18n:check`
Expected: OK。

- [ ] **Step 5: 提交**

```bash
git add docs/specs/vocabulary.md docs/specs/personal-wardrobe-spec.md docs/superpowers/plans/2026-10-02-wardrobe-foundation.md
git commit -m "docs: record the vocabulary write-back conventions and as-built errata

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 状态三态数据层（lifecycle 枚举列）

**Files:**
- Create: `backend/migrations/versions/XXXX_lifecycle_status.py`（新增枚举列 + 回填）
- Modify: `backend/app/models/item.py`（`lifecycle` 列）
- Modify: `backend/app/schemas/item.py`（`lifecycle` 字段 + `is_archived` 兼容视图）
- Modify: `backend/app/services/item_service.py`（create/update/list 过滤语义）
- Test: `backend/tests/test_items.py`

**Interfaces:**
- Consumes: 现有 `is_archived`/`archive_reason`/`archived_at` 语义
- Produces: `ClothingItem.lifecycle: 'active'|'idle'|'retired'`（列名 lifecycle、PG 枚举 `item_lifecycle`）；响应同时给 `lifecycle` 与兼容 `is_archived`（=retired）；入参 `lifecycle` 优先，`is_archived=true/false` 映射 retired/active；列表默认 = 非 retired（闲置可见）。

- [ ] **Step 1: 写失败测试**（`test_items.py` 追加）

```python
class TestLifecycleStatus:
    async def test_lifecycle_defaults_and_roundtrip(self, client: AsyncClient, auth_headers):
        create = await self._create_item(client, auth_headers, {"type": "shirt", "lifecycle": "idle"})
        assert create.json()["lifecycle"] == "idle"
        assert create.json()["is_archived"] is False  # 兼容视图：只有 retired 为 True
        item_id = create.json()["id"]
        patched = await client.patch(
            f"/api/v1/items/{item_id}", json={"lifecycle": "retired"}, headers=auth_headers
        )
        assert patched.json()["lifecycle"] == "retired"
        assert patched.json()["is_archived"] is True

    async def test_legacy_is_archived_maps_to_lifecycle(self, client: AsyncClient, auth_headers):
        create = await self._create_item(client, auth_headers, {"type": "shirt", "is_archived": True})
        assert create.json()["lifecycle"] == "retired"
        idle = await self._create_item(client, auth_headers, {"type": "shirt", "lifecycle": "idle"})
        assert idle.json()["is_archived"] is False

    async def test_list_hides_retired_but_keeps_idle(self, client: AsyncClient, auth_headers):
        active = await self._create_item(client, auth_headers, {"type": "shirt"})
        idle = await self._create_item(client, auth_headers, {"type": "shirt", "lifecycle": "idle"})
        retired = await self._create_item(client, auth_headers, {"type": "shirt", "lifecycle": "retired"})
        listing = await client.get("/api/v1/items", headers=auth_headers)
        ids = {i["id"] for i in listing.json()["items"]}
        assert {active.json()["id"], idle.json()["id"]} <= ids
        assert retired.json()["id"] not in ids
        only_retired = await client.get(
            "/api/v1/items", params={"lifecycle": "retired"}, headers=auth_headers
        )
        assert only_retired.json()["items"][0]["id"] == retired.json()["id"]
```

（沿用该类已有的 `_create_item` multipart 辅助；`lifecycle` 走表单字段，与其它新字段同款。）

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_items.py -q -k Lifecycle`
Expected: FAIL（字段不存在/422）。

- [ ] **Step 3: 迁移与模型**

迁移（沿用 `e7f8a9b0c1d2` 头部风格）：`sa.Enum("active","idle","retired", name="item_lifecycle")` 新列 `clothing_items.lifecycle`，`nullable=False, server_default="active"`，随后

```sql
UPDATE clothing_items SET lifecycle = 'retired' WHERE is_archived = TRUE;
```

模型加列；schema：`ItemCreate/ItemUpdate.lifecycle: Literal['active','idle','retired'] | None`，`ItemResponse.lifecycle` + `is_archived` 改 computed（`self.lifecycle == 'retired'`，读侧不破坏旧消费者）；`item_service` 写侧：`lifecycle` 优先、`is_archived` 映射（True→retired，False→active）；列表过滤：显式 `lifecycle=` 精确筛，否则非 retired。

- [ ] **Step 4: 跑测试确认通过 + 全量**

Run: `docker compose exec backend python -m pytest tests/ -q`
Expected: PASS（含既有 is_archived 用例——兼容视图不破坏它们）。

- [ ] **Step 5: 提交**

```bash
git add backend/migrations backend/app/models/item.py backend/app/schemas/item.py backend/app/services/item_service.py backend/tests/test_items.py
git commit -m "feat(db): add lifecycle status (active/idle/retired) with is_archived compat

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 统计页风格分布 + 三档口径

**Files:**
- Modify: `backend/app/api/analytics.py`（`style_distribution`、`scope` 参数）
- Modify: `frontend/lib/hooks/use-analytics.ts`、`frontend/app/dashboard/analytics/page.tsx`
- Test: `backend/tests/test_analytics.py`

**Interfaces:**
- Consumes: Task 4 的 `lifecycle`
- Produces: `GET /api/v1/analytics?scope=all|no_retired|active_only`（默认 `all`）；响应新增 `style_distribution: [{style,count,percentage}]`；分布/排名查询按 scope 过滤 lifecycle（all=不过滤、no_retired=排除 retired、active_only=仅 active）。

- [ ] **Step 1: 写失败测试**（`test_analytics.py` 追加）

```python
    @pytest.mark.asyncio
    async def test_style_distribution_and_scope(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user: User
    ):
        db_session.add(_make_item(test_user.id, style=["casual", "y2k"]))
        db_session.add(_make_item(test_user.id, style=["casual"]))
        retired = _make_item(test_user.id, style=["casual"])
        retired.lifecycle = "retired"
        db_session.add(retired)
        await db_session.flush()

        all_scope = await client.get("/api/v1/analytics", headers=auth_headers)
        styles = {row["style"]: row["count"] for row in all_scope.json()["style_distribution"]}
        assert styles == {"casual": 3, "y2k": 1}

        active = await client.get("/api/v1/analytics", params={"scope": "active_only"}, headers=auth_headers)
        styles = {row["style"]: row["count"] for row in active.json()["style_distribution"]}
        assert styles == {"casual": 2, "y2k": 1}
```

（多主色件次口径沿用；style 分布按件计数，一件多风格各计 1。）

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_analytics.py -q -k style_and_scope`
Expected: FAIL（无 style_distribution 字段）。

- [ ] **Step 3: 实现后端 + 前端**

后端：`scope: Literal["all","no_retired","active_only"] = Query("all")`，helper `_lifecycle_clause(scope)` 挂进各查询；style 分布 = `func.unnest(ClothingItem.style)` 同款件计数。前端：`AnalyticsData` 加 `style_distribution`；统计页在颜色/类型分布旁加「风格分布」卡（复用类型分布的 Progress 行）；页首加三档选择（全部/排除退役/仅在役，`useAnalytics(scope)` 传参）。i18n 键 `analytics.statsScope.*` en+zh-CN 各三条。

- [ ] **Step 4: 跑测试与门禁**

Run: `docker compose exec backend python -m pytest tests/ -q && docker compose exec frontend npm test -- --run && docker compose exec frontend npx tsc --noEmit && docker compose exec frontend npm run i18n:check`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/analytics.py backend/tests/test_analytics.py frontend/lib/hooks/use-analytics.ts frontend/app/dashboard/analytics/page.tsx frontend/messages
git commit -m "feat(stats): style distribution and the three-tier lifecycle scope

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 三态状态 UI（详情/筛选/标注）+ 前端测试

**Files:**
- Modify: `frontend/components/item-detail-dialog.tsx`（状态控件两档→三档）
- Modify: `frontend/app/dashboard/wardrobe/page.tsx`（筛选与卡片标注）
- Modify: `frontend/lib/types.ts`（`Item.lifecycle` + 兼容 `is_archived`）
- Modify: `frontend/messages/en/wardrobe.json`、`frontend/messages/zh-CN/wardrobe.json`
- Test: `frontend/tests/item-edit-form.test.tsx`（状态映射用例）

**Interfaces:**
- Consumes: Task 4 的 API 契约（`lifecycle` 优先、`is_archived` 兼容）
- Produces: 详情状态控件三档「在役/闲置/已退役」（选退役才显示原因输入）；网格筛选状态 chips 三档；闲置件卡片标注「闲置」；en/zh-CN 各加 `status.idle`。

- [ ] **Step 1: 写失败测试**（`item-edit-form.test.tsx` 追加）

```ts
describe('lifecycle edit form', () => {
  it('maps the three states onto the edit form', () => {
    const base = { /* 同既有 baseItem */ };
    expect(editFormFromItem({ ...base, lifecycle: 'idle', is_archived: false } as unknown as Item).lifecycle).toBe('idle');
    expect(editFormFromItem({ ...base, lifecycle: 'retired', is_archived: true } as unknown as Item).lifecycle).toBe('retired');
  });
});
```

（`EditForm` 加 `lifecycle: 'active' | 'idle' | 'retired'`；`editFormFromItem` 取 `item.lifecycle ?? (item.is_archived ? 'retired' : 'active')`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec frontend npx vitest run tests/item-edit-form.test.tsx`
Expected: FAIL。

- [ ] **Step 3: 实现 UI**

详情：`is_archived` Switch 换三档 Select（在役/闲置/已退役），仅退役显示 `archive_reason`；保存提交 `lifecycle`。wardrobe 页：状态筛选 chips 加「闲置」；卡片 badge 显示闲置/已退役标注（已退役沿用现有样式）。`types.ts` 的 `Item` 加 `lifecycle`。i18n：`wardrobe.itemDetail.status.*` 三值 + 筛选键。

- [ ] **Step 4: 门禁**

Run: `docker compose exec frontend npm test -- --run && docker compose exec frontend npx tsc --noEmit && docker compose exec frontend npm run i18n:check && docker compose exec frontend npx vitest run tests/pruned-entry-guard.test.ts`
Expected: 全 PASS（守卫不误伤）。

- [ ] **Step 5: 提交**

```bash
git add frontend/components/item-detail-dialog.tsx frontend/app/dashboard/wardrobe/page.tsx frontend/lib/types.ts frontend/lib/item-edit-form.ts frontend/messages frontend/tests/item-edit-form.test.tsx
git commit -m "feat(ui): three-state lifecycle status (active/idle/retired)

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 执行顺序

Task 1→2→3 先行（收口既有欠账）；Task 4（数据层）→ Task 5（统计）→ Task 6（UI）。
Task 3 的 spec §5 状态语义文本与 Task 4 的实现必须一致（先改 spec 再实现或反之，同一提交序内完成）。
