"""Convert the official campaign-calendar response into dated calendar entries.

Only fields that describe the public campaign and its listed calendar date are
retained. A listed day is never interpreted as an opening or closing date.
"""

from __future__ import annotations

from typing import Any

from .calendar import validate_document


_OFFICIAL_SERVER = "https://mcp.mcd.cn"
_ENTRY_SUFFIX = "｜活动日历条目"


class NormalizationError(ValueError):
    """A response cannot be normalized without guessing its meaning."""


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NormalizationError(f"Missing or invalid {location} object.")
    return value


def _list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise NormalizationError(f"Missing or invalid {location} list.")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"Missing or invalid {location} text.")
    return value


def _event_identifier(event: dict[str, Any]) -> str:
    for field in ("activityCode", "resourceId"):
        candidate = event.get(field)
        if candidate is None or candidate == "":
            continue
        if not isinstance(candidate, str):
            raise NormalizationError("Invalid campaign identifier type.")
        if candidate.strip():
            return candidate.strip()
    raise NormalizationError("The campaign has no activityCode or resourceId.")


def _source_texts(result: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for block in _list(result.get("content"), "result.content"):
        block = _object(block, "result.content block")
        if block.get("type") == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise NormalizationError("Invalid result.content text block.")
            texts.append(text)
    return texts


def normalize_campaign(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a validated ``mode='live'`` document from the official MCP result.

    Supported input is the envelope returned by ``client.fetch_campaign`` with
    ``result.structuredContent.success/code/data.dailyList``. Each dailyList
    event becomes one entry on its displayed day, with start=end. The original
    article content must also occur continuously in a result.content text block.
    Empty dailyList is a valid empty calendar; missing fields are errors.

    Exact duplicate entries are removed. Conflicting content for one campaign
    identifier on one day is an error. Prices, subscriptions, account fields,
    app links, and image lists are not used or copied into the output.
    """
    raw = _object(raw, "MCP response")
    if raw.get("server") != _OFFICIAL_SERVER:
        raise NormalizationError("The response does not identify the official MCP server.")
    retrieved_at = _text(raw.get("retrieved_at"), "retrieved_at")
    result = _object(raw.get("result"), "result")
    if result.get("isError", False) is not False:
        raise NormalizationError("The campaign-calendar tool reported an error.")
    structured = _object(result.get("structuredContent"), "structuredContent")
    if "success" not in structured or "code" not in structured:
        raise NormalizationError("Missing campaign business status fields.")
    if (structured["success"] is not True
            or type(structured["code"]) is not int
            or structured["code"] != 200):
        raise NormalizationError("The campaign-calendar business response was unsuccessful.")
    data = _object(structured.get("data"), "campaign data")
    days = _list(data.get("dailyList"), "data.dailyList")
    texts = _source_texts(result)
    by_identifier: dict[str, dict[str, str]] = {}
    for day_value in days:
        day = _object(day_value, "dailyList day")
        display_date = _text(day.get("date"), "dailyList date")
        for event_value in _list(day.get("events"), "dailyList events"):
            event = _object(event_value, "campaign event")
            identifier = _event_identifier(event) + ":" + display_date
            article = _object(event.get("articleDto"), "articleDto")
            title = _text(article.get("title"), "articleDto.title").strip()
            source_text = _text(article.get("content"), "articleDto.content")
            if not any(source_text in block for block in texts):
                raise NormalizationError(
                    "Campaign evidence was not found verbatim in the MCP text response."
                )
            entry = {
                "id": identifier,
                "title": title + _ENTRY_SUFFIX,
                "start": display_date,
                "end": display_date,
                "description": (
                    f"这是官方活动日历的展示日期（{display_date}），"
                    "不代表当天新开售，也不代表活动结束日期。"
                    "正文中的开售日期、活动规则等信息请以来源原文为准。"
                ),
                "source_text": source_text,
            }
            previous = by_identifier.get(identifier)
            if previous is not None and previous != entry:
                raise NormalizationError(
                    "Conflicting campaign content was returned for the same identifier and day."
                )
            by_identifier[identifier] = entry
    document = {
        "mode": "live",
        "retrieved_at": retrieved_at,
        "events": list(by_identifier.values()),
    }
    try:
        clean = validate_document(document)
    except ValueError:
        # Calendar validation owns date parsing and field bounds; its failures
        # must not echo an identifier or any other raw response data here.
        raise NormalizationError(
            "The normalized campaign has invalid calendar dates or fields."
        ) from None
    clean["events"].sort(key=lambda entry: (entry["start"], entry["id"]))
    return clean
