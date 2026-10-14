import json
from datetime import date
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.services.weather_service import DayWeather

BASE = "/api/v1/records"
DAY_WEATHER = "app.services.weather_service.WeatherService.get_weather_for_date"


def _jpeg(size=(64, 48)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


async def _record(client, headers, n=1) -> dict:
    files = [("photos", (f"p{i}.jpg", _jpeg(), "image/jpeg")) for i in range(n)]
    r = await client.post(BASE, data={"data": "{}"}, files=files, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_add_photo_appends_position(client, auth_headers):
    rec = await _record(client, auth_headers)
    r = await client.post(
        f"{BASE}/{rec['id']}/photos",
        files={"photo": ("x.jpg", _jpeg(), "image/jpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert [p["position"] for p in r.json()["photos"]] == [0, 1]


@pytest.mark.asyncio
async def test_delete_photo_renumbers(client, auth_headers):
    rec = await _record(client, auth_headers, n=3)
    first = rec["photos"][0]["id"]
    r = await client.delete(f"{BASE}/{rec['id']}/photos/{first}", headers=auth_headers)
    assert r.status_code == 200
    photos = r.json()["photos"]
    assert [p["position"] for p in photos] == [0, 1]
    assert first not in [p["id"] for p in photos]


@pytest.mark.asyncio
async def test_delete_last_photo_rejected(client, auth_headers):
    rec = await _record(client, auth_headers)
    r = await client.delete(f"{BASE}/{rec['id']}/photos/{rec['photos'][0]['id']}", headers=auth_headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_rotate_photo_on_disk(client, auth_headers, db_session):
    from sqlalchemy import select

    from app.models import OutfitPhoto
    from app.services.image_service import ImageService

    rec = await _record(client, auth_headers)
    pid = rec["photos"][0]["id"]
    r = await client.post(
        f"{BASE}/{rec['id']}/photos/{pid}/rotate", json={"direction": "cw"}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    photo = (
        await db_session.execute(
            select(OutfitPhoto).where(OutfitPhoto.id == pid).execution_options(populate_existing=True)
        )
    ).scalar_one()
    with Image.open(ImageService().get_image_path(photo.image_path)) as im:
        assert im.size == (48, 64)


@pytest.mark.asyncio
async def test_rotate_invalid_direction_422(client, auth_headers):
    rec = await _record(client, auth_headers)
    pid = rec["photos"][0]["id"]
    r = await client.post(f"{BASE}/{rec['id']}/photos/{pid}/rotate", json={"direction": "up"}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_photo_of_other_record_404(client, auth_headers):
    a = await _record(client, auth_headers, n=2)
    b = await _record(client, auth_headers)
    r = await client.delete(f"{BASE}/{b['id']}/photos/{a['photos'][0]['id']}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_weather_lookup_uses_city_coordinates(client, auth_headers):
    mock = AsyncMock(return_value=DayWeather(22.0, 15.0, "cloudy"))
    with patch(DAY_WEATHER, new=mock):
        r = await client.get(f"{BASE}/weather", params={"city": "杭州", "date": "2026-10-10"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"weather": {"temp_high": 22.0, "temp_low": 15.0, "condition": "cloudy"}}
    args = mock.call_args.args
    assert args[0] == pytest.approx(30.2741) and args[1] == pytest.approx(120.1551)
    assert args[2] == date(2026, 10, 10)


@pytest.mark.asyncio
async def test_weather_unknown_city_returns_null(client, auth_headers):
    with patch(DAY_WEATHER, new=AsyncMock()) as mock:
        r = await client.get(f"{BASE}/weather", params={"city": "火星", "date": "2026-10-10"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"weather": None}
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_weather_lookup_unavailable_returns_null(client, auth_headers):
    with patch(DAY_WEATHER, new=AsyncMock(return_value=None)):
        r = await client.get(f"{BASE}/weather", params={"city": "香港", "date": "2020-01-01"}, headers=auth_headers)
    assert r.json() == {"weather": None}
