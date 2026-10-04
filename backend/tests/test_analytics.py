"""GET /api/v1/analytics — the statistics-page contract.

Before these existed nothing hit the endpoint: its color reads still pointed at
the dropped primary_color column and the whole response 500'd (dashboard blank).
Assertions pin the spec §4 keep-list, the dropped AI metrics, and the §10.15
color rule: count by 件次 over primary colors only.
"""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User


def _make_item(user_id, **kwargs) -> ClothingItem:
    return ClothingItem(
        user_id=user_id,
        type="shirt",
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        **kwargs,
    )


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_keep_list_and_dropped_ai_metrics(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user: User
    ):
        db_session.add(
            _make_item(test_user.id, primary_colors=["black"], secondary_colors=["white"], wear_count=3)
        )
        db_session.add(_make_item(test_user.id, primary_colors=["wine"], wear_count=0))
        await db_session.flush()

        resp = await client.get("/api/v1/analytics", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Spec §4 keep-list — nothing else may appear on the wire.
        assert set(data) == {
            "wardrobe",
            "color_distribution",
            "type_distribution",
            "most_worn",
            "least_worn",
            "never_worn",
        }
        # Spec §4 摘-list: AI recommendation metrics are gone from the contract.
        assert "acceptance_rate" not in data["wardrobe"]
        assert "average_rating" not in data["wardrobe"]

        assert data["wardrobe"]["total_items"] == 2
        assert data["wardrobe"]["total_wears"] == 3
        assert data["wardrobe"]["items_by_status"]["ready"] == 2

    @pytest.mark.asyncio
    async def test_color_distribution_counts_件次_over_primaries_only(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user: User
    ):
        # Two primaries: counts once in each. The secondary never counts.
        db_session.add(
            _make_item(test_user.id, primary_colors=["army", "black"], secondary_colors=["white"])
        )
        db_session.add(_make_item(test_user.id, primary_colors=["black"]))
        db_session.add(_make_item(test_user.id, primary_colors=[], secondary_colors=["wine"]))
        await db_session.flush()

        resp = await client.get("/api/v1/analytics", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        counts = {row["color"]: row["count"] for row in resp.json()["color_distribution"]}
        assert counts == {"black": 2, "army": 1}

    @pytest.mark.asyncio
    async def test_rankings_use_first_primary_shape(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user: User
    ):
        worn = _make_item(test_user.id, primary_colors=["army", "black"], wear_count=5)
        unworn = _make_item(test_user.id, primary_colors=["wine"], wear_count=0)
        db_session.add_all([worn, unworn])
        await db_session.flush()

        resp = await client.get("/api/v1/analytics", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert [w["id"] for w in data["most_worn"]] == [str(worn.id)]
        assert [w["id"] for w in data["never_worn"]] == [str(unworn.id)]
        # Legacy singular shape: the lead primary, not the raw list.
        assert data["most_worn"][0]["primary_color"] == "army"
        assert data["never_worn"][0]["primary_color"] == "wine"
