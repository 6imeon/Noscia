"""Structured extraction — return the answer as typed, cited fields over the passages (BYOK).

The companion to ``summarize`` (prose answer): same grounded retrieval, but the model
returns a *typed value per field* instead of a paragraph — the "Structured" tab. Two modes:

* AUTO (default) — the model reads the query+passages and *derives* the salient fields
  (entities, quantities, dates, methods, standards) and fills them. So Structured mirrors
  the prose Answer rather than forcing a fixed schema that may not fit the question — no
  more "great answer, then a wall of blanks." ``auto_extract``.
* MANUAL — the caller pins specific fields (build-a-table use case) and we fill exactly
  those, slugged into a strict schema. ``extract_structured``.

Both: one LLM call constrained by a JSON schema (OpenAI/OpenRouter Structured Outputs) over
the same compact passages the answer uses — so a structured pull costs no more than a
normal search + one synthesis. Each field cites the source rows it drew on; any field the
passages don't support comes back ``null`` (evidence-or-null, rule 8 — blank beats
hallucinated). BYOK via the ``get_secret`` seam; no key ⇒ all-null fields, no error.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import get_secret
from ..contract import ExtractedField, StructuredField

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

# A few more passages than the prose answer — several fields need broader grounding.
DEFAULT_TOP_N = 8
_TIMEOUT_S = 40.0

_SYSTEM = (
    "You are an ESG research assistant performing structured extraction. Fill each "
    "requested field using ONLY the numbered source passages provided — no outside "
    "knowledge. For each field return an object with `value` (a concise value drawn from "
    "the passages) and `sources` (the list of source numbers that support that value). If "
    "the passages do not contain the information for a field, return null for `value` and "
    "an empty `sources` list — never guess. Blank beats hallucinated."
)

# AUTO mode: the model picks the fields too. It returns the answer as a flat JSON object —
# snake_case keys naming the salient aspects of the topic, each value a single synthesized
# sentence grounded in (and citing) the passages. Like Exa's Structured tab: the answer,
# as JSON. Each value names its own subject, so a multi-subject topic reads cleanly without
# splitting into separate records.
_MAX_AUTO_FIELDS = 8
_AUTO_SYSTEM = (
    "You are an ESG research assistant. Read the question and the numbered source "
    "passages, then return the answer as a flat JSON object of the key findings — like a "
    "structured-data view of the answer.\n"
    "- Choose the salient aspects of the topic (the sub-questions a reader cares about). "
    f"Return 3-{_MAX_AUTO_FIELDS} of them.\n"
    "- Each is one field: a short snake_case `name` (e.g. scope3_requirements, "
    "baseline_year, deal_volume), a `value` that is ONE concise, self-contained sentence "
    "answering it, and `sources` (the source numbers supporting it).\n"
    "- A value must NAME its own subject so it stands alone (e.g. 'CSRD/ESRS requires "
    "firms to disclose material Scope 3 emissions.'), and may draw on several passages.\n"
    "- Use ONLY the passages — no outside knowledge. If the passages don't support an "
    "aspect, set `value` null and `sources` empty — never guess. Blank beats hallucinated."
)

# A fixed strict schema for AUTO: a flat list of {name, value, sources} the model fills —
# it names its own fields (the field set isn't known ahead of time, unlike the manual path).
AUTO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": ["string", "null"]},
                    "sources": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["name", "value", "sources"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["fields"],
    "additionalProperties": False,
}


def _format_sources(passages: list[str]) -> str:
    return "\n\n".join(f"[{i}] {p[:1500]}" for i, p in enumerate(passages, start=1) if p.strip())


def _slug(name: str) -> str:
    """A JSON-schema-safe key from a display name (Structured Outputs needs ^[a-zA-Z0-9_])."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]


def build_schema(fields: list[StructuredField]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """A strict object schema + the key→display-name map.

    Each field is a ``{value: string|null, sources: int[]}`` object so the model names the
    passages it drew on structurally (more reliable than parsing inline ``[n]``). Keys are
    slugged from the display name, de-duplicated, with an index fallback so an unnamed/
    garbage field still yields a valid unique key.
    """
    props: dict[str, Any] = {}
    keymap: list[tuple[str, str]] = []
    for i, f in enumerate(fields):
        key = _slug(f.name) or f"field_{i}"
        base, j = key, 2
        while key in props:
            key, j = f"{base}_{j}", j + 1
        props[key] = {
            "type": "object",
            "description": (f.description or f.name)[:200],
            "properties": {
                "value": {"type": ["string", "null"]},
                "sources": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["value", "sources"],
            "additionalProperties": False,
        }
        keymap.append((key, f.name))
    schema = {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }
    return schema, keymap


def _parse_field(obj: Any, n: int) -> tuple[str | None, list[int]]:
    """``(value, cited_ranks)`` from one field object; ``(None, [])`` when unsupported."""
    if not isinstance(obj, dict):
        return None, []
    value = obj.get("value")
    if not isinstance(value, str) or not value.strip():
        return None, []
    raw = obj.get("sources") or []
    cited = sorted({s for s in raw if isinstance(s, int) and 1 <= s <= n})
    return value.strip(), cited


async def _complete(query: str, sources: str, key: str, schema: dict[str, Any], model: str) -> Any:
    """One Structured-Outputs call → parsed JSON content. Raises on any transport error."""
    import httpx

    system = _AUTO_SYSTEM if schema is AUTO_SCHEMA else _SYSTEM
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Topic: {query}\n\nSources:\n{sources}"},
        ],
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "extraction", "strict": True, "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        resp = await client.post(
            OPENROUTER_URL, headers={"Authorization": f"Bearer {key}"}, json=body
        )
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])


async def extract_structured(
    query: str,
    passages: list[str],
    fields: list[StructuredField],
    *,
    model: str = DEFAULT_MODEL,
) -> list[ExtractedField]:
    """Fill ``fields`` from ``passages`` — one cited value each, null when unsupported.

    Never raises: returns all-null fields when no key is configured, the passages are
    empty, or the call fails — so the caller can attach the result blindly.
    """
    echoed = [ExtractedField(name=f.name) for f in fields]
    key = get_secret("openrouter")
    sources = _format_sources(passages)
    if not key or not sources or not fields:
        return echoed

    schema, keymap = build_schema(fields)
    try:
        data = await _complete(query, sources, key, schema, model)
    except Exception:  # noqa: BLE001 — a failed extraction must not sink the search
        return echoed

    n = len(passages)
    out: list[ExtractedField] = []
    for key_i, name in keymap:
        value, cites = _parse_field(data.get(key_i), n)
        out.append(ExtractedField(name=name, value=value, citations=cites))
    return out


def _parse_fields(raw: Any, n: int) -> list[ExtractedField]:
    """Named {name,value,sources} objects → ExtractedFields; drops the nameless."""
    out: list[ExtractedField] = []
    for item in (raw or [])[:_MAX_AUTO_FIELDS]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        value, cites = _parse_field(item, n)
        out.append(ExtractedField(name=name.strip()[:60], value=value, citations=cites))
    return out


async def auto_extract(
    query: str,
    passages: list[str],
    *,
    model: str = DEFAULT_MODEL,
) -> list[ExtractedField]:
    """Derive the salient fields from the query+passages and fill them (AUTO mode).

    The model names its own snake_case fields and gives each a one-sentence synthesized
    value — the answer as a flat JSON object (Exa-style). Returns ``[]`` when no
    key/passages or the call fails (never raises); drops any field with no usable name.
    """
    key = get_secret("openrouter")
    sources = _format_sources(passages)
    if not key or not sources:
        return []

    try:
        data = await _complete(query, sources, key, AUTO_SCHEMA, model)
    except Exception:  # noqa: BLE001 — a failed extraction must not sink the search
        return []

    return _parse_fields((data or {}).get("fields"), len(passages))
