import json
from io import BytesIO

import pytest
from PIL import Image

RECORDS = "/api/v1/records"
OUTFITS = "/api/v1/outfits"


async def _create_record(client, headers) -> str:
    buf = BytesIO()
    Image.new("RGB", (64, 48), (200, 100, 50)).save(buf, format="JPEG")
    r = await client.post(
        RECORDS,
        data={"data": json.dumps({"date": "2026-10-01"})},
        files=[("photos", ("p.jpg", buf.getvalue(), "image/jpeg"))],
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_list_excludes_records(client, auth_headers):
    rid = await _create_record(client, auth_headers)
    for params in ({}, {"status": "accepted"}, {"is_lookbook": "false"}):
        r = await client.get(OUTFITS, params=params, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert rid not in {o["id"] for o in r.json()["outfits"]}


@pytest.mark.asyncio
async def test_by_id_routes_404_for_records(client, auth_headers):
    rid = await _create_record(client, auth_headers)
    assert (await client.get(f"{OUTFITS}/{rid}", headers=auth_headers)).status_code == 404
    assert (await client.delete(f"{OUTFITS}/{rid}", headers=auth_headers)).status_code == 404
    assert (
        await client.patch(f"{OUTFITS}/{rid}", json={"name": "x"}, headers=auth_headers)
    ).status_code == 404
    assert (await client.post(f"{OUTFITS}/{rid}/accept", headers=auth_headers)).status_code == 404
    assert (
        await client.post(f"{OUTFITS}/{rid}/clone-to-lookbook", json={}, headers=auth_headers)
    ).status_code == 404
    still = await client.get(f"{RECORDS}/{rid}", headers=auth_headers)
    assert still.status_code == 200


@pytest.mark.asyncio
async def test_bulk_delete_does_not_delete_records(client, auth_headers):
    rid = await _create_record(client, auth_headers)

    by_ids = await client.post(
        f"{OUTFITS}/bulk/delete", json={"outfit_ids": [rid]}, headers=auth_headers
    )
    assert by_ids.status_code == 200
    assert by_ids.json()["deleted"] == 0

    select_all = await client.post(
        f"{OUTFITS}/bulk/delete",
        json={"select_all": True, "filters": {"status_filter": "accepted"}},
        headers=auth_headers,
    )
    assert select_all.status_code == 200
    assert select_all.json()["deleted"] == 0

    assert (await client.get(f"{RECORDS}/{rid}", headers=auth_headers)).status_code == 200
