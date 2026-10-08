# Review Findings Fixes (10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 10 code-review findings (data loss, crash, status/lifecycle sync, scope, migration reproducibility, error surfacing, dead code), each with a regression test.

**Architecture:** Ten independent, self-contained fixes in severity order. Backend fixes land in the schema/service/worker/API layers with pytest regression tests; frontend fixes follow the repo's "extract pure helper into `frontend/lib`, test there" pattern. Finding 8 freezes vocabulary snapshots inside the migration so it no longer reads the runtime-mutable `garment_vocabulary.json`.

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Pydantic v2 + Alembic; Next.js 14 App Router + React 18 + TS + TanStack Query v5; tests run only inside the Docker Compose stack.

**Spec:** `docs/specs/personal-wardrobe-spec.md` (§5 lifecycle, §10.15 color counts, §10.16 三档口径), `docs/specs/vocabulary.md`

## Global Constraints

- Tests run ONLY in containers (host npm 9 misreads the npm-11 lockfile):
  - backend: `docker compose exec backend python -m pytest tests/ -q`
  - frontend: `docker compose exec frontend npm test -- --run`, `docker compose exec frontend npx tsc --noEmit`, `docker compose exec frontend npm run lint`
  - i18n/vocab: `docker compose exec frontend npm run i18n:check`, `docker compose exec frontend npm run vocab:check`
  - `COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml` is pinned in `.env`; run `docker compose …` from the repo root.
- Baselines before this batch: backend **833 passed**, frontend **205 passed**. After the batch both must be green and strictly larger (each task adds tests).
- i18n: `en` is the key source; parity gates `zh-CN` against `en` only; all other locales are frozen (do not touch). New keys go into **`frontend/messages/en/…` and `frontend/messages/zh-CN/…` only**.
- 摘不删 (spec §7): pruned product-shell code is kept with `// 摘不删` markers; `frontend/tests/pruned-entry-guard.test.ts` scans live sources. Never delete marked code.
- Lifecycle invariant (spec §5/§10.16): `lifecycle` is authoritative; crossing the retired boundary keeps `status` + `archived_at` in lockstep (same side effects as the archive/restore endpoints).
- The vocabulary JSON (`backend/app/data/garment_vocabulary.json`) is runtime-mutable (soft-vocab writes it back). Migrations must never read it at run time.
- Commit messages end with: `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- No credential solicitation, ever. All verification runs against the already-running container stack (7 services, healthy).

## Review Focus

1. A PATCH without `lifecycle` in the body must not touch retired bookkeeping — the boundary fix is an xor on the lifecycle axis, not a blanket "anything not retired clears". Pinned by Task 4's `test_update_without_lifecycle_leaves_retired_bookkeeping`.
2. The headline scope must keep `items_by_status`'s processing/error buckets — the cards use the lifecycle axis only; applying the distributions' finished-only filter would zero the buckets the breakdown exists to show. Pinned by Task 6's `test_scope_applies_to_headline_stats`.
3. A single detail-dialog save must both preserve unnamed tags keys AND still apply the style change it carries — round-trip fidelity and the update itself in one request. Pinned by Task 1's `test_update_preserves_ai_tag_keys`.
4. Nullable occasion must never render the string "null" or throw: card title, detail-page title, dialog title, and the clone-name prefill all need explicit fallbacks. Pinned by Task 2's `outfit-occasion-fallbacks` tests.
5. Migration re-runs must be reproducible from the migration file alone, while runtime callers of the shared helpers keep the live vocabulary default (tagging still maps types via `BODY_PART_BY_TYPE`). Pinned by Task 8's frozen-mapping tests plus the existing `test_body_part_case_sql_covers_every_seed_type` staying green.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/schemas/item.py` | `ItemTags` schema — must round-trip the whole tags JSONB blob |
| `backend/app/workers/tagging.py` | tagging completion writes; must not resurrect retired items |
| `backend/app/services/item_service.py` | `update()` boundary side effects; `mark_pending()` status mapping |
| `backend/app/api/analytics.py` | scope clause composition for headline + distributions |
| `backend/app/services/recommendation_service.py` | prompt formatter color concat guard |
| `backend/app/utils/color_migration.py` | shared migration helpers; accept frozen overrides |
| `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py` | self-contained frozen snapshots |
| `frontend/lib/types.ts`, `frontend/lib/hooks/use-outfits.ts`, `frontend/types/index.ts` | `Outfit.occasion: string \| null` |
| `frontend/components/outfits/outfit-card.tsx` | title fallback + occasion badge guard |
| `frontend/components/shared/clone-to-lookbook-dialog.tsx` | null-safe clone-name prefill |
| `frontend/components/outfit-preview-dialog.tsx`, `frontend/components/shared/lineage-card.tsx`, `frontend/components/outfit-history-card.tsx`, `frontend/app/dashboard/outfits/[id]/page.tsx`, `frontend/app/dashboard/outfits/new/page.tsx`, `frontend/app/dashboard/page.tsx`, `frontend/app/dashboard/family/feed/page.tsx` | null-safe occasion consumers |
| `frontend/lib/item-edit-form.ts` | `lifecycleLabelKey` read-view helper |
| `frontend/components/item-detail-dialog.tsx` | three-state badge; dead imports |
| `frontend/components/vocab/vocab-managed-chip.tsx` | `runVocabAction` shared error surface |
| `frontend/components/vocab/part-type-select.tsx` | rename/disable error surfacing |
| `frontend/messages/{en,zh-CN}/outfits.json`, `frontend/messages/{en,zh-CN}/wardrobe.json` | new keys `cards.untitledOutfit`, `vocabManage.actionFailed` |

---

### Task 1: Tags JSONB round-trip must survive a detail-dialog save

**Files:**
- Modify: `backend/app/schemas/item.py:20-31` (class `ItemTags`)
- Test: `backend/tests/test_items.py` (new class `TestTagsRoundTrip`)

**Interfaces:**
- Consumes: nothing from earlier tasks (first task).
- Produces: `ItemTags` accepts and returns the full tags blob (`occasion: list[str]`, `brand`, `condition`, `features: list[str]`, `logprobs_confidence: float | None`, plus any unnamed future keys). Task 10's verification depends on this staying green.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_items.py` (all imports it needs — `uuid4`, `AsyncClient`, `_make_test_image_bytes` — are already in the module):

```python
class TestTagsRoundTrip:
    """AI display metadata in the tags JSONB must survive a detail-dialog save.

    The dialog round-trips the whole tags blob through ItemUpdate on every
    save. ItemTags used to drop every key it did not name at validation and the
    service then overwrote the JSONB column — a mere rename wiped
    occasion/brand/condition/features/logprobs_confidence from the AI panel.
    """

    @pytest.mark.asyncio
    async def test_update_preserves_ai_tag_keys(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(), "image/jpeg")},
            data={"type": "shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        assert create.status_code in (200, 201), create.text
        item_id = create.json()["id"]

        # The detail dialog's save payload: the whole previous tags blob plus
        # the style the user edited.
        ai_tags = {
            "colors": ["blue"],
            "primary_color": "blue",
            "pattern": "striped",
            "style": ["casual"],
            "occasion": ["work"],
            "brand": "Acme",
            "condition": "good",
            "features": ["pocket"],
            "logprobs_confidence": 0.87,
        }
        patched = await client.patch(
            f"/api/v1/items/{item_id}",
            json={"name": "renamed", "tags": {**ai_tags, "style": ["casual", "y2k"]}},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
        tags = patched.json()["tags"]
        assert tags["occasion"] == ["work"]
        assert tags["brand"] == "Acme"
        assert tags["condition"] == "good"
        assert tags["features"] == ["pocket"]
        assert tags["logprobs_confidence"] == 0.87
        assert tags["pattern"] == "striped"
        # The update itself still applies.
        assert tags["style"] == ["casual", "y2k"]
        assert patched.json()["name"] == "renamed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestTagsRoundTrip -q`
Expected: FAIL — `tags["occasion"]` is `KeyError` (the keys were stripped by `ItemTags` validation).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas/item.py`, replace the `ItemTags` class (lines 20-31) with:

```python
class ItemTags(BaseModel):
    # AI-tagging display metadata. The AI JSON contract still names colors /
    # primary_color (see app.services.ai_service); these keys live only in the
    # tags JSONB blob, never on the item's own color columns.
    #
    # extra="allow" is load-bearing: a detail-dialog save round-trips the whole
    # blob through this schema, and Pydantic's default extra="ignore" silently
    # dropped every key the schema did not name before the JSONB column was
    # overwritten without them.
    model_config = ConfigDict(extra="allow")
    colors: list[str] = Field(default_factory=list)
    primary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    formality: str | None = None
    fit: str | None = None
    # Keys written by tags_to_item_fields — named here so the round-trip is
    # typed as well as preserved.
    occasion: list[str] = Field(default_factory=list)
    brand: str | None = None
    condition: str | None = None
    features: list[str] = Field(default_factory=list)
    logprobs_confidence: float | None = None
```

(`ConfigDict` and `Field` are already imported in this module.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestTagsRoundTrip tests/test_items.py -q`
Expected: PASS — new class green, the rest of `test_items.py` unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/item.py backend/tests/test_items.py
git commit -m "fix(api): keep AI tag keys through a detail-dialog save round-trip

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Nullable `Outfit.occasion` — type it and guard every consumer

**Files:**
- Modify: `frontend/lib/types.ts:348`, `frontend/lib/hooks/use-outfits.ts:49`, `frontend/types/index.ts:39` (`occasion: string` → `occasion: string | null`)
- Modify: `frontend/components/outfits/outfit-card.tsx:81-90` (`getCardTitle`), `:187-189` (badge)
- Modify: `frontend/components/shared/clone-to-lookbook-dialog.tsx:25-33` (prop + `defaultCloneName`)
- Modify: `frontend/app/dashboard/outfits/[id]/page.tsx:85-87` (title), `:103-105` (badge)
- Modify: `frontend/components/outfit-preview-dialog.tsx:75` (title)
- Modify: `frontend/components/shared/lineage-card.tsx:29-33` (label)
- Modify: `frontend/components/outfit-history-card.tsx:149-151` (badge)
- Modify: `frontend/app/dashboard/family/feed/page.tsx:101-103` (badge)
- Modify: `frontend/app/dashboard/page.tsx:207` (occasion line)
- Modify: `frontend/app/dashboard/outfits/new/page.tsx:324` and `:474` (no edit needed once the prop widens — listed so tsc failures there are recognized as Task 2 scope)
- Modify: `frontend/messages/en/outfits.json`, `frontend/messages/zh-CN/outfits.json` (new key `cards.untitledOutfit`)
- Test: `frontend/tests/outfit-occasion-fallbacks.test.ts` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `getCardTitle(outfit, t)` and `defaultCloneName(occasion)` are exported and null-safe; `Outfit.occasion` is `string | null` everywhere (all three declarations).

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/outfit-occasion-fallbacks.test.ts`:

```ts
import { format } from 'date-fns';
import { describe, expect, it, vi } from 'vitest';
import { getCardTitle } from '@/components/outfits/outfit-card';
import { defaultCloneName } from '@/components/shared/clone-to-lookbook-dialog';
import type { Outfit } from '@/lib/types';

// The modules render next/image and next/link; nothing here renders them.
vi.mock('next/image', () => ({ default: () => null }));
vi.mock('next/link', () => ({ default: () => null }));

// Records the interpolation values so the fallback chain is observable.
const t = (key: string, values?: Record<string, string>) =>
  values ? `${key}(${values.occasion ?? ''})` : key;

describe('getCardTitle with a nullable occasion', () => {
  it('falls back to the untitled label instead of dereferencing null', () => {
    expect(getCardTitle({ occasion: null } as unknown as Outfit, t)).toBe('untitledOutfit');
  });

  it('capitalizes the occasion into the fallback template', () => {
    expect(getCardTitle({ occasion: 'dinner' } as unknown as Outfit, t)).toBe(
      'outfitFallback(Dinner)',
    );
  });

  it('prefers name, then reasoning, then the first highlight', () => {
    expect(getCardTitle({ name: 'N', occasion: 'dinner' } as unknown as Outfit, t)).toBe('N');
    expect(getCardTitle({ reasoning: 'R', occasion: 'dinner' } as unknown as Outfit, t)).toBe('R');
    expect(getCardTitle({ highlights: ['H'], occasion: 'dinner' } as unknown as Outfit, t)).toBe('H');
  });
});

describe('defaultCloneName with a nullable occasion', () => {
  it('drops the occasion prefix instead of crashing on null', () => {
    expect(defaultCloneName(null)).toBe(format(new Date(), 'MMM d'));
    expect(defaultCloneName('')).toBe(format(new Date(), 'MMM d'));
  });

  it('keeps the capitalized prefix for a present occasion', () => {
    expect(defaultCloneName('dinner')).toBe(`Dinner — ${format(new Date(), 'MMM d')}`);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- --run tests/outfit-occasion-fallbacks.test.ts`
Expected: FAIL — `getCardTitle` and `defaultCloneName` are not exported (import error), and the `null.charAt` crash is the bug under test.

- [ ] **Step 3: Write minimal implementation**

1. **Types** — in all three files, change the field to `occasion: string | null;` (`frontend/lib/types.ts:348`, `frontend/lib/hooks/use-outfits.ts:49`, `frontend/types/index.ts:39`).

2. **`frontend/components/outfits/outfit-card.tsx`** — export and null-guard `getCardTitle` (replace lines 81-90):

```tsx
export function getCardTitle(outfit: Outfit, t: any): string {
  if (outfit.name) return outfit.name;
  if (outfit.reasoning) return outfit.reasoning;
  if (outfit.highlights && outfit.highlights.length > 0) {
    return outfit.highlights[0];
  }
  // occasion is nullable (the external-authoring path may omit it) — never
  // dereference it blind, and fall back to a plain label when it is absent.
  if (outfit.occasion) {
    const occasion =
      outfit.occasion.charAt(0).toUpperCase() + outfit.occasion.slice(1);
    return t('outfitFallback', { occasion });
  }
  return t('untitledOutfit');
}
```

Replace the occasion badge (lines 187-189) so an absent occasion does not render an empty pill:

```tsx
            {outfit.occasion && (
              <Badge variant="outline" className="capitalize">
                {outfit.occasion}
              </Badge>
            )}
```

3. **`frontend/components/shared/clone-to-lookbook-dialog.tsx`** — widen the prop and make the prefill null-safe (this file has the same `charAt(0)` crash):

```tsx
interface CloneToLookbookDialogProps {
  open: boolean;
  sourceOutfitId: string;
  sourceOccasion: string | null;
  onClose: () => void;
  onSuccess?: (newOutfitId: string) => void;
}

export function defaultCloneName(occasion: string | null): string {
  const date = format(new Date(), 'MMM d');
  if (!occasion) return date;
  const occasionTitle = occasion.charAt(0).toUpperCase() + occasion.slice(1);
  return `${occasionTitle} — ${date}`;
}
```

4. **`frontend/app/dashboard/outfits/[id]/page.tsx`** — title (lines 85-87):

```tsx
  const title =
    outfit.name ||
    outfit.reasoning ||
    (outfit.occasion
      ? t('cards.outfitFallback', { occasion: outfit.occasion })
      : t('cards.untitledOutfit'));
```

Badge (lines 103-105):

```tsx
          {outfit.occasion && (
            <Badge variant="outline" className="capitalize">
              {outfit.occasion}
            </Badge>
          )}
```

5. **`frontend/components/outfit-preview-dialog.tsx:75`** — bind the outfits.cards namespace beside the existing hooks (`const tCards = useTranslations('outfits.cards');`) and replace the title line:

```tsx
            <h2 className="text-lg font-semibold capitalize">
              {outfit.occasion ? t('title', { occasion: outfit.occasion }) : tCards('untitledOutfit')}
            </h2>
```

6. **`frontend/components/shared/lineage-card.tsx`** — replace lines 29-33 (empty interpolation collapses in HTML, so the existing messages keep their grammar):

```tsx
  const occasion = referenced.occasion ?? '';
  const label = isReplacement
    ? referenced.scheduled_for
      ? t('replacesWithDate', { occasion, date: format(parseISO(referenced.scheduled_for), 'MMM d') })
      : t('replaces', { occasion })
    : t('fromLookbook', { name: referenced.name || referenced.occasion || '' });
```

7. **`frontend/components/outfit-history-card.tsx`** (lines 149-151) and **`frontend/app/dashboard/family/feed/page.tsx`** (lines 101-103) — same badge guard:

```tsx
            {outfit.occasion && (
              <Badge variant="secondary" className="capitalize text-xs">
                {outfit.occasion}
              </Badge>
            )}
```

8. **`frontend/app/dashboard/page.tsx:207`** — guard the occasion line:

```tsx
              {outfit.occasion && (
                <p className="text-sm font-medium capitalize truncate">{outfit.occasion}</p>
              )}
```

9. **i18n** — add `cards.untitledOutfit` under the `cards` object in both `frontend/messages/en/outfits.json` and `frontend/messages/zh-CN/outfits.json`:
   - en: `"untitledOutfit": "Untitled outfit"`
   - zh-CN: `"untitledOutfit": "未命名搭配"`

- [ ] **Step 4: Run tests and type-check to verify they pass**

Run: `docker compose exec frontend npm test -- --run tests/outfit-occasion-fallbacks.test.ts && docker compose exec frontend npx tsc --noEmit && docker compose exec frontend npm run i18n:check`
Expected: tests PASS; tsc emits **zero** errors (the known nullable-occasion error set is exactly 10 errors across the files above; all must be gone); i18n check green.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/hooks/use-outfits.ts frontend/types/index.ts \
  frontend/components/outfits/outfit-card.tsx frontend/components/shared/clone-to-lookbook-dialog.tsx \
  frontend/app/dashboard/outfits/ frontend/components/outfit-preview-dialog.tsx \
  frontend/components/shared/lineage-card.tsx frontend/components/outfit-history-card.tsx \
  frontend/app/dashboard/page.tsx frontend/app/dashboard/family/feed/page.tsx \
  frontend/messages/en/outfits.json frontend/messages/zh-CN/outfits.json \
  frontend/tests/outfit-occasion-fallbacks.test.ts
git commit -m "fix(ui): null-safe outfit occasion across cards, dialogs and clone flow

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Tagging completion must not write retired items back to ready

**Files:**
- Modify: `backend/app/workers/tagging.py:276-286` (write loop's `status` handling)
- Modify: `backend/app/services/item_service.py:360-368` (`mark_pending`)
- Test: `backend/tests/test_item_tagging.py` (add cases to `TestCreateGating` and `TestWorkerTaggingOrigin`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a retired item's terminal `status` is `ItemStatus.archived` from every pipeline exit (tagging completion, `mark_pending(set_ready=True)`). Task 4's tests rely on create-as-retired leaving `status="archived"`.

- [ ] **Step 1: Write the failing tests**

Add to `TestCreateGating` in `backend/tests/test_item_tagging.py` (copy the `skip_ai` test's mock pattern exactly):

```python
    @pytest.mark.asyncio
    async def test_skip_ai_retired_item_is_archived_not_ready(self, client: AsyncClient, auth_headers):
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                data={"skip_ai": "true", "lifecycle": "retired"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["lifecycle"] == "retired"
        assert data["status"] == "archived"
        assert data["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_not_called()
```

Add to `TestWorkerTaggingOrigin` (copy `test_happy_path_stamps_auto`'s stub pattern):

```python
    @pytest.mark.asyncio
    async def test_retired_item_stays_archived_after_tagging(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/worker-retired.jpg",
            status=ItemStatus.processing,
            lifecycle="retired",
        )
        db_session.add(item)
        await db_session.commit()

        stub_tags = ClothingTags(
            type="shirt", primary_color="blue", colors=["blue"], confidence=0.9
        )

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path):
                return stub_tags

        monkeypatch.setattr(tagging, "AIService", _StubAI)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item.id), __file__)

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.status == ItemStatus.archived
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend python -m pytest tests/test_item_tagging.py -q -k "retired or skip_ai_retired"`
Expected: FAIL — both new tests see `status == "ready"` where `ItemStatus.archived` is required.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/workers/tagging.py`, split `status` out of the always-update tuple in the write loop (around lines 276-286). The tuple becomes `("ai_processed", "ai_confidence", "ai_raw_response", "tags", "ai_description")` and a new branch handles `status`:

```python
            for field, value in ai_fields.items():
                # Always update AI metadata fields (including tags JSONB and description)
                if field in (
                    "ai_processed",
                    "ai_confidence",
                    "ai_raw_response",
                    "tags",
                    "ai_description",
                ):
                    setattr(item, field, value)
                elif field == "status":
                    # Tagging must not resurrect a retired item: its terminal
                    # status is archived, whatever the pipeline computed
                    # (spec §10.16 status/lifecycle sync).
                    setattr(
                        item,
                        field,
                        ItemStatus.archived if item.lifecycle == "retired" else value,
                    )
                elif field in ("tagging_status", "tagged_by", "tagged_at"):
```

In `backend/app/services/item_service.py`, replace `mark_pending` (lines 360-368):

```python
    async def mark_pending(self, item: ClothingItem, *, set_ready: bool = False) -> ClothingItem:
        if set_ready:
            # create-as-retired + skip_ai lands here; a retired item's terminal
            # status is archived — same sync rule as the tagging write path.
            item.status = (
                ItemStatus.archived if item.lifecycle == "retired" else ItemStatus.ready
            )
        item.tagging_status = TaggingStatus.pending
        item.tagged_by = None
        item.tagged_at = None
        await self.db.flush()
        result = await self.get_by_id(item.id, item.user_id)
        return result  # type: ignore[return-value]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend python -m pytest tests/test_item_tagging.py tests/test_tagging_durability.py tests/test_tagging_worker.py tests/test_items.py -q`
Expected: PASS — new cases green; existing `status == "ready"` expectations (active items) unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/tagging.py backend/app/services/item_service.py backend/tests/test_item_tagging.py
git commit -m "fix(sync): tagging completion must not write retired items back to ready

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: retired → idle boundary clears the archived bookkeeping

**Files:**
- Modify: `backend/app/services/item_service.py:315-323` (boundary block in `update()`)
- Test: `backend/tests/test_items.py` (add cases to `TestLifecycleStatus`)

**Interfaces:**
- Consumes: nothing from earlier tasks (tests set up retired bookkeeping via a `PATCH {"lifecycle": "retired"}` transition, not via create).
- Produces: crossing the retired boundary in **either** direction, to **any** of the three states, keeps `status` + `archived_at` in lockstep; a PATCH without `lifecycle` never touches them.

- [ ] **Step 1: Write the failing tests**

Add to `TestLifecycleStatus` in `backend/tests/test_items.py` (uses the class's existing `_create` helper):

```python
    @pytest.mark.asyncio
    async def test_retired_to_idle_clears_archived_side_effects(
        self, client: AsyncClient, auth_headers
    ):
        create = await self._create(client, auth_headers, {"type": "shirt"}, seed=7)
        assert create.status_code in (200, 201), create.text
        item_id = create.json()["id"]

        retired = await client.patch(
            f"/api/v1/items/{item_id}", json={"lifecycle": "retired"}, headers=auth_headers
        )
        assert retired.status_code == 200, retired.text
        assert retired.json()["status"] == "archived"
        assert retired.json()["archived_at"] is not None

        patched = await client.patch(
            f"/api/v1/items/{item_id}", json={"lifecycle": "idle"}, headers=auth_headers
        )
        assert patched.status_code == 200, patched.text
        data = patched.json()
        assert data["lifecycle"] == "idle"
        assert data["status"] == "ready"
        assert data["archived_at"] is None

    @pytest.mark.asyncio
    async def test_update_without_lifecycle_leaves_retired_bookkeeping(
        self, client: AsyncClient, auth_headers
    ):
        create = await self._create(client, auth_headers, {"type": "shirt"}, seed=8)
        assert create.status_code in (200, 201), create.text
        item_id = create.json()["id"]
        await client.patch(
            f"/api/v1/items/{item_id}", json={"lifecycle": "retired"}, headers=auth_headers
        )

        # A rename of a retired item must not quietly restore it.
        patched = await client.patch(
            f"/api/v1/items/{item_id}", json={"name": "still retired"}, headers=auth_headers
        )
        assert patched.status_code == 200, patched.text
        data = patched.json()
        assert data["lifecycle"] == "retired"
        assert data["status"] == "archived"
        assert data["archived_at"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestLifecycleStatus -q`
Expected: `test_retired_to_idle_clears_archived_side_effects` FAILS — `status` stays `"archived"` and `archived_at` stays set. (`test_update_without_lifecycle_leaves_retired_bookkeeping` may already pass; it pins the xor guard's other edge.)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/item_service.py`, replace the boundary block (lines 315-323):

```python
        # Crossing the retired boundary keeps the same side effects as the
        # dedicated archive/restore endpoints (status + archived_at). The
        # trigger is the lifecycle axis — any in/out transition counts, not
        # just the retired↔active pair, and a desynced boolean must not skip it.
        if "lifecycle" in update_data:
            was_retired = item.lifecycle == "retired"
            now_retired = update_data["lifecycle"] == "retired"
            if now_retired and not was_retired:
                update_data["archived_at"] = datetime.now(UTC)
                update_data["status"] = ItemStatus.archived
            elif was_retired and not now_retired:
                update_data["archived_at"] = None
                update_data["status"] = ItemStatus.ready
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend python -m pytest tests/test_items.py -q`
Expected: PASS — both new cases green; existing `TestLifecycleStatus` cases unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/item_service.py backend/tests/test_items.py
git commit -m "fix(sync): retired→idle crossing clears the archived bookkeeping

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Three-state lifecycle label on the detail read view

**Files:**
- Modify: `frontend/lib/item-edit-form.ts` (add `lifecycleLabelKey`)
- Modify: `frontend/components/item-detail-dialog.tsx:924-927` (read-view badge)
- Test: `frontend/tests/item-edit-form.test.tsx` (add describe block)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `lifecycleLabelKey(item: Pick<Item, 'lifecycle' | 'is_archived'>): 'statusActive' | 'statusIdle' | 'statusRetired'`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/item-edit-form.test.tsx` (extend the existing `lifecycle edit form` area; `Item` type is already imported there):

```ts
describe('lifecycle read-view label', () => {
  it('maps the three states onto distinct status keys', () => {
    expect(lifecycleLabelKey({ lifecycle: 'active', is_archived: false })).toBe('statusActive');
    expect(lifecycleLabelKey({ lifecycle: 'idle', is_archived: false })).toBe('statusIdle');
    expect(lifecycleLabelKey({ lifecycle: 'retired', is_archived: true })).toBe('statusRetired');
  });

  it('falls back to the compat view for rows without lifecycle', () => {
    expect(lifecycleLabelKey({ is_archived: true } as Item)).toBe('statusRetired');
    expect(lifecycleLabelKey({ is_archived: false } as Item)).toBe('statusActive');
  });
});
```

Add `lifecycleLabelKey` to the import from `@/lib/item-edit-form` at the top of the test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- --run tests/item-edit-form.test.tsx`
Expected: FAIL — `lifecycleLabelKey` is not exported.

- [ ] **Step 3: Write minimal implementation**

Append to `frontend/lib/item-edit-form.ts` (mirrors `editFormFromItem`'s compat fallback):

```ts
/** Read-view status label for the three-state lifecycle (spec §10.16). */
export function lifecycleLabelKey(
  item: Pick<Item, 'lifecycle' | 'is_archived'>,
): 'statusActive' | 'statusIdle' | 'statusRetired' {
  // lifecycle is the authority; fall back to the compat view for older rows.
  const lifecycle = item.lifecycle ?? (item.is_archived ? 'retired' : 'active');
  if (lifecycle === 'retired') return 'statusRetired';
  if (lifecycle === 'idle') return 'statusIdle';
  return 'statusActive';
}
```

In `frontend/components/item-detail-dialog.tsx`, extend the existing import (line 69) with `lifecycleLabelKey` and replace the read-view badge (lines 924-927):

```tsx
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">{t('status')}</span>
                      <Badge variant={item.is_archived ? 'outline' : 'secondary'}>
                        {t(lifecycleLabelKey(item))}
                      </Badge>
                      {item.is_archived && item.archive_reason && (
                        <span className="text-muted-foreground truncate">{item.archive_reason}</span>
                      )}
                    </div>
```

(The i18n keys `statusActive` / `statusIdle` / `statusRetired` already exist in `wardrobe.itemDetail` for both en and zh-CN.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec frontend npm test -- --run tests/item-edit-form.test.tsx && docker compose exec frontend npx tsc --noEmit`
Expected: PASS, tsc clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/item-edit-form.ts frontend/components/item-detail-dialog.tsx frontend/tests/item-edit-form.test.tsx
git commit -m "fix(ui): three-state lifecycle label on the item detail read view

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: Lifecycle scope applies to the headline wardrobe cards

**Files:**
- Modify: `backend/app/api/analytics.py:101-112` (`_scope_clause` split), `:140-149` (`items_query`)
- Test: `backend/tests/test_analytics.py` (add `test_scope_applies_to_headline_stats` to `TestStyleDistributionAndScope`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_lifecycle_clause(scope)` — the scope's lifecycle axis alone; `_scope_clause(scope)` = `_lifecycle_clause` ∧ "not unfinished" for the distributions.

- [ ] **Step 1: Write the failing test**

Add to `TestStyleDistributionAndScope` in `backend/tests/test_analytics.py` (uses the module's `_make_item` helper; `ItemStatus` is already imported):

```python
    @pytest.mark.asyncio
    async def test_scope_applies_to_headline_stats(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user: User
    ):
        db_session.add(_make_item(test_user.id, lifecycle="active", wear_count=3))
        db_session.add(_make_item(test_user.id, lifecycle="idle", wear_count=2))
        db_session.add(
            _make_item(
                test_user.id, lifecycle="retired", wear_count=5, status=ItemStatus.archived
            )
        )
        db_session.add(
            _make_item(
                test_user.id, lifecycle="active", wear_count=1, status=ItemStatus.processing
            )
        )
        await db_session.flush()

        all_scope = (await client.get("/api/v1/analytics", headers=auth_headers)).json()
        assert all_scope["wardrobe"]["total_items"] == 4
        assert all_scope["wardrobe"]["total_wears"] == 11
        assert all_scope["wardrobe"]["items_by_status"]["ready"] == 2

        active_only = (
            await client.get(
                "/api/v1/analytics", params={"scope": "active_only"}, headers=auth_headers
            )
        ).json()
        assert active_only["wardrobe"]["total_items"] == 2
        assert active_only["wardrobe"]["total_wears"] == 4
        # The pipeline breakdown keeps its buckets in scope — the finished-only
        # filter of the distributions must not zero processing/error out.
        assert active_only["wardrobe"]["items_by_status"] == {
            "ready": 1,
            "processing": 1,
            "archived": 0,
            "error": 0,
        }

        no_retired = (
            await client.get(
                "/api/v1/analytics", params={"scope": "no_retired"}, headers=auth_headers
            )
        ).json()
        assert no_retired["wardrobe"]["total_items"] == 3
        assert no_retired["wardrobe"]["total_wears"] == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_analytics.py -q`
Expected: FAIL — `total_items` is 4 under every scope (no scope on the headline query).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/analytics.py`, add `true` to the sqlalchemy import (line 7: `from sqlalchemy import and_, case, func, select, true`) and replace `_scope_clause` (lines 101-112) with:

```python
Scope = Literal["all", "no_retired", "active_only"]


def _lifecycle_clause(scope: Scope):
    """The scope's lifecycle axis alone (spec §10.16)：全部 / 排除退役 / 仅在役."""
    if scope == "active_only":
        return ClothingItem.lifecycle == "active"
    if scope == "no_retired":
        return ClothingItem.lifecycle != "retired"
    return true()


def _scope_clause(scope: Scope):
    """统计三档口径（spec §10.16）：全部 / 排除退役 / 仅在役。

    Unfinished pipeline states (processing/error) never count in the
    distributions, whatever the scope; the scope axis is the lifecycle column.
    """
    unfinished = ClothingItem.status.in_([ItemStatus.processing, ItemStatus.error])
    return and_(_lifecycle_clause(scope), ~unfinished)
```

Replace `items_query`'s `.where(...)` (lines 140-149):

```python
    # Headline cards take the lifecycle axis only, not the finished-only filter
    # the distributions use: items_by_status is the pipeline's own breakdown and
    # must still show its processing/error buckets in scope (spec §10.16).
    items_query = select(
        func.count(ClothingItem.id).label("total"),
        func.sum(case((ClothingItem.status == ItemStatus.ready, 1), else_=0)).label("ready"),
        func.sum(case((ClothingItem.status == ItemStatus.processing, 1), else_=0)).label(
            "processing"
        ),
        func.sum(case((ClothingItem.status == ItemStatus.archived, 1), else_=0)).label("archived"),
        func.sum(case((ClothingItem.status == ItemStatus.error, 1), else_=0)).label("error"),
        func.sum(ClothingItem.wear_count).label("total_wears"),
    ).where(and_(ClothingItem.user_id == current_user.id, _lifecycle_clause(scope)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend python -m pytest tests/test_analytics.py tests/test_analytics_insights.py -q`
Expected: PASS — new case green; the keep-list assertion and `test_scope_filters_lifecycle` unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/analytics.py backend/tests/test_analytics.py
git commit -m "fix(stats): lifecycle scope applies to the headline wardrobe cards

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Guard None color arrays in the recommendation formatter

**Files:**
- Modify: `backend/app/services/recommendation_service.py:249`
- Test: `backend/tests/test_recommendation_service.py` (add case to `TestFormatItemsEnriched`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_format_items_for_prompt` is total over items whose array columns are still `None` (pre-INSERT), same as `pairing_service`'s formatter.

- [ ] **Step 1: Write the failing test**

Add to `TestFormatItemsEnriched` in `backend/tests/test_recommendation_service.py` (uses the module's `_make_item`, `ScoredItem`, `date`):

```python
    def test_null_color_arrays_do_not_crash(self):
        # Freshly built items carry None array columns until INSERT — the
        # same hole pairing_service's formatter already guards.
        service = RecommendationService.__new__(RecommendationService)
        item = _make_item(primary_colors=None, secondary_colors=None)
        scored = [ScoredItem(item=item)]

        text, _ = service._format_items_for_prompt(scored, {}, date(2026, 3, 8))
        assert "shirt" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_recommendation_service.py::TestFormatItemsEnriched -q`
Expected: FAIL — `TypeError: unsupported operand type(s) for +: 'NoneType' and 'NoneType'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/recommendation_service.py`, replace line 249:

```python
            # `or []`: freshly built items carry None array columns until
            # INSERT (same guard as pairing_service's formatter).
            all_colors = (item.primary_colors or []) + (item.secondary_colors or [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend python -m pytest tests/test_recommendation_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "fix(suggest): guard None color arrays in the recommendation formatter

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Freeze the vocabulary snapshots the data migration reads

**Files:**
- Modify: `backend/app/utils/color_migration.py` (`body_part_case_sql`, `migrate_legacy_colors`, `_normalize` — optional frozen overrides, live defaults preserved)
- Modify: `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py` (embed snapshots; pass them in)
- Test: `backend/tests/test_color_migration.py` (two new cases)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `body_part_case_sql(type_column, mapping=None)`, `migrate_legacy_colors(primary_color, colors, valid=None)` — defaults stay live for runtime callers (tagging/`item_service`); the migration passes `_TYPE_BODY_PART` / `_COLOR_VALUES` from its own module.

Note: this migration has already run on the dev DB. Alembic does not checksum migration files, and the seed vocabulary has not drifted yet, so editing the file only changes **fresh** runs (which is the point); already-written rows are untouched.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_color_migration.py`:

```python
def test_body_part_case_sql_accepts_a_frozen_mapping():
    sql = body_part_case_sql("type", mapping={"shirt": "tops", "jeans": "bottoms"})
    assert "WHEN type = 'shirt' THEN 'tops'" in sql
    assert "WHEN type = 'jeans' THEN 'bottoms'" in sql
    # Nothing outside the snapshot may leak in from the live vocabulary.
    assert "'dress'" not in sql


def test_migrate_legacy_colors_accepts_a_frozen_valid_set():
    assert migrate_legacy_colors("red", ["blue", "chartreuse"], valid={"red", "blue"}) == (
        ["red"],
        ["blue"],
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend python -m pytest tests/test_color_migration.py -q`
Expected: FAIL — `TypeError: body_part_case_sql() got an unexpected keyword argument 'mapping'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/utils/color_migration.py`, replace `_normalize`, `migrate_legacy_colors` and `body_part_case_sql` (keep `LEGACY_COLOR_ALIASES` and the imports as they are):

```python
def _normalize(value: str | None, valid: set[str]) -> str | None:
    """Map a legacy/AI color onto the vocabulary — or drop it.

    Policy (spec §1.4): a direct vocabulary hit always wins (a live color must
    never be alias-rewritten — "lavender" is both a live color and a legacy
    alias for "taro"), then the alias table; what is still outside the
    vocabulary is discarded rather than written through.
    """
    if not value:
        return None
    value = value.strip().lower()
    if value in valid:
        return value
    value = LEGACY_COLOR_ALIASES.get(value, value)
    return value if value in valid else None


def migrate_legacy_colors(
    primary_color: str | None,
    colors: list[str] | None,
    valid: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Split/normalize the legacy (primary_color, colors) shape.

    `valid` defaults to the live vocabulary; the DB data migration passes a
    frozen snapshot so re-runs stay reproducible.
    """
    valid = COLOR_VALUE_SET if valid is None else valid
    primary = _normalize(primary_color, valid)
    primary_list = [primary] if primary else []
    secondary: list[str] = []
    for raw in colors or []:
        value = _normalize(raw, valid)
        if value and value not in primary_list and value not in secondary:
            secondary.append(value)
    return primary_list, secondary


def body_part_case_sql(type_column: str, mapping: dict[str, str] | None = None) -> str:
    """CASE expression mapping a type column onto body_part slugs.

    `mapping` defaults to the live vocabulary; the DB data migration passes a
    frozen snapshot so re-runs stay reproducible.
    """
    branches = " ".join(
        f"WHEN {type_column} = '{value}' THEN '{part}'"
        for value, part in sorted((BODY_PART_BY_TYPE if mapping is None else mapping).items())
    )
    return f"CASE {branches} ELSE NULL END"
```

In `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py`, add the frozen snapshots right after the `depends_on` line:

```python
# Frozen snapshots of the seed vocabulary (2026-10-02). The runtime vocabulary
# file is soft-writable — vocab management writes it back — so deriving these
# values from it at run time makes a fresh migration write different
# body_part/color values on any machine whose vocabulary has drifted.
# Migrations must be reproducible from their own contents.
_TYPE_BODY_PART: dict[str, str] = {
    "tank-top": "tops",
    "shirt": "tops",
    "vest": "tops",
    "sweater": "tops",
    "bandeau": "tops",
    "polo": "tops",
    "t-shirt": "tops",
    "hoodie": "tops",
    "top": "tops",
    "skirt": "bottoms",
    "pants": "bottoms",
    "shorts": "bottoms",
    "jeans": "bottoms",
    "slacks": "bottoms",
    "sweatpants": "bottoms",
    "bottom": "bottoms",
    "jumpskirt": "dresses",
    "slip-dress": "dresses",
    "dress": "dresses",
    "suit": "dresses",
    "coat": "outerwear",
    "trench": "outerwear",
    "jacket": "outerwear",
    "cardigan": "outerwear",
    "blazer": "outerwear",
    "down-jacket": "outerwear",
    "heels": "footwear",
    "sandals": "footwear",
    "shoes": "footwear",
    "slippers": "footwear",
    "socks": "footwear",
    "boots": "footwear",
    "sneakers": "footwear",
    "bag": "accessories",
    "tie": "accessories",
    "hat": "accessories",
    "circle-lens": "accessories",
    "watch": "accessories",
    "scarf": "accessories",
    "glasses": "accessories",
    "belt": "accessories",
    "accessories": "accessories",
    "ear-cuff": "jewelry",
    "earrings": "jewelry",
    "hair-accessory": "jewelry",
    "ring": "jewelry",
    "bracelet": "jewelry",
    "bangle": "jewelry",
    "neck-ring": "jewelry",
    "necklace": "jewelry",
    "brooch": "jewelry",
    "jewelry": "jewelry",
}
_COLOR_VALUES: set[str] = {
    "black", "white", "gray", "dark-gray", "light-gray", "off-white",
    "brown", "khaki", "camel", "caramel", "coffee",
    "red", "cherry", "brick", "wine", "dark-red",
    "yellow", "lemon", "cream", "ginger", "pumpkin",
    "orange", "tangerine",
    "green", "mint", "avocado", "grass", "olive", "army", "dark-green",
    "blue", "sky", "misty", "royal", "denim", "klein", "navy",
    "purple", "taro", "lavender", "grape",
    "pink", "sakura", "lotus", "coral", "rose",
    "gold", "silver",
}
```

Then pass the snapshots at the call sites in `upgrade()`:

- `body_part_case_sql("type")` → `body_part_case_sql("type", mapping=_TYPE_BODY_PART)` (both call sites: inside the per-row UPDATE and the `WHERE body_part IS NULL` sweep)
- `migrate_legacy_colors(row.primary_color, row.colors)` → `migrate_legacy_colors(row.primary_color, row.colors, valid=_COLOR_VALUES)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend python -m pytest tests/test_color_migration.py tests/test_item_tagging.py -q`
Expected: PASS — the two new cases green, the pre-existing default-behavior cases (`test_migrate_legacy_colors`, `test_body_part_case_sql_covers_every_seed_type`) still green via the live defaults.

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/color_migration.py backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py backend/tests/test_color_migration.py
git commit -m "fix(db): freeze the vocabulary snapshots the data migration reads

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: Surface vocab rename/disable failures

**Files:**
- Modify: `frontend/components/vocab/vocab-managed-chip.tsx:80` (disable), `:103-111` (rename save) — add exported `runVocabAction`
- Modify: `frontend/components/vocab/part-type-select.tsx:105-107` (disable), `:128-134` (rename save)
- Modify: `frontend/messages/en/wardrobe.json`, `frontend/messages/zh-CN/wardrobe.json` (new key `vocabManage.actionFailed`)
- Test: `frontend/tests/vocab-action-errors.test.ts` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `runVocabAction(t, fn): Promise<boolean>` in `vocab-managed-chip.tsx` — resolves `true` on success, toasts `vocabManage.actionFailed` and resolves `false` on rejection/throw.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/vocab-action-errors.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { runVocabAction } from '@/components/vocab/vocab-managed-chip';

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

// setup.ts's next-intl stub already renders keys as-is.
const t = (key: string) => key;

describe('runVocabAction', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports a failed mutation and returns false', async () => {
    const ok = await runVocabAction(t, () => Promise.reject(new Error('offline')));
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('actionFailed');
  });

  it('stays quiet and returns true on success', async () => {
    const ok = await runVocabAction(t, () => Promise.resolve());
    expect(ok).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('catches synchronous throws too', async () => {
    const ok = await runVocabAction(t, () => {
      throw new Error('boom');
    });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('actionFailed');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- --run tests/vocab-action-errors.test.ts`
Expected: FAIL — `runVocabAction` is not exported.

- [ ] **Step 3: Write minimal implementation**

In `frontend/components/vocab/vocab-managed-chip.tsx`, add below the `VocabEntryHandlers` interface (toast is already imported):

```tsx
/**
 * Run one soft-vocabulary mutation and surface failures. A bare await on
 * patch.mutateAsync left an unhandled rejection, a stuck dialog and no toast.
 */
export async function runVocabAction(
  t: (key: string) => string,
  fn: () => void | Promise<unknown>,
): Promise<boolean> {
  try {
    await fn();
    return true;
  } catch {
    toast.error(t('actionFailed'));
    return false;
  }
}
```

Replace the rename-save `onClick` (the button around lines 103-111):

```tsx
              <Button
                onClick={async () => {
                  const next = draft.trim();
                  if (!next) {
                    toast.error(t('invalid'));
                    return;
                  }
                  if (await runVocabAction(t, () => handlers.onRename(value, next))) {
                    setRenameOpen(false);
                  }
                }}
              >
                {t('save')}
              </Button>
```

Replace the disable menu item (line 80):

```tsx
              <DropdownMenuItem
                onSelect={() => void runVocabAction(t, () => handlers.onDisable(value))}
              >
                {t('disable')}
              </DropdownMenuItem>
```

In `frontend/components/vocab/part-type-select.tsx`, extend the import: `import { runVocabAction, type VocabEntryHandlers } from './vocab-managed-chip';`. Replace the disable menu item:

```tsx
            <DropdownMenuItem
              onSelect={() => void runVocabAction(vm, () => entryHandlers.onDisable(selected.value))}
            >
              {vm('disable')}
            </DropdownMenuItem>
```

Replace the rename-save `onClick`:

```tsx
              <Button
                onClick={async () => {
                  const next = draft.trim();
                  if (!next || !selected) return;
                  if (await runVocabAction(vm, () => entryHandlers.onRename(selected.value, next))) {
                    setRenameOpen(false);
                  }
                }}
              >
                {vm('save')}
              </Button>
```

i18n — add under `vocabManage` in both `frontend/messages/en/wardrobe.json` and `frontend/messages/zh-CN/wardrobe.json`:
- en: `"actionFailed": "Something went wrong. Please try again."`
- zh-CN: `"actionFailed": "操作失败，请重试。"`

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec frontend npm test -- --run tests/vocab-action-errors.test.ts tests/use-vocabulary.test.tsx tests/item-edit-form.test.tsx && docker compose exec frontend npx tsc --noEmit && docker compose exec frontend npm run i18n:check`
Expected: PASS, tsc clean, i18n green.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/vocab/vocab-managed-chip.tsx frontend/components/vocab/part-type-select.tsx \
  frontend/messages/en/wardrobe.json frontend/messages/zh-CN/wardrobe.json \
  frontend/tests/vocab-action-errors.test.ts
git commit -m "fix(vocab): surface rename/disable failures instead of swallowing them

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: Drop dead code, then run the full verification battery

**Files:**
- Modify: `frontend/components/item-detail-dialog.tsx` (remove `Layers` icon import, `useRouter` import and `const router = useRouter();`)
- Modify: `backend/app/api/analytics.py:15` (remove `count_composition` from the import)

**Interfaces:**
- Consumes: every earlier task's commits — this task is the whole-batch gate.
- Produces: a green tree at the pre-batch baselines plus the new tests (backend > 833, frontend > 205).

- [ ] **Step 1: Verify the dead code is dead**

Run: `grep -n 'router\.\|Layers' frontend/components/item-detail-dialog.tsx && grep -n 'count_composition' backend/app/api/analytics.py`
Expected: only the import/binding lines themselves (no `router.` usage, `Layers` only in the lucide import list, `count_composition` only in the import line). If any real usage appears, stop and report — do not delete used code.

- [ ] **Step 2: Remove the dead code**

In `frontend/components/item-detail-dialog.tsx`:
- delete `  Layers,` from the lucide-react import list (line 23),
- delete the entire line `import { useRouter } from 'next/navigation';` (line 5),
- delete the entire line `  const router = useRouter();` (around line 93).

In `backend/app/api/analytics.py`, replace line 15 with:

```python
from app.utils.clothing import WardrobeComposition, first_primary
```

(`composition_insights` keeps its `WardrobeComposition` annotation — 摘不删, spec §7 — and `_wear_stats` still uses `first_primary`.)

- [ ] **Step 3: Run the full verification battery**

Run each; all must pass:

```bash
docker compose exec backend python -m pytest tests/ -q
docker compose exec frontend npm test -- --run
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run lint
docker compose exec frontend npm run i18n:check
docker compose exec frontend npm run vocab:check
docker compose exec frontend npm test -- --run tests/pruned-entry-guard.test.ts
```

Expected: backend ≥ 833 passed with the new tests included; frontend ≥ 205 passed with the new tests included; tsc/lint/i18n/vocab/pruned-entry-guard all green.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/item-detail-dialog.tsx backend/app/api/analytics.py
git commit -m "chore: drop the dead Layers/useRouter/count_composition leftovers

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## After the plan

Run the targeted re-review (定点复核) over the fix commits (the 10 task commits above), same as the previous rounds: one scoped review pass over the batch diff, then fix any new findings it surfaces.
