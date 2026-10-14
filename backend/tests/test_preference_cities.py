from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest

from app.services.weather_service import GeocodingServiceError

BASE = "/api/v1/users/me/preferences"
GEOCODE = "app.services.weather_service.WeatherService.geocode_location_name"


@pytest.mark.asyncio
async def test_presets_returned_when_unset(client, auth_headers):
    r = await client.get(BASE, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert [c["name"] for c in body["cities"]] == ["杭州", "香港", "合肥", "深圳"]
    assert body["default_city"] is None


@pytest.mark.asyncio
async def test_set_default_city_must_be_in_list(client, auth_headers):
    ok = await client.patch(BASE, json={"default_city": "杭州"}, headers=auth_headers)
    assert ok.status_code == 200
    assert ok.json()["default_city"] == "杭州"

    bad = await client.patch(BASE, json={"default_city": "火星"}, headers=auth_headers)
    assert bad.status_code == 422

    cleared = await client.patch(BASE, json={"default_city": None}, headers=auth_headers)
    assert cleared.json()["default_city"] is None


@pytest.mark.asyncio
async def test_add_city_geocodes_and_appends(client, auth_headers):
    with patch(GEOCODE, new=AsyncMock(return_value=(31.23, 121.47, "上海市"))):
        r = await client.post(f"{BASE}/cities", json={"name": " 上海 "}, headers=auth_headers)
    assert r.status_code == 200
    cities = r.json()["cities"]
    assert cities[-1] == {"name": "上海", "latitude": 31.23, "longitude": 121.47}
    assert len(cities) == 5


@pytest.mark.asyncio
async def test_add_duplicate_city_409(client, auth_headers):
    r = await client.post(f"{BASE}/cities", json={"name": "杭州"}, headers=auth_headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_add_unknown_city_422(client, auth_headers):
    with patch(GEOCODE, new=AsyncMock(return_value=None)):
        r = await client.post(f"{BASE}/cities", json={"name": "不存在市"}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_add_city_geocoder_down_502(client, auth_headers):
    with patch(GEOCODE, new=AsyncMock(side_effect=GeocodingServiceError("down"))):
        r = await client.post(f"{BASE}/cities", json={"name": "上海"}, headers=auth_headers)
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_delete_city_clears_default(client, auth_headers):
    await client.patch(BASE, json={"default_city": "合肥"}, headers=auth_headers)
    r = await client.delete(f"{BASE}/cities/{quote('合肥')}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "合肥" not in [c["name"] for c in body["cities"]]
    assert body["default_city"] is None


@pytest.mark.asyncio
async def test_delete_missing_city_404(client, auth_headers):
    r = await client.delete(f"{BASE}/cities/{quote('火星')}", headers=auth_headers)
    assert r.status_code == 404
