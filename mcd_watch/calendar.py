"""Validate reviewed event data and export deterministic, offline calendars.

This module never fetches data.  A human-reviewed MCP response is the source of
live records; bundled examples must use ``mode='demo'``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit


DEMO_LABEL = "【模拟演示】"
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_REQUIRED_DOCUMENT_FIELDS = {"mode", "retrieved_at", "events"}
_REQUIRED_EVENT_FIELDS = {"id", "title", "start", "description", "source_text"}
_OPTIONAL_EVENT_FIELDS = {"end", "source_url"}
_MAX_EVENTS = 1000
_MAX_DOCUMENT_BYTES = 20_000_000


def _text(value: Any, field: str, maximum: int, *, multiline: bool = False,
          nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    # CRLF is a newline; a lone CR or another ASCII control is not text input.
    value = value.replace("\r\n", "\n") if multiline else value
    for character in value:
        codepoint = ord(character)
        if ((codepoint < 32 and not (multiline and character == "\n"))
                or codepoint == 127 or 0xD800 <= codepoint <= 0xDFFF):
            raise ValueError(f"{field} contains a forbidden control or surrogate")
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if nonempty and not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value


def _date(value: Any, field: str) -> date:
    value = _text(value, field, 10, nonempty=True)
    if not _DATE_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} is not a valid calendar date") from error


def _timestamp(value: Any) -> datetime:
    value = _text(value, "retrieved_at", 40, nonempty=True)
    if not _TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("retrieved_at must be an ISO 8601 timestamp with a timezone")
    if value[-1] != "Z":
        offset_hours, offset_minutes = map(int, value[-5:].split(":"))
        if offset_hours > 23 or offset_minutes > 59:
            raise ValueError("retrieved_at contains an invalid timezone offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("missing timezone")
        # Check representability after conversion as well as local validity.
        parsed.astimezone(timezone.utc)
        return parsed
    except (ValueError, OverflowError) as error:
        raise ValueError("retrieved_at is not a valid timezone-aware timestamp") from error


def _source_url(value: Any, mode: str, field: str) -> str:
    value = _text(value, field, 2048, nonempty=True)
    if (any(character.isspace() for character in value)
            or any(character in value for character in '\\<>"\'`')
            or re.search(r"%0[ad]", value, flags=re.IGNORECASE)):
        raise ValueError(f"{field} contains unsafe URL characters")
    try:
        parsed = urlsplit(value)
        allowed_schemes = {"https"} if mode == "live" else {"http", "https"}
        if (parsed.scheme.lower() not in allowed_schemes or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("unsupported URL")
        # Reading .port validates malformed or out-of-range port numbers.
        parsed.port
    except ValueError as error:
        protocol = "https" if mode == "live" else "http or https"
        raise ValueError(f"{field} must be a safe absolute {protocol} URL") from error
    return value


def validate_document(document: Any) -> dict[str, Any]:
    """Return a fresh canonical document or raise ``ValueError``.

    Unknown fields are rejected to catch mistakes in the reviewed input.
    ``end`` defaults to ``start`` and is inclusive.  Descriptions and evidence
    preserve LF newlines; CRLF input is normalized to LF.
    """
    if not isinstance(document, dict):
        raise ValueError("document must be a JSON object")
    if set(document) != _REQUIRED_DOCUMENT_FIELDS:
        raise ValueError("document must contain exactly mode, retrieved_at, and events")
    mode = document["mode"]
    if not isinstance(mode, str) or mode not in {"demo", "live"}:
        raise ValueError("mode must be demo or live")
    _timestamp(document["retrieved_at"])
    events = document["events"]
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise ValueError(f"events must be a list with at most {_MAX_EVENTS} records")
    reviewed: list[dict[str, str]] = []
    ids: set[str] = set()
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, dict):
            raise ValueError(f"{prefix} must be an object")
        fields = set(event)
        if (not _REQUIRED_EVENT_FIELDS.issubset(fields)
                or fields - (_REQUIRED_EVENT_FIELDS | _OPTIONAL_EVENT_FIELDS)):
            raise ValueError(f"{prefix} has missing or unknown fields")
        identifier = _text(event["id"], f"{prefix}.id", 200, nonempty=True).strip()
        if identifier in ids:
            raise ValueError(f"duplicate event id: {identifier}")
        ids.add(identifier)
        title = _text(event["title"], f"{prefix}.title", 500, nonempty=True).strip()
        start = _date(event["start"], f"{prefix}.start")
        end = _date(event.get("end", event["start"]), f"{prefix}.end")
        if end < start:
            raise ValueError(f"{prefix}.end must not precede start")
        clean = {
            "id": identifier,
            "title": title,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "description": _text(event["description"], f"{prefix}.description",
                                 20_000, multiline=True),
            "source_text": _text(event["source_text"], f"{prefix}.source_text",
                                 20_000, multiline=True, nonempty=True),
        }
        if "source_url" in event:
            clean["source_url"] = _source_url(event["source_url"], mode,
                                               f"{prefix}.source_url")
        reviewed.append(clean)
    return {"mode": mode, "retrieved_at": document["retrieved_at"], "events": reviewed}


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_events(path: str | Path) -> dict[str, Any]:
    """Read a UTF-8 JSON file, reject duplicate keys, and validate its schema."""
    path = Path(path)
    if path.stat().st_size > _MAX_DOCUMENT_BYTES:
        raise ValueError("input JSON exceeds 20 MB")
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"),
                              object_pairs_hook=_unique_json_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"input is not valid UTF-8 JSON: {error}") from error
    return validate_document(document)


def _select(document: Any, keyword: str | None, starts_after: str | None,
            ends_before: str | None) -> tuple[dict[str, Any], list[dict[str, str]]]:
    clean = validate_document(document)
    lower = _date(starts_after, "starts_after") if starts_after is not None else None
    upper = _date(ends_before, "ends_before") if ends_before is not None else None
    if lower and upper and lower > upper:
        raise ValueError("starts_after must not be later than ends_before")
    needle = (_text(keyword, "keyword", 500).casefold() if keyword is not None else "")
    selected = []
    for event in clean["events"]:
        if lower and date.fromisoformat(event["end"]) < lower:
            continue
        if upper and date.fromisoformat(event["start"]) > upper:
            continue
        searchable = "\n".join(event[key] for key in ("title", "description", "source_text"))
        if needle and needle not in searchable.casefold():
            continue
        selected.append(event)
    selected.sort(key=lambda event: (event["start"], event["end"], event["id"]))
    return clean, selected


def _ical_text(value: str) -> str:
    return (value.replace("\\", "\\\\").replace("\n", "\\n")
            .replace(";", "\\;").replace(",", "\\,"))


def _fold(line: str) -> str:
    """Fold an iCalendar content line at 75 UTF-8 octets, without splitting text."""
    segments: list[str] = []
    segment = ""
    octets = 0
    for character in line:
        width = len(character.encode("utf-8"))
        if octets + width > 75:
            segments.append(segment)
            segment = " "
            octets = 1
        segment += character
        octets += width
    segments.append(segment)
    return "\r\n".join(segments)


def _title(event: dict[str, str], mode: str) -> str:
    title = event["title"]
    return (DEMO_LABEL + title if mode == "demo" and not title.startswith(DEMO_LABEL)
            else title)


def to_ics(document: Any, keyword: str | None = None,
           starts_after: str | None = None, ends_before: str | None = None) -> str:
    """Export RFC 5545 all-day events with inclusive overlap date filtering.

    Re-exporting a stable ID in the same mode preserves its UID.  Live and demo
    IDs have separate namespaces.  Returned text has CRLF endings; write with
    ``Path(...).write_bytes(text.encode('utf-8'))`` to preserve them on Windows.
    """
    clean, events = _select(document, keyword, starts_after, ends_before)
    mode = clean["mode"]
    utc = _timestamp(clean["retrieved_at"]).astimezone(timezone.utc)
    stamp = (f"{utc.year:04d}{utc.month:02d}{utc.day:02d}T"
             f"{utc.hour:02d}{utc.minute:02d}{utc.second:02d}Z")
    calendar_name = DEMO_LABEL + "麦麦不忘日历" if mode == "demo" else "麦麦不忘日历"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//McdWatch//Reviewed Activity Calendar 1.0//ZH-CN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:" + _ical_text(calendar_name)]
    if mode == "demo":
        lines.append("X-WR-CALDESC:" + _ical_text("模拟演示数据，不代表真实活动或优惠。"))
    for event in events:
        try:
            exclusive_end = date.fromisoformat(event["end"]) + timedelta(days=1)
        except OverflowError as error:
            raise ValueError("event end is too late for an exclusive iCalendar DTEND") from error
        uid = hashlib.sha256((mode + "\0" + event["id"]).encode("utf-8")).hexdigest()
        evidence_label = "模拟来源文字（非真实优惠）" if mode == "demo" else "来源原文证据"
        description_parts = [event["description"], evidence_label + "：" + event["source_text"]]
        if mode == "demo":
            description_parts.insert(0, "模拟演示，不代表真实活动或优惠。")
        description = "\n\n".join(part for part in description_parts if part)
        lines.extend([
            "BEGIN:VEVENT", "UID:" + uid + "@mcd-watch-calendar",
            "DTSTAMP:" + stamp,
            "DTSTART;VALUE=DATE:" + event["start"].replace("-", ""),
            "DTEND;VALUE=DATE:" + exclusive_end.isoformat().replace("-", ""),
            "SUMMARY:" + _ical_text(_title(event, mode)),
            "DESCRIPTION:" + _ical_text(description),
        ])
        if event.get("source_url"):
            lines.append("URL:" + event["source_url"])
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _markdown_text(value: str) -> str:
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", value)


def to_markdown(document: Any, keyword: str | None = None,
                starts_after: str | None = None, ends_before: str | None = None) -> str:
    """Export a readable, date-sorted Markdown digest using the same filters."""
    clean, events = _select(document, keyword, starts_after, ends_before)
    mode = clean["mode"]
    heading = "# " + (DEMO_LABEL if mode == "demo" else "") + "麦麦不忘日历"
    lines = [heading, ""]
    if mode == "demo":
        lines.extend(["> 模拟演示数据，不代表真实活动或优惠。", ""])
    lines.extend(["资料获取时间：" + _markdown_text(clean["retrieved_at"]), "",
                  f"共 {len(events)} 项活动。", ""])
    if not events:
        lines.extend(["当前筛选条件下没有活动。", ""])
    for event in events:
        interval = event["start"]
        if event["end"] != event["start"]:
            interval += " 至 " + event["end"] + "（含末日）"
        lines.extend(["## " + _markdown_text(_title(event, mode)), "",
                      "日期：" + interval, ""])
        if event["description"]:
            lines.extend([_markdown_text(event["description"]), ""])
        label = "模拟来源文字（非真实优惠）" if mode == "demo" else "来源原文证据"
        lines.extend([label + "：", ""])
        lines.extend("> " + _markdown_text(line) for line in event["source_text"].split("\n"))
        lines.append("")
        if event.get("source_url"):
            lines.extend(["[查看来源](<" + event["source_url"] + ">)", ""])
    return "\n".join(lines)


def diff_documents(current: Any, previous: Any) -> dict[str, list[str]]:
    """Compare reviewed records by stable ID, ignoring retrieval time and order.

    Comparing demo against live is an input error because they represent
    different data namespaces.  Output lists are lexicographically sorted.
    """
    clean_current = validate_document(current)
    clean_previous = validate_document(previous)
    if clean_current["mode"] != clean_previous["mode"]:
        raise ValueError("cannot compare demo and live documents")
    current_by_id = {event["id"]: event for event in clean_current["events"]}
    previous_by_id = {event["id"]: event for event in clean_previous["events"]}
    current_ids, previous_ids = set(current_by_id), set(previous_by_id)
    return {
        "added": sorted(current_ids - previous_ids),
        "changed": sorted(identifier for identifier in current_ids & previous_ids
                          if current_by_id[identifier] != previous_by_id[identifier]),
        "removed": sorted(previous_ids - current_ids),
    }
