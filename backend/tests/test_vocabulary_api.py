"""Runtime vocabulary API — soft entries write back to the JSON and the markdown.

Every write must keep both faces in step *and* compile-equivalent: the compiler
rebuilds the JSON from the markdown and --check (T13 gate) compares them byte
for byte.
"""
import json

import pytest

from app.utils.garment_vocabulary import VOCABULARY_PATH
from app.utils.vocabulary_md import MD_PATH


@pytest.fixture()
def vocab_snapshot():
    before_json = VOCABULARY_PATH.read_text(encoding="utf-8")
    before_md = MD_PATH.read_text(encoding="utf-8")
    yield
    VOCABULARY_PATH.write_text(before_json, encoding="utf-8")
    MD_PATH.write_text(before_md, encoding="utf-8")


def _compile_md():
    from scripts.compile_vocabulary import compile_vocabulary

    return compile_vocabulary(MD_PATH.read_text(encoding="utf-8"))


class TestVocabularyApi:
    @pytest.mark.asyncio
    async def test_get_vocabulary(self, client, auth_headers):
        resp = await client.get("/api/v1/vocabulary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["body_parts"]) == 7
        assert len(data["colors"]["values"]) == 48

    @pytest.mark.asyncio
    async def test_add_style_writes_json_and_md(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/styles",
            json={"value": "y2k", "label": "Y2K"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        assert any(s["value"] == "y2k" for s in data["styles"])
        assert "y2k" in MD_PATH.read_text(encoding="utf-8")
        assert _compile_md() == data

    @pytest.mark.asyncio
    async def test_add_color_requires_hex(self, client, auth_headers, vocab_snapshot):
        bad = await client.post(
            "/api/v1/vocabulary/colors/values",
            json={"value": "haze", "label": "雾色", "family": "blue"},
            headers=auth_headers,
        )
        assert bad.status_code == 422
        good = await client.post(
            "/api/v1/vocabulary/colors/values",
            json={"value": "haze", "label": "雾色", "family": "blue", "hex": "#8fa9bf"},
            headers=auth_headers,
        )
        assert good.status_code in (200, 201)
        assert _compile_md() == json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))

    @pytest.mark.asyncio
    async def test_add_type_rejects_unknown_body_part(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/types",
            json={"value": "hoodie-dress", "label": "卫衣裙", "body_part": "unknown"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_type_writes_before_catchall(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/types",
            json={"value": "tunic", "label": "罩衫", "body_part": "tops"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        tops = [t["value"] for t in data["types"] if t["body_part"] == "tops"]
        assert tops[-1] == "top", tops  # catch-all stays last
        assert "tunic" in tops
        assert _compile_md() == data

    @pytest.mark.asyncio
    async def test_duplicate_slug_rejected(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/styles",
            json={"value": "casual", "label": "休闲2"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_rename_and_disable_and_reenable(self, client, auth_headers, vocab_snapshot):
        rename = await client.patch(
            "/api/v1/vocabulary/styles/casual",
            json={"label": "休闲风"},
            headers=auth_headers,
        )
        assert rename.status_code == 200
        disable = await client.patch(
            "/api/v1/vocabulary/styles/casual",
            json={"disabled": True},
            headers=auth_headers,
        )
        assert disable.status_code == 200
        data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        entry = next(s for s in data["styles"] if s["value"] == "casual")
        assert entry["label"] == "休闲风" and entry.get("disabled") is True
        assert _compile_md() == data

        enable = await client.patch(
            "/api/v1/vocabulary/styles/casual",
            json={"disabled": False},
            headers=auth_headers,
        )
        assert enable.status_code == 200
        data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        entry = next(s for s in data["styles"] if s["value"] == "casual")
        assert "disabled" not in entry
        assert _compile_md() == data

    @pytest.mark.asyncio
    async def test_add_color_family_full_chain(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/colors/families",
            json={"value": "pastel", "label": "马卡龙系"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        value = await client.post(
            "/api/v1/vocabulary/colors/values",
            json={"value": "macaron", "label": "马卡龙", "family": "pastel", "hex": "#f7c6d9"},
            headers=auth_headers,
        )
        assert value.status_code in (200, 201), value.text
        data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
        assert any(f["value"] == "pastel" for f in data["colors"]["families"])
        assert any(c["value"] == "macaron" for c in data["colors"]["values"])
        assert _compile_md() == data

    @pytest.mark.asyncio
    async def test_materials_and_formality_are_closed(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/materials",
            json={"value": "cashmere", "label": "羊绒"},
            headers=auth_headers,
        )
        assert resp.status_code in (404, 405)


def test_runtime_type_meta_matches_compiler():
    # The API derives role/wash from body part on add; the compiler must derive
    # the same values on recompile or the two faces drift on --check.
    from app.api.vocabulary import ROLE_BY_PART, WASH_BY_PART
    from scripts.compile_vocabulary import ROLE_BY_PART as C_ROLE, WASH_BY_PART as C_WASH

    assert ROLE_BY_PART == C_ROLE
    assert WASH_BY_PART == C_WASH


class TestTypeMeta:
    @pytest.mark.asyncio
    async def test_added_type_role_follows_body_part(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/types",
            json={"value": "hoodie-dress", "label": "卫衣裙", "body_part": "dresses"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        entry = resp.json()
        assert entry["role"] == "full_body"
        assert _compile_md() == json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
