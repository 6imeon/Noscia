"""BYOK structured extraction — no-key path, schema building, citation parsing (no network)."""

import asyncio

from noscia.contract import StructuredField
from noscia.search import structured as st


def _fields(*names: str) -> list[StructuredField]:
    return [StructuredField(name=n) for n in names]


def test_no_key_returns_all_null_fields(monkeypatch):
    monkeypatch.setattr(st, "get_secret", lambda _name: None)
    out = asyncio.run(st.extract_structured("q", ["passage a"], _fields("Target year", "Scope")))
    assert [f.name for f in out] == ["Target year", "Scope"]
    assert all(f.value is None and f.citations == [] for f in out)


def test_empty_passages_short_circuit(monkeypatch):
    monkeypatch.setattr(st, "get_secret", lambda _name: "sk-test")
    out = asyncio.run(st.extract_structured("q", ["   ", ""], _fields("Target year")))
    assert out[0].value is None and out[0].citations == []


def test_build_schema_keys_are_slugged_and_strict():
    schema, keymap = st.build_schema(_fields("Target Year", "Scope 3 coverage"))
    assert [k for k, _ in keymap] == ["target_year", "scope_3_coverage"]
    assert [name for _, name in keymap] == ["Target Year", "Scope 3 coverage"]
    # strict Structured Outputs: every property required, no extras
    assert schema["required"] == ["target_year", "scope_3_coverage"]
    assert schema["additionalProperties"] is False
    # each field is a {value: string|null, sources: int[]} object so citations are structural
    prop = schema["properties"]["target_year"]
    assert prop["type"] == "object"
    assert prop["required"] == ["value", "sources"]
    assert prop["properties"]["value"]["type"] == ["string", "null"]
    assert prop["properties"]["sources"]["items"]["type"] == "integer"


def test_build_schema_dedupes_colliding_and_empty_keys():
    schema, keymap = st.build_schema(_fields("Scope!", "Scope?", "***"))
    keys = [k for k, _ in keymap]
    assert keys[0] == "scope" and keys[1] == "scope_2"  # collision suffixed
    assert keys[2] == "field_2"  # un-sluggable name falls back to index
    assert len(set(keys)) == 3 and schema["required"] == keys


def test_parse_field_extracts_value_dedupes_and_bounds_sources():
    value, cited = st._parse_field({"value": "Net-zero by 2050", "sources": [1, 3, 1, 9]}, n=6)
    assert value == "Net-zero by 2050"
    assert cited == [1, 3]  # deduped; 9 > n dropped


def test_parse_field_null_when_unsupported():
    assert st._parse_field({"value": None, "sources": []}, 6) == (None, [])
    assert st._parse_field({"value": "   ", "sources": [1]}, 6) == (None, [])
    assert st._parse_field(None, 6) == (None, [])  # malformed object guarded
    # a value with no usable sources still returns the value, just uncited
    assert st._parse_field({"value": "ERW", "sources": []}, 6) == ("ERW", [])


def test_auto_schema_is_strict_array_of_named_fields():
    items = st.AUTO_SCHEMA["properties"]["fields"]["items"]
    # the model names its own snake_case fields, so each item carries name + value + sources
    assert items["required"] == ["name", "value", "sources"]
    assert items["additionalProperties"] is False
    assert items["properties"]["name"]["type"] == "string"
    assert items["properties"]["value"]["type"] == ["string", "null"]
    assert st.AUTO_SCHEMA["required"] == ["fields"]


def test_auto_extract_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(st, "get_secret", lambda _name: None)
    assert asyncio.run(st.auto_extract("q", ["passage a"])) == []


def test_auto_extract_parses_flat_fields_and_drops_nameless(monkeypatch):
    monkeypatch.setattr(st, "get_secret", lambda _name: "sk-test")

    async def fake_complete(query, sources, key, schema, model):
        assert schema is st.AUTO_SCHEMA
        return {
            "fields": [
                {"name": "deal_volume", "value": "Microsoft bought 36,920t.", "sources": [1, 1, 9]},
                {"name": "  ", "value": "dropped", "sources": [1]},  # no name → dropped
                {"name": "target_year", "value": None, "sources": []},  # unsupported → null
            ]
        }

    monkeypatch.setattr(st, "_complete", fake_complete)
    out = asyncio.run(st.auto_extract("q", ["p1", "p2"]))
    assert [f.name for f in out] == ["deal_volume", "target_year"]
    assert out[0].value == "Microsoft bought 36,920t." and out[0].citations == [1]  # deduped; 9>n
    assert out[1].value is None and out[1].citations == []
