# Code-Review Findings Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the ten defects a whole-branch code review raised on `docs/personal-wardrobe-spec`, ranked by severity — two data-loss paths first, then correctness gaps in the lifecycle/tag contracts, then UI/i18n polish.

**Architecture:** All fixes are localized corrections to existing files: schema fields the UI already sends, service predicates that must read the authoritative `lifecycle` column, one new migration that normalizes legacy `purchase_date` rows, lazy vocabulary loading so runtime writes reach running processes, and two frontend vocab-dialog repairs. Every task is test-first with a failing pin before the code change.

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Alembic + Pydantic v2 (backend); Next.js 14 App Router + React 18 + TanStack Query v5 (frontend). Tests run only in containers.

**Spec:** `docs/specs/personal-wardrobe-spec.md` (esp. §5 status three-state, §10.16 three-tier analytics) + `docs/specs/vocabulary.md`

## Global Constraints

- Tests run ONLY in containers: `docker compose exec backend python -m pytest tests/ -q`, `docker compose exec frontend npm test -- --run`, `docker compose exec frontend npx tsc --noEmit`, `npm run lint`, `npm run i18n:check`, `npm run vocab:check`, plus `tests/pruned-entry-guard.test.ts`. Host npm 9 misreads the npm-11 lockfile — never run frontend tooling on the host.
- Backend suite note: the suite has an autouse session flock (`WARDROBE_TEST_LOCK`, see `backend/tests/conftest.py`); a second concurrent run queues instead of racing. Historical intermittent flakes are documented in memory `backend-suite-intermittent-flakes` — judge a failure only after single-test re-run + one full re-run.
- i18n: en is the key source; parity gate covers zh-CN only; de/fr/it/ja/ko/zh-TW are frozen — new keys go in en + zh-CN only.
- `lifecycle` ('active'/'idle'/'retired') is authoritative (spec §5/§10.16); `is_archived` is a computed compat view AND the retired compat input on create/PATCH. A desynced boolean must never hide a row.
- Vocabulary JSON (`backend/app/data/garment_vocabulary.json`) is runtime-mutable via `POST /vocabulary/*`; migrations must stay reproducible from their own contents (never read the live vocabulary at migration load).
- Commits end with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- The plan document `docs/superpowers/plans/*.md` stays UNTRACKED (user decision) — never `git add` it.
- Security red line: never solicit admin/superuser credentials; the only account is the repo's public low-privilege `wardrobe` default.

## Review Focus

- A filter the UI sends but the API schema silently drops must not widen a destructive bulk action (Task 1 pins select-all delete under `favorite`/`needs_wash` filters).
- A pre-branch `purchase_date` with a real day must not lose that day silently on first save (Task 2 pins the migration normalization + marker).
- A desynced `is_archived` boolean must never hide a row from dedup/counts (Task 3 pins `find_duplicate_by_hash` against a drifted row).
- Explicitly-null tag keys are part of the AI blob contract and must survive a detail-dialog save (Task 4 pins `{"brand": null, …}` round-trip).
- An item whose only color lives in `secondary_colors` must still contribute that color to AI prompts (Task 5 pins secondary-only formatting in both services).

---

### Task 1: Bulk filters must honor favorite/needs_wash (data loss)

**Files:**
- Modify: `backend/app/schemas/item.py:339-343` (BulkFilters)
- Modify: `backend/app/services/item_service.py:142-152` (get_ids_by_filter signature + predicates)
- Modify: `backend/app/api/items.py:108-116` (_resolve_bulk_item_ids call)
- Test: `backend/tests/test_items.py` (new `TestBulkFilters` class, or extend bulk tests near line 843)

**Interfaces:**
- Consumes: `ItemFilter.favorite`/`needs_wash` semantics from `get_list` (`item_service.py:79-80,102-103`) — same predicate shape.
- Produces: `BulkFilters.favorite: bool | None`, `BulkFilters.needs_wash: bool | None`; `ItemService.get_ids_by_filter(..., favorite: bool | None = None, needs_wash: bool | None = None)`.

The wardrobe UI (`frontend/app/dashboard/wardrobe/page.tsx:557-564`) already sends `favorite` and `needs_wash` in `getBulkParams` and `BulkOperationParams` (`use-items.ts:633-637`) declares them, but `BulkFilters` names neither field — Pydantic drops them and `_resolve_bulk_item_ids` builds the id set with no favorite/needs_wash predicate. Select-all bulk delete then covers every item matching the remaining filters, not the filtered selection on screen.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_items.py` (class `TestBulkFilters`):

```python
class TestBulkFilters:
    """Bulk select_all must honor every filter the UI sends.

    BulkFilters silently dropped favorite/needs_wash: select-all delete then
    matched far more items than the filtered selection on screen (e.g. every
    wardrobe row, not the three favorites).
    """

    @pytest.mark.asyncio
    async def test_select_all_delete_honors_favorite_filter(self, client: AsyncClient, auth_headers, db_session):
        # one favorite + one non-favorite item (distinct image seeds: identical
        # bytes collide under phash and the second create 409s as a duplicate)
        for name, fav, seed in (("fav shirt", True, 1), ("plain shirt", False, 2)):
            created = await client.post(
                "/api/v1/items",
                files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(seed), "image/jpeg")},
                data={"type": "shirt", "name": name, "skip_ai": "true", "favorite": str(fav).lower()},
                headers=auth_headers,
            )
            assert created.status_code in (200, 201), created.text

        deleted = await client.post(
            "/api/v1/items/bulk/delete",
            json={"select_all": True, "filters": {"favorite": True}},
            headers=auth_headers,
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted"] == 1

        remaining = await client.get("/api/v1/items", headers=auth_headers)
        names = {i["name"] for i in remaining.json()["items"]}
        assert names == {"plain shirt"}

    @pytest.mark.asyncio
    async def test_select_all_delete_honors_needs_wash_filter(self, client: AsyncClient, auth_headers, db_session):
        kept = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(3), "image/jpeg")},
            data={"type": "shirt", "name": "clean shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        assert kept.status_code in (200, 201), kept.text
        # the other item is needs_wash=True (set directly; no public toggle)
        dirty = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(4), "image/jpeg")},
            data={"type": "shirt", "name": "dirty shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        assert dirty.status_code in (200, 201), dirty.text
        item_id = dirty.json()["id"]
        await db_session.execute(
            update(ClothingItem).where(ClothingItem.id == item_id).values(needs_wash=True)
        )
        await db_session.commit()

        deleted = await client.post(
            "/api/v1/items/bulk/delete",
            json={"select_all": True, "filters": {"needs_wash": True}},
            headers=auth_headers,
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted"] == 1

        remaining = await client.get("/api/v1/items", headers=auth_headers)
        assert {i["name"] for i in remaining.json()["items"]} == {"clean shirt"}
```

(Ensure `from sqlalchemy import update` is imported in the test module header; `uuid4` and `_make_test_image_bytes` already exist in that file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestBulkFilters -q`
Expected: FAIL — `deleted` is 2 (both rows) instead of 1, or 422/KeyError proving the filter keys are dropped.

- [ ] **Step 3: Write minimal implementation**

`backend/app/schemas/item.py` — extend BulkFilters:

```python
class BulkFilters(BaseModel):
    type: str | None = None
    search: str | None = None
    is_archived: bool | None = None
    lifecycle: Literal["active", "idle", "retired"] | None = None
    # Sent by the wardrobe UI's select-all bulk actions; dropping either one
    # widens a destructive action past the filter the user sees on screen.
    favorite: bool | None = None
    needs_wash: bool | None = None
```

`backend/app/services/item_service.py` — extend `get_ids_by_filter` signature and add the two predicates beside the existing type filter:

```python
    async def get_ids_by_filter(
        self,
        user_id: UUID,
        type_filter: str | None = None,
        search: str | None = None,
        is_archived: bool = False,
        lifecycle: str | None = None,
        favorite: bool | None = None,
        needs_wash: bool | None = None,
        excluded_ids: list[UUID] | None = None,
        after_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[UUID]:
        query = select(ClothingItem.id).where(ClothingItem.user_id == user_id)

        if type_filter:
            query = query.where(ClothingItem.type == type_filter)

        if favorite is not None:
            query = query.where(ClothingItem.favorite == favorite)
        if needs_wash is not None:
            query = query.where(ClothingItem.needs_wash == needs_wash)
```

(rest of the method unchanged)

`backend/app/api/items.py` — pass the filters through in `_resolve_bulk_item_ids`:

```python
    item_ids = await item_service.get_ids_by_filter(
        user_id=user_id,
        type_filter=filters.type if filters else None,
        search=filters.search if filters else None,
        is_archived=filters.is_archived if filters and filters.is_archived is not None else False,
        lifecycle=filters.lifecycle if filters else None,
        favorite=filters.favorite if filters else None,
        needs_wash=filters.needs_wash if filters else None,
        excluded_ids=list(request.excluded_ids) if request.excluded_ids else None,
        after_id=request.after_id,
        limit=limit + 1,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestBulkFilters -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the bulk neighbors for regressions**

Run: `docker compose exec backend python -m pytest tests/test_bulk_action_limits.py tests/test_items.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/item.py backend/app/services/item_service.py backend/app/api/items.py backend/tests/test_items.py
git commit -m "fix(bulk): honor favorite/needs_wash in select-all bulk actions" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Migrate legacy purchase_date rows to day 1 with a precision marker (data loss)

**Files:**
- Modify: `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py:115-145` (upgrade data step)
- Test: `backend/tests/test_color_migration.py` (extend, or new `backend/tests/test_purchase_date_migration.py`)

**Interfaces:**
- Consumes: `parse_purchase_date` contract in `item_service.py:16-27` (both wire forms persist as day 1; marker records the user's real precision).
- Produces: every non-null `purchase_date` row has `EXTRACT(DAY) = 1` and a non-null `purchase_date_precision` immediately after upgrade.

The migration adds `purchase_date_precision` but never normalizes pre-existing rows. Old rows hold full dates (old schema was a plain `Date`), while `ItemResponse._format_purchase_date` (`schemas/item.py:137-146`) renders "%Y-%m" and `parse_purchase_date` writes back day 1 — so the day component is silently destroyed on the first detail-dialog save with no marker recording the loss. Normalizing in the migration makes the loss deterministic and recorded instead of lazy and silent.

- [ ] **Step 1: Write the failing test**

Add `backend/tests/test_purchase_date_migration.py`. It loads the migration module with `importlib` (the same pattern `test_color_migration.py` uses for its load-chain probe) and executes the migration's **own** statement constant against a seeded legacy row — so the test pins the shipped SQL, not a copy:

```python
"""Legacy purchase_date rows must be normalized at migration time.

The old schema stored a plain Date (users entered full days). The new wire
format is year-month only, so the day is dropped — the migration must do that
once, deterministically, and record the loss in purchase_date_precision,
instead of the first unrelated save silently rewriting the row.
"""
import importlib.util
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "e7f8a9b0c1d2_personal_wardrobe_fields.py"
    )
    spec = importlib.util.spec_from_file_location("e7f8a9b0c1d2_normalize_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_legacy_full_dates_come_out_as_day_one_with_marker(db_session: AsyncSession, test_user):
    from app.models.item import ClothingItem

    item = ClothingItem(
        id=uuid4(), user_id=test_user.id, type="shirt", image_path="t.jpg",
        purchase_date=date(2024, 3, 15),  # legacy full date, no marker
    )
    db_session.add(item)
    await db_session.flush()

    module = _migration_module()
    await db_session.execute(text(module.NORMALIZE_PURCHASE_DATE_SQL))
    await db_session.flush()
    await db_session.refresh(item)

    assert item.purchase_date == date(2024, 3, 1)
    assert item.purchase_date_precision == "month"


@pytest.mark.asyncio
async def test_rows_with_marker_are_untouched(db_session: AsyncSession, test_user):
    from app.models.item import ClothingItem

    item = ClothingItem(
        id=uuid4(), user_id=test_user.id, type="shirt", image_path="t.jpg",
        purchase_date=date(2024, 1, 1), purchase_date_precision="year",
    )
    db_session.add(item)
    await db_session.flush()

    module = _migration_module()
    await db_session.execute(text(module.NORMALIZE_PURCHASE_DATE_SQL))
    await db_session.flush()
    await db_session.refresh(item)

    assert item.purchase_date == date(2024, 1, 1)
    assert item.purchase_date_precision == "year"


def test_migration_ships_the_normalization_in_its_own_contents():
    # Reproducibility rule: the migration carries the statement itself, with
    # no runtime-vocabulary or app-side repair dependency.
    module = _migration_module()
    assert hasattr(module, "NORMALIZE_PURCHASE_DATE_SQL")
    assert "date_trunc('month', purchase_date)" in module.NORMALIZE_PURCHASE_DATE_SQL
    assert "purchase_date_precision = 'month'" in module.NORMALIZE_PURCHASE_DATE_SQL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_purchase_date_migration.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'NORMALIZE_PURCHASE_DATE_SQL'` (all three tests).

- [ ] **Step 3: Write minimal implementation**

In `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py`, at module level next to the frozen snapshots, add:

```python
# 旧数据是完整日期（老 schema 是裸 Date），新线格式只有年-月。日成分在这里
# 一次性丢掉并记录 precision='month'，而不是等到某次无关保存静默改写行。
# 已带 precision 的行不动。
NORMALIZE_PURCHASE_DATE_SQL = (
    "UPDATE clothing_items SET purchase_date = date_trunc('month', purchase_date)::date, "
    "purchase_date_precision = 'month' "
    "WHERE purchase_date IS NOT NULL AND purchase_date_precision IS NULL"
)
```

and inside `upgrade()`, immediately after the `op.add_column(... "purchase_date_precision" ...)` block and before the color data migration loop:

```python
    op.execute(sa.text(NORMALIZE_PURCHASE_DATE_SQL))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_purchase_date_migration.py tests/test_color_migration.py tests/test_items.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py backend/tests/test_purchase_date_migration.py
git commit -m "fix(db): normalize legacy purchase_date rows at migration time" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Dedup and ready-count must read lifecycle, not the boolean

**Files:**
- Modify: `backend/app/services/item_service.py:42-54` (get_ready_item_count) and `:193-210` (find_duplicate_by_hash)
- Test: `backend/tests/test_items.py` (extend)

**Interfaces:**
- Consumes: `get_list`'s lifecycle authority clause (`item_service.py:88-96`).
- Produces: same signatures; predicates change to `ClothingItem.lifecycle != "retired"`.

`find_duplicate_by_hash` and `get_ready_item_count` still filter `is_archived.is_(False)` while listing uses `lifecycle != 'retired'`. When the boolean drifts (older tooling writing the column directly, partial restores), an item becomes a hidden "duplicate" of a row the list doesn't show, or a visible item is ignored as archived — exactly the rows this branch's migration was meant to reconcile.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_items.py`:

```python
class TestLifecycleAuthorityInQueries:
    """lifecycle is the authority; a desynced boolean must not hide a row."""

(Reuse `update` from sqlalchemy in the test module header — Task 1 already added it to this file; add `update` to the `from sqlalchemy import …` line if running this task standalone.)

    @pytest.mark.asyncio
    async def test_duplicate_lookup_ignores_a_drifted_boolean(self, client: AsyncClient, auth_headers, test_user, db_session):
        created = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(), "image/jpeg")},
            data={"type": "shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        assert created.status_code in (200, 201), created.text
        item_id = created.json()["id"]

        from app.services.item_service import ItemService
        svc = ItemService(db_session)

        # Pin a known hash and desync the boolean behind the service layer's
        # back: is_archived=True while lifecycle stays 'active'.
        await db_session.execute(
            update(ClothingItem)
            .where(ClothingItem.id == item_id)
            .values(image_hash="drift-test-hash", is_archived=True)
        )
        await db_session.commit()

        found = await svc.find_duplicate_by_hash(test_user.id, "drift-test-hash")
        assert found is not None and found.id == item_id

    @pytest.mark.asyncio
    async def test_ready_count_ignores_a_drifted_boolean(self, client: AsyncClient, auth_headers, test_user, db_session):
        created = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(), "image/jpeg")},
            data={"type": "shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        assert created.status_code in (200, 201), created.text
        item_id = created.json()["id"]

        from app.services.item_service import ItemService
        svc = ItemService(db_session)

        before = await svc.get_ready_item_count(test_user.id)
        await db_session.execute(
            update(ClothingItem).where(ClothingItem.id == item_id).values(is_archived=True)
        )
        await db_session.commit()
        after = await svc.get_ready_item_count(test_user.id)
        assert after == before  # drifted boolean hides nothing

        # and a really-retired row does leave the count
        await db_session.execute(
            update(ClothingItem)
            .where(ClothingItem.id == item_id)
            .values(lifecycle="retired", is_archived=False)  # drift the other way
        )
        await db_session.commit()
        assert await svc.get_ready_item_count(test_user.id) == before - 1
```

(Reuse `update` from sqlalchemy in the test module header.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestLifecycleAuthorityInQueries -q`
Expected: FAIL — count drops when only the boolean flips.

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/item_service.py` — in `get_ready_item_count` replace `ClothingItem.is_archived.is_(False),` with:

```python
                    # lifecycle is the authority (spec §5); the boolean is only
                    # a compat view and may drift.
                    ClothingItem.lifecycle != "retired",
```

and in `find_duplicate_by_hash` replace `ClothingItem.is_archived.is_(False),` with the same clause.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestLifecycleAuthorityInQueries -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/item_service.py backend/tests/test_items.py
git commit -m "fix(items): read lifecycle in dedup and ready-count queries" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Tag round-trip must keep explicitly-null keys

**Files:**
- Modify: `backend/app/services/item_service.py:287-292` (update tags rewrite) and `:240-242` (create exclude_none)
- Test: `backend/tests/test_items.py` (`TestTagsRoundTrip`, around line 2137)

**Interfaces:**
- Consumes: `ItemTags` extra="allow" contract (`schemas/item.py:20-44`).
- Produces: unchanged shapes; null-valued keys survive create + PATCH round-trips.

`update()` rewrites the tags dict with `if v is not None`, so a detail-dialog save drops AI-blob keys that carry null (`{"primary_color": null, "brand": null, "fit": null}`) instead of preserving them like the undeclared keys pinned earlier. `create()`'s `exclude_none=True` has the same shape.

- [ ] **Step 1: Write the failing test**

Append to `TestTagsRoundTrip` in `backend/tests/test_items.py`:

```python
    @pytest.mark.asyncio
    async def test_update_preserves_null_valued_tag_keys(self, client: AsyncClient, auth_headers):
        # AI answers "unknown" as an explicit null. The blob's key presence is
        # load-bearing for the AI panel, so a rename save must not drop it.
        create = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(), "image/jpeg")},
            data={"type": "shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        assert create.status_code in (200, 201), create.text
        item_id = create.json()["id"]

        patched = await client.patch(
            f"/api/v1/items/{item_id}",
            json={
                "name": "renamed",
                "tags": {"primary_color": None, "brand": None, "fit": None, "colors": ["blue"]},
            },
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
        tags = patched.json()["tags"]
        assert tags["primary_color"] is None
        assert tags["brand"] is None
        assert tags["fit"] is None
        assert tags["colors"] == ["blue"]

        # and the second save still sees the same keys
        again = await client.patch(
            f"/api/v1/items/{item_id}",
            json={"tags": {**tags}},
            headers=auth_headers,
        )
        assert again.json()["tags"]["brand"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestTagsRoundTrip -q`
Expected: new test FAILS — `tags["brand"]` raises KeyError (key stripped).

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/item_service.py` — two edits, one contract: **store exactly the keys the client sent, explicit nulls included**.

In `create()`, replace the tags build:

```python
        tags = {}
        if item_data.tags:
            # Round-trip contract: keep every key the client sent, explicit
            # nulls included (AI "unknown" answers) — exclude_unset keeps
            # only what arrived, so unset defaults don't get materialized
            # and nothing that arrived gets dropped.
            tags = item_data.tags.model_dump(exclude_unset=True)
```

In `update()`, replace the dict-comprehension filter (the `if v is not None` line):

```python
        if "tags" in update_data and update_data["tags"]:
            tags = update_data["tags"]
            if isinstance(tags, dict):
                # Keep explicitly-null keys: the AI blob's key presence is
                # load-bearing (primary_color in tag_data etc.), and a
                # detail-dialog save round-trips the whole blob. The parent
                # dump is already exclude_unset, so this dict is exactly
                # what the client sent.
                update_data["tags"] = dict(tags)
            else:
                update_data["tags"] = tags.model_dump(exclude_unset=True)
```

Then make the tags→column projection **value-aware** so preserved nulls don't
change column semantics (this projection is itself a consumer keying on key
presence — the shape change must not turn `"pattern": null` into a column
wipe). In the same function:
- the per-column loop becomes `if tag_data.get(column) is not None: setattr(item, column, tag_data[column])` (empty lists still project; explicit nulls leave the column alone, as before),
- the color projection guard becomes `if tag_data.get("primary_color") is not None or tag_data.get("colors") is not None:` so a blob carrying only null color keys no longer fires the splitter with two Nones and clears the columns.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestTagsRoundTrip tests/test_item_tagging.py -q`
Expected: PASS (all pre-existing tags tests keep passing)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/item_service.py backend/tests/test_items.py
git commit -m "fix(items): keep explicitly-null tag keys through create and update" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Prompt color formatters must use the full color list

**Files:**
- Modify: `backend/app/services/recommendation_service.py:250-256`
- Modify: `backend/app/services/pairing_service.py:74-83`
- Test: `backend/tests/test_recommendation_service.py` (`TestFormatItemsEnriched`) and `backend/tests/test_pairings.py` (`TestFormatItemDescription`)

**Interfaces:**
- Consumes: `first_primary` (`app/utils/clothing.py:11`), `ClothingItem.primary_colors`/`secondary_colors`.
- Produces: unchanged `_format_items_for_prompt` / `_format_item_description` signatures.

Both formatters skip the single-color branch unless the primary list is non-empty, so an item whose only color is secondary contributes no color at all.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_pairings.py`, `TestFormatItemDescription`:

```python
    def test_secondary_only_item_still_shows_its_color(self):
        from app.services.pairing_service import PairingService

        item = _make_item(uuid4(), primary_colors=[], secondary_colors=["wine"])
        text = PairingService(None)._format_item_description(item)
        assert "wine" in text
```

In `backend/tests/test_recommendation_service.py`, `TestFormatItemsEnriched`:

```python
    def test_secondary_only_item_still_shows_its_color(self):
        service = RecommendationService.__new__(RecommendationService)
        item = _make_item(primary_colors=[], secondary_colors=["wine"])
        scored = [ScoredItem(item=item)]

        text, _ = service._format_items_for_prompt(scored, {}, date(2026, 3, 8))
        assert "wine" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_pairings.py::TestFormatItemDescription tests/test_recommendation_service.py::TestFormatItemsEnriched -q`
Expected: both new tests FAIL (no "wine" in text).

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/recommendation_service.py` — replace the color block with:

```python
            # `or []`: freshly built items carry None array columns until
            # INSERT (same guard as pairing_service's formatter).
            all_colors = (item.primary_colors or []) + (item.secondary_colors or [])
            if all_colors and len(all_colors) > 1:
                parts.append(f"colors: {', '.join(all_colors)}")
            elif all_colors:
                # A single color may live in secondary_colors only.
                parts.append(first_primary(all_colors))
```

`backend/app/services/pairing_service.py` — replace its color block with:

```python
        # Colors (primary + secondary; the prompt wants every color on the item).
        # `or []` keeps the formatter total for freshly built items whose array
        # columns only get their default at INSERT.
        colors = list(dict.fromkeys([*(item.primary_colors or []), *(item.secondary_colors or [])]))
        if len(colors) > 1:
            parts.append(f"colors: {', '.join(colors)}")
        elif colors:
            # A single color may live in secondary_colors only.
            parts.append(first_primary(colors))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_pairings.py tests/test_recommendation_service.py -q`
Expected: PASS (existing single-color-is-a-bare-name pin still passes)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/app/services/pairing_service.py backend/tests/test_pairings.py backend/tests/test_recommendation_service.py
git commit -m "fix(prompts): never drop a secondary-only color from item lines" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: Un-retiring an item must clear archive_reason

**Files:**
- Modify: `backend/app/services/item_service.py:320-330` (update() crossing block)
- Test: `backend/tests/test_items.py` (extend)

**Interfaces:**
- Consumes: `restore()` invariant at `item_service.py:518-526` (clears `archive_reason`).
- Produces: PATCH retirement-crossing side effects clear `archived_at`, `archive_reason`, reset `status`.

PATCH `{"is_archived": false}` or `{"lifecycle": "active"}` on a retired item clears `archived_at` and resets status but leaves `archive_reason` populated — unlike the dedicated `restore()` path.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_items.py`:

```python
class TestUnretireClearsReason:
    @pytest.mark.asyncio
    async def test_patch_active_clears_archive_reason(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(), "image/jpeg")},
            data={"type": "shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        item_id = create.json()["id"]

        retired = await client.patch(
            f"/api/v1/items/{item_id}",
            json={"lifecycle": "retired", "archive_reason": "donated"},
            headers=auth_headers,
        )
        assert retired.status_code == 200, retired.text
        assert retired.json()["archive_reason"] == "donated"

        unretired = await client.patch(
            f"/api/v1/items/{item_id}",
            json={"lifecycle": "active"},
            headers=auth_headers,
        )
        assert unretired.status_code == 200, unretired.text
        body = unretired.json()
        assert body["archive_reason"] is None
        assert body["lifecycle"] == "active"
        assert body["is_archived"] is False

    @pytest.mark.asyncio
    async def test_patch_is_archived_false_clears_archive_reason(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/items",
            files={"image": (f"{uuid4()}.jpg", _make_test_image_bytes(), "image/jpeg")},
            data={"type": "shirt", "skip_ai": "true"},
            headers=auth_headers,
        )
        item_id = create.json()["id"]

        await client.patch(
            f"/api/v1/items/{item_id}",
            json={"is_archived": True, "archive_reason": "donated"},
            headers=auth_headers,
        )
        unretired = await client.patch(
            f"/api/v1/items/{item_id}",
            json={"is_archived": False},
            headers=auth_headers,
        )
        assert unretired.status_code == 200, unretired.text
        assert unretired.json()["archive_reason"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestUnretireClearsReason -q`
Expected: FAIL — `archive_reason == "donated"` after un-retire.

- [ ] **Step 3: Write minimal implementation**

In `item_service.update()`'s crossing block, extend the un-retire branch:

```python
            elif was_retired and not now_retired:
                update_data["archived_at"] = None
                update_data["status"] = ItemStatus.ready
                # Same invariant as restore(): the reason belongs to the
                # retired period and must not survive into the active row.
                update_data["archive_reason"] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestUnretireClearsReason -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/item_service.py backend/tests/test_items.py
git commit -m "fix(items): clear archive_reason when a retired item comes back" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Runtime vocabulary writes must reach running processes

**Files:**
- Modify: `backend/app/utils/garment_vocabulary.py` (lazy load)
- Modify: `backend/app/services/ai_service.py:17-24,68-90` (VALID_* / TAGGING_PROMPT must not be import-time snapshots)
- Modify: `backend/app/workers/tagging.py:16,125` (BODY_PART_BY_TYPE lookup at call time)
- Test: `backend/tests/test_vocabulary_api.py` (extend) and/or `backend/tests/test_garment_vocabulary.py`

**Interfaces:**
- Consumes: the vocabulary file as sole data source; `POST /vocabulary/*` write path (`api/vocabulary.py:_save`).
- Produces: same public names (`TYPES`, `COLOR_VALUE_SET`, `BODY_PART_BY_TYPE`, `STYLE_VALUES`, `render_tagging_prompt`, …) but resolved at access time from a cached re-read (mtime-keyed), so any process sees writes without restart.

`_DATA` is loaded once at import and exported as frozen constants, so entries added via `POST /vocabulary/*` are rejected by AI validation/tagging until every process is restarted — and nothing documents that. The fix: cache the parse keyed on file mtime; derive names through module `__getattr__` (PEP 562) so existing `from … import TYPES` snapshots only at *first use of that name in that module*, and move ai_service's derivations to call sites.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_vocabulary_api.py` (uses the existing `vocab_snapshot` fixture; `_parse_tags_from_response` takes no `self` state, so the test constructs `AIService()` exactly as `test_ai_service.py` does):

```python
    @pytest.mark.asyncio
    async def test_add_color_reaches_validation_without_restart(self, client, auth_headers, vocab_snapshot):
        """A soft-vocab write must be visible to the validation sets at once.

        _DATA was a load-time snapshot: the API accepted the new color while
        ai_service's VALID_COLORS kept rejecting it until a process restart.
        """
        resp = await client.post(
            "/api/v1/vocabulary/colors/values",
            json={"value": "haze", "label": "雾色", "family": "blue", "hex": "#8fa9bf"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text

        from app.services.ai_service import AIService
        tags = AIService()._parse_tags_from_response(
            '{"type": "shirt", "primary_color": "haze", "colors": ["haze"]}'
        )
        assert tags.primary_color == "haze"
        assert tags.colors == ["haze"]

    @pytest.mark.asyncio
    async def test_add_type_reaches_prompt_and_body_part_map(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/types",
            json={"value": "hoodie-dress", "label": "卫衣裙", "body_part": "dresses"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text

        from app.utils.garment_vocabulary import BODY_PART_BY_TYPE, render_tagging_prompt
        assert BODY_PART_BY_TYPE.get("hoodie-dress") == "dresses"
        assert "hoodie-dress" in render_tagging_prompt("<<TYPES>>")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_vocabulary_api.py -q`
Expected: new tests FAIL — `haze` maps to None (validation stale, `tags.primary_color is None`) / `BODY_PART_BY_TYPE.get("hoodie-dress")` is None.

- [ ] **Step 3: Write minimal implementation**

`backend/app/utils/garment_vocabulary.py` — replace the eager `_DATA = json.loads(...)` and the derived-name assignments with an mtime-cached reader plus a module `__getattr__` that derives each name on access. Every expression moves verbatim; only *when* it runs changes:

```python
import json
from functools import lru_cache
from pathlib import Path

VOCABULARY_PATH = Path(__file__).parent.parent / "data" / "garment_vocabulary.json"


@lru_cache(maxsize=8)
def _data_at(mtime_ns: int) -> dict:
    # Keyed on mtime so a soft-vocabulary write is picked up by every
    # process (API + arq worker) at its next access — the file is the sole
    # source of truth and is runtime-mutable (see app.api.vocabulary).
    return json.loads(VOCABULARY_PATH.read_text())


def _data() -> dict:
    return _data_at(VOCABULARY_PATH.stat().st_mtime_ns)


# Single source for both the runtime API and the compiler — the
# pre-seeded fallback types in accessories/jewelry keep (accessory, 3).
ROLE_BY_PART: dict[str, str] = {
    "tops": "base_top", "bottoms": "bottom", "dresses": "full_body",
    "outerwear": "outer_layer", "footwear": "footwear",
    "accessories": "accessory", "jewelry": "accessory",
}
WASH_BY_PART: dict[str, int] = {
    "tops": 2, "bottoms": 4, "dresses": 3, "outerwear": 8,
    "footwear": 15, "accessories": 3, "jewelry": 3,
}


def render_tagging_prompt(template: str) -> str:
    data = _data()
    replacements = {
        "<<TYPES>>": ", ".join(t["value"] for t in data["types"]),
        "<<MATERIALS>>": ", ".join(data["materials"]),
        "<<FORMALITY>>": ", ".join(data["formality"]),
        "<<BODY_PARTS>>": ", ".join(p["value"] for p in data["body_parts"]),
        "<<COLORS>>": ", ".join(c["value"] for c in data["colors"]["values"]),
        "<<STYLES>>": ", ".join(s["value"] for s in data["styles"]),
        "<<SEASONS>>": ", ".join(s["value"] for s in data["seasons"]),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def __getattr__(name: str):
    """Derived vocabulary names, computed on access from the current file.

    The old module ran these comprehensions once at import. The vocabulary is
    runtime-mutable, so access must observe writes without a restart.
    """
    data = _data()
    types = data["types"]
    body_parts = data["body_parts"]
    colors = data["colors"]
    if name == "TYPES":
        return tuple(entry["value"] for entry in types)
    if name == "ITEM_ROLE":
        return {entry["value"]: entry["role"] for entry in types}
    if name == "DEFAULT_WASH_INTERVALS":
        return {entry["value"]: entry["wash_interval"] for entry in types}
    if name == "MATERIALS":
        return tuple(data["materials"])
    if name == "FORMALITY":
        # Ordered from least to most formal; the scorer measures distance along this scale.
        return tuple(data["formality"])
    if name == "BODY_PARTS":
        return tuple(body_parts)
    if name == "BODY_PART_BY_TYPE":
        return {t["value"]: t["body_part"] for t in types}
    if name == "TYPES_BY_PART":
        return {
            part["value"]: tuple(
                t["value"] for t in types if t["body_part"] == part["value"]
            )
            for part in body_parts
        }
    if name == "TYPE_LABELS":
        return {t["value"]: t["label"] for t in types}
    if name == "COLOR_FAMILIES":
        return tuple(colors["families"])
    if name == "COLOR_VALUES":
        return tuple(colors["values"])
    if name == "COLOR_VALUE_SET":
        return {c["value"] for c in colors["values"]}
    if name == "STYLE_VALUES":
        return tuple(s["value"] for s in data["styles"])
    if name == "STYLE_LABELS":
        return {s["value"]: s["label"] for s in data["styles"]}
    if name == "SEASON_VALUES":
        return tuple(s["value"] for s in data["seasons"])
    if name == "SEASON_LABELS":
        return {s["value"]: s["label"] for s in data["seasons"]}
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

Notes for the implementer:
- `ROLE_BY_PART` / `WASH_BY_PART` are static dicts today (not JSON-derived) — they stay ordinary module constants (their comment about runtime additions moves with them).
- `VOCABULARY_PATH`, `render_tagging_prompt`, `_data`, `__getattr__` stay ordinary module attributes. Preserve the original comments verbatim where the code moves (`test_garment_vocabulary.py` asserts on the semantics they document).
- The names must remain importable (`from app.utils.garment_vocabulary import TYPES` works through `__getattr__`), so every existing importer keeps compiling.

`backend/app/services/ai_service.py` — the module-level snapshots must go:
- Remove `VALID_TYPES = set(TYPES)`, `VALID_COLORS = COLOR_VALUE_SET`, `VALID_MATERIALS`, `VALID_FORMALITY`, `VALID_STYLES`, `VALID_SEASONS` and `TAGGING_PROMPT = render_tagging_prompt(...)` and the corresponding `from app.utils.garment_vocabulary import (...)` names (keep `render_tagging_prompt`).
- Inside `_parse_tags_from_response`, resolve at call time (add `from app.utils import garment_vocabulary as gv` at module top):

```python
        # Resolved per call: the vocabulary is runtime-mutable and a soft-vocab
        # write must reach validation without restarting this process.
        valid_types = set(gv.TYPES)
        valid_colors = set(gv.COLOR_VALUE_SET)
        valid_materials = set(gv.MATERIALS)
        valid_formality = set(gv.FORMALITY)
        valid_styles = set(gv.STYLE_VALUES)
        valid_seasons = set(gv.SEASON_VALUES)
```

  and pass those locals into the existing `validate_value`/`validate_list` calls (replacing `VALID_TYPES` → `valid_types`, `VALID_COLORS` → `valid_colors`, etc.).
- At the `analyze_image` system-message site, replace `TAGGING_PROMPT` with `render_tagging_prompt(load_prompt("clothing_analysis"))` computed at call time.
- Keep `VALID_PATTERNS` and `VALID_FIT` as-is (not vocabulary-derived).

`backend/app/workers/tagging.py` — in `tags_to_item_fields` (line 125) read `gv.BODY_PART_BY_TYPE.get(tags.type)` at call time (module top: `from app.utils import garment_vocabulary as gv`), not the from-imported snapshot.

Update `backend/tests/test_garment_vocabulary.py`, which imports `TAGGING_PROMPT`, `VALID_FORMALITY`, `VALID_MATERIALS`, `VALID_TYPES` from ai_service — same public surface, now derived at access:
- `TAGGING_PROMPT` → `render_tagging_prompt(load_prompt("clothing_analysis"))` (import both from their modules; `_prompt_options` keeps working on the rendered string).
- `VALID_TYPES` → `set(gv.TYPES)`, `VALID_MATERIALS` → `set(gv.MATERIALS)`, `VALID_FORMALITY` → `set(gv.FORMALITY)` (import `from app.utils import garment_vocabulary as gv`).
- `test_ai_validation_sets_come_from_the_vocabulary` keeps its assertions unchanged — it compares ai_service's accepted sets to `gv.*`, which is now literally the same call-time source; its remaining value is that the *prompt* still lists exactly those sets.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_vocabulary_api.py tests/test_garment_vocabulary.py tests/test_ai_service.py tests/test_item_tagging.py tests/test_tagging_worker.py -q`
Expected: PASS (plus the two new freshness pins)

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/garment_vocabulary.py backend/app/services/ai_service.py backend/app/workers/tagging.py backend/tests/
git commit -m "fix(vocab): resolve vocabulary at access time, not import time" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Guard body_part_case_sql against quoted slugs

**Files:**
- Modify: `backend/app/utils/color_migration.py:70-82`
- Test: `backend/tests/test_color_migration.py`

**Interfaces:**
- Consumes: nothing new (migration passes a frozen mapping).
- Produces: same signature `body_part_case_sql(type_column, mapping=None) -> str`, but values are passed through SQLAlchemy bind params or strict literal escaping.

The CASE is f-string-interpolated with no escaping; its default path feeds the runtime-mutable vocabulary, so a quoted slug in the live vocab would break or inject into the UPDATE statement.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_color_migration.py`:

```python
def test_body_part_case_sql_survives_quoted_slugs():
    from app.utils.color_migration import body_part_case_sql

    sql = body_part_case_sql("type", mapping={"shirt": "tops", "o'brien": "jewelry"})
    # The quote must be escaped in the literal, not raw — a raw quote is both
    # invalid SQL and an injection vector when the mapping comes from the
    # runtime vocabulary.
    assert "'o''brien'" in sql
    assert "o'brien" not in sql.replace("o''brien", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_color_migration.py -q`
Expected: new test FAILS (raw `o'brien` present).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/utils/color_migration.py`, replace the `branches = ...` f-string with escaped literals (same discipline as `_array_literal` above it):

```python
    branches = " ".join(
        "WHEN {col} = '{value}' THEN '{part}'".format(
            col=type_column,
            value=value.replace("'", "''"),
            part=part.replace("'", "''"),
        )
        for value, part in sorted(mapping.items())
    )
    return f"CASE {branches} ELSE NULL END"
```

and document the invariant in the docstring: "`type_column` is a code-provided identifier; mapping values are quoted with doubled single quotes so runtime-vocabulary slugs can never break out of the literal (same rule as `_array_literal`)."

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_color_migration.py tests/test_purchase_date_migration.py -q`
Expected: PASS (all 20 + 3)

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/color_migration.py backend/tests/test_color_migration.py
git commit -m "fix(db): quote-escape slugs in body_part_case_sql" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: Vocab add-chip copy must not interpolate English kind nouns

**Files:**
- Modify: `frontend/components/vocab/vocab-managed-chip.tsx:143-158` (VocabAddChip)
- Modify: `frontend/components/vocab/part-type-select.tsx:90` (add option)
- Modify: `frontend/components/vocab/color-multi-select.tsx:43`, `frontend/components/vocab/style-multi-select.tsx:42` (call sites)
- Modify: `frontend/messages/en/wardrobe.json`, `frontend/messages/zh-CN/wardrobe.json` (vocabManage/vocabAdd)
- Test: `frontend/tests/vocab-action-errors.test.ts` or a new `frontend/tests/vocab-add-label.test.tsx`

**Interfaces:**
- Consumes: existing `wardrobe.vocabAdd.title.{colors,styles,types}` translations.
- Produces: `VocabAddChip` takes `kind: 'color' | 'style' | 'type'` and renders `wardrobe.vocabAdd.title.<plural>`; no `{kind}` interpolation remains.

`VocabAddChip` interpolates raw English kind nouns into `添加{kind}…`, rendering mixed-language copy on zh-CN (`添加color…`). The `vocabAdd.title.*` keys already carry the proper translations.

- [ ] **Step 1: Write the failing test**

New `frontend/tests/vocab-add-label.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { VocabAddChip } from '@/components/vocab/vocab-managed-chip';

// next-intl is mocked in setup.ts to echo bare keys; interpolation values are
// dropped — so the pin is "which message key is rendered", not the copy.
describe('VocabAddChip label', () => {
  it('renders the vocabulary title message, not a raw kind noun', () => {
    render(<VocabAddChip kind="color" onClick={() => {}} />);
    expect(screen.getByText('title.colors')).toBeInTheDocument();
  });

  it('maps style and type kinds onto their title keys', () => {
    const { unmount } = render(<VocabAddChip kind="style" onClick={() => {}} />);
    expect(screen.getByText('title.styles')).toBeInTheDocument();
    unmount();
    render(<VocabAddChip kind="type" onClick={() => {}} />);
    expect(screen.getByText('title.types')).toBeInTheDocument();
  });
});
```

(If the component keeps namespace `wardrobe.vocabManage`, echo will render `title.colors` only if the implementation calls `useTranslations('wardrobe.vocabAdd')('title.colors')` — the mock echoes the bare key. Adjust the expected string to whatever key the fix settles on; the pin is that no `addEntry`-with-kind call remains.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- --run tests/vocab-add-label.test.tsx`
Expected: FAIL — renders `addEntry` (mock echo of the old message key).

- [ ] **Step 3: Write minimal implementation**

`frontend/components/vocab/vocab-managed-chip.tsx` — change the chip to look up the pre-translated title:

```tsx
/** Trailing chip that opens the add dialog for this picker. */
const TITLE_KEY = {
  color: 'title.colors',
  style: 'title.styles',
  type: 'title.types',
} as const;

export function VocabAddChip({ kind, onClick }: { kind: 'color' | 'style' | 'type'; onClick: () => void }) {
  const t = useTranslations('wardrobe.vocabAdd');
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col items-center rounded-md border border-dashed p-1 text-muted-foreground hover:text-foreground"
    >
      <span className="flex h-6 w-6 items-center justify-center">
        <Plus className="h-4 w-4" />
      </span>
      <span className="text-xs">{t(TITLE_KEY[kind])}</span>
    </button>
  );
}
```

Call sites become `kind="color"` / `kind="style"` (props renamed from `kindLabel`). `part-type-select.tsx:90` replaces `vm('addEntry', { kind: 'type' })` with the `wardrobe.vocabAdd` title lookup for `types` (add `const va = useTranslations('wardrobe.vocabAdd');` there). Then remove the now-unused `addEntry` key from `vocabManage` in both en and zh-CN message files (i18n keys must stay referenced — run `npm run i18n:check`).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- --run tests/vocab-add-label.test.tsx && npm run i18n:check && npm run lint`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/vocab/ frontend/messages/en/wardrobe.json frontend/messages/zh-CN/wardrobe.json frontend/tests/vocab-add-label.test.tsx
git commit -m "fix(i18n): stop interpolating English kind nouns into add-chip copy" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: VocabAddDialog must re-seed selects when reopened

**Files:**
- Modify: `frontend/components/vocab/vocab-add-dialog.tsx:45-55,66-80`
- Test: `frontend/tests/vocab-add-label.test.tsx` (extend) or new `frontend/tests/vocab-add-dialog.test.tsx`

**Interfaces:**
- Consumes: `family` prop (the body part / color family to file under).
- Produces: unchanged props and submit payload; dialog state always agrees with what submit will send.

The dialog seeds `partValue`/`familyValue` from the `family` prop only on mount and on reset-at-close, so reopening it for a different body part preselects the previous one while submit uses the new prop.

- [ ] **Step 1: Write the failing test**

New `frontend/tests/vocab-add-dialog.test.tsx`. The observable bug: state seeds from `family` only at mount, so reopening the mounted dialog for a different body part shows the previous one in the select while submit reads the current prop. Pin both sides (the visible preselect and the submitted payload). The select is only rendered when `family` is absent (`kind === 'types' && !family`), and `SelectValue` shows the `placeholder` prop when its value is empty — the i18n mock echoes keys, so the placeholder reads `bodyPartPlaceholder` and a 'tops' selection reads the generated label `BODY_PART_LABELS.tops`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { VocabAddDialog } from '@/components/vocab/vocab-add-dialog';
import { BODY_PART_LABELS } from '@/lib/generated/garment-vocabulary';

const mutateAsync = vi.hoisted(() => vi.fn()); // vi.mock factories are hoisted above module init
vi.mock('@/lib/hooks/use-vocabulary', () => ({
  useVocabulary: () => ({ data: { colors: { families: [] }, types: [], styles: [] } }),
  useAddStyle: () => ({ mutateAsync, isPending: false }),
  useAddType: () => ({ mutateAsync, isPending: false }),
  useAddColorValue: () => ({ mutateAsync, isPending: false }),
}));

describe('VocabAddDialog body-part preselect', () => {
  it('reseeds the select when the mounted dialog reopens without a family', () => {
    const { rerender } = render(
      <VocabAddDialog kind="types" open onOpenChange={() => {}} family="tops" />,
    );
    // close and reopen with no family prop — the component stays mounted, so
    // only an open-time reseed clears the previous session's choice
    rerender(<VocabAddDialog kind="types" open={false} onOpenChange={() => {}} family="tops" />);
    rerender(<VocabAddDialog kind="types" open onOpenChange={() => {}} family={undefined} />);

    // fresh open must show the placeholder, not the previous dialog's 'tops'
    expect(screen.getByText('bodyPartPlaceholder')).toBeInTheDocument();
    expect(screen.queryByText(BODY_PART_LABELS.tops)).not.toBeInTheDocument();
  });

  it('submits the current family prop after a previous session picked a part', async () => {
    mutateAsync.mockClear();
    const { rerender } = render(
      <VocabAddDialog kind="types" open onOpenChange={() => {}} family="tops" />,
    );
    rerender(<VocabAddDialog kind="types" open={false} onOpenChange={() => {}} family="tops" />);
    rerender(<VocabAddDialog kind="types" open onOpenChange={() => {}} family="footwear" />);

    fireEvent.change(screen.getByLabelText('label'), { target: { value: 'Sneakers' } });
    fireEvent.change(screen.getByLabelText('slug'), { target: { value: 'sneakers' } });
    fireEvent.click(screen.getByText('submit'));

    // display and payload must agree on the new prop, not the stale state
    expect(mutateAsync).toHaveBeenCalledWith({
      value: 'sneakers',
      label: 'Sneakers',
      body_part: 'footwear',
    });
  });
});
```

(`getByLabelText('label')` resolves through the mock's echoed key on `<Label htmlFor="vocab-label">` + `<Input id="vocab-label">`; `getByText('submit')` is the submit button's echoed key. Both mirror how `vocab-action-errors.test.ts` reasons about the i18n mock.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- --run tests/vocab-add-dialog.test.tsx`
Expected: FAIL on the first test — the trigger still shows the previous body part's label (`BODY_PART_LABELS.tops`) instead of the placeholder. (The second test passes before the fix too — it pins the submit-side contract so a later refactor cannot reintroduce the disagreement from the other direction.)

- [ ] **Step 3: Write minimal implementation**

In `vocab-add-dialog.tsx`, derive the two select values from the prop at open time — replace the mount-only seeding:

```tsx
  const [label, setLabel] = useState('');
  const [slug, setSlug] = useState('');
  const [hex, setHex] = useState('#8fa9bf');
  const [familyValue, setFamilyValue] = useState('');
  const [partValue, setPartValue] = useState('');

  // Re-seed every time the dialog opens: the parent's `family` prop changes
  // between opens (body-part switch in the item form), and submit reads the
  // prop while the select shows state — a mount-only seed left the two
  // disagreeing (and the footer Cancel bypasses reset() entirely).
  useEffect(() => {
    if (open) {
      setFamilyValue(family ?? '');
      setPartValue(family ?? '');
    }
  }, [open, family]);
```

Keep `reset()` for label/slug/hex on close and after a successful submit, and drop its two select seeds (the open-time effect is now the authority). Submit logic (`family ?? partValue`) is unchanged. Add `useEffect` to the existing `react` import.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- --run tests/vocab-add-dialog.test.tsx && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/vocab/vocab-add-dialog.tsx frontend/tests/vocab-add-dialog.test.tsx
git commit -m "fix(vocab): reseed add-dialog selects on every open" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Closing battery (after all tasks)

- [ ] `docker compose exec backend python -m pytest tests/ -q` — full backend suite green (850+ expected; if a flake fires, single-run + one full re-run per memory before declaring failure)
- [ ] `docker compose exec frontend npm test -- --run` — full frontend suite green (223+ expected)
- [ ] `docker compose exec frontend npx tsc --noEmit` — TSC_OK
- [ ] `npm run lint`, `npm run i18n:check`, `npm run vocab:check`, `npm test -- --run tests/pruned-entry-guard.test.ts` (frontend dir) — all green
