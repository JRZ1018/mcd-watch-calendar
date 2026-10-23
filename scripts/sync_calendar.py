"""Build the public calendar from one verified official MCP response.

Run ``python scripts/sync_calendar.py --help`` for online and offline usage.
The raw response is kept under private/ and is never a public artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcd_watch.calendar import to_ics, to_markdown, validate_document
from mcd_watch.cli import verify_source
from mcd_watch.client import fetch_campaign
from mcd_watch.normalize import normalize_campaign


SERVER = "https://mcp.mcd.cn"
TOOL = "campaign-calendar"
PUBLIC_PATHS = (
    "docs/calendar.ics",
    "docs/calendar.md",
    "docs/events.json",
    "docs/status.json",
    "evidence/live-verification.json",
)
_EVENT_FIELDS = ("id", "title", "start", "end", "description", "source_text", "source_url")


class SyncError(RuntimeError):
    """A safe synchronization failure without response contents or credentials."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SyncError("The raw response contains duplicate JSON keys.")
        result[key] = value
    return result


def _load_raw(raw_path: Path) -> dict[str, Any]:
    if raw_path.stat().st_size > 20_000_000:
        raise SyncError("The raw response exceeds the supported size limit.")
    raw = json.loads(raw_path.read_bytes(), object_pairs_hook=_unique_object)
    if not isinstance(raw, dict):
        raise SyncError("The raw response must be a JSON object.")
    return raw


def build_publications(raw: dict[str, Any], raw_path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Generate every public payload in memory before touching existing files."""
    normalized = validate_document(normalize_campaign(raw))
    # Keep an explicit public field projection even if normalization grows new
    # internal fields in a future version.
    document = {
        "mode": normalized["mode"],
        "retrieved_at": normalized["retrieved_at"],
        "events": [
            {key: event[key] for key in _EVENT_FIELDS if key in event}
            for event in normalized["events"]
        ],
    }
    document = validate_document(document)
    raw_hash = verify_source(document, raw_path)
    # The normalizer requires evidence in an actual text block. Check that
    # stricter condition again here rather than allowing serialized account data
    # to act as a substitute source for a public quote.
    texts = [block["text"] for block in raw["result"]["content"]
             if block.get("type") == "text"]
    if not all(any(event["source_text"] in text for text in texts)
               for event in document["events"]):
        raise SyncError("A public quote was not present in the original MCP text.")
    dates = sorted({event["start"] for event in document["events"]})
    status = {
        "mode": "live",
        "server": SERVER,
        "tool": TOOL,
        "retrieved_at": document["retrieved_at"],
        "event_count": len(document["events"]),
        "day_count": len(dates),
        "range_start": dates[0] if dates else None,
        "range_end": dates[-1] if dates else None,
    }
    event_bytes = _json_bytes(document)
    calendar = to_ics(document)
    markdown = to_markdown(document)
    if (not calendar.startswith("BEGIN:VCALENDAR\r\n")
            or not calendar.endswith("END:VCALENDAR\r\n")
            or calendar.count("\r\nBEGIN:VEVENT\r\n") != len(document["events"])):
        raise SyncError("The generated iCalendar did not pass structural verification.")
    # Verify serialized JSON, including date and field constraints, before any
    # of the generated output replaces a currently published file.
    validate_document(json.loads(event_bytes))
    receipt = {
        **status,
        "raw_sha256": raw_hash,
        "normalized_sha256": hashlib.sha256(event_bytes).hexdigest(),
        "source_text_verified": True,
        "calendar_dates_are_display_dates": True,
    }
    payloads = {
        "docs/calendar.ics": calendar.encode("utf-8"),
        "docs/calendar.md": markdown.encode("utf-8"),
        "docs/events.json": event_bytes,
        "docs/status.json": _json_bytes(status),
        "evidence/live-verification.json": _json_bytes(receipt),
    }
    if set(payloads) != set(PUBLIC_PATHS):
        raise SyncError("The generated publication file set was invalid.")
    return payloads, status


def _stage_bytes(target: Path, content: bytes) -> Path:
    """Write a closed, flushed replacement on the target's own filesystem."""
    target.parent.mkdir(parents=True, exist_ok=True)
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=target.parent,
            prefix=f".{target.name}.sync-", suffix=".tmp",
        ) as handle:
            staged = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return staged
    except BaseException:
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise


def _publish_atomically(payloads: dict[Path, bytes]) -> None:
    """Stage all files, then replace each atomically with rollback on failure.

    Filesystems do not support one atomic operation over multiple paths. Existing
    bytes are therefore staged too, so a later replace failure can restore every
    earlier replacement without regenerating data or making a network request.
    """
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    retain_backups = False
    try:
        for target, content in payloads.items():
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise SyncError("An output path is not a regular file.")
            staged[target] = _stage_bytes(target, content)
            backups[target] = _stage_bytes(target, target.read_bytes()) if target.exists() else None
        for target, replacement in staged.items():
            os.replace(replacement, target)
            replaced.append(target)
    except BaseException:
        rollback_failed = False
        for target in reversed(replaced):
            try:
                backup = backups[target]
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    os.replace(backup, target)
                    backups[target] = None
            except OSError:
                rollback_failed = True
        if rollback_failed:
            retain_backups = True
            raise SyncError(
                "Publication failed and rollback needs local recovery; "
                "same-directory backup files were retained."
            ) from None
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        if not retain_backups:
            for temporary in backups.values():
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def sync_calendar(*, from_raw: Path | None = None, output_root: Path = ROOT) -> dict[str, Any]:
    """Sync once from a saved raw file or one schema-validated online query.

    No token, raw response, subscription field, or account data is printed.
    ``from_raw`` preserves the original retrieved_at and needs no network.
    """
    output_root = Path(output_root)
    online_raw_stage: Path | None = None
    raw_bytes: bytes | None = None
    try:
        if from_raw is None:
            # The official client discovers tools/list and validates this empty
            # argument object against the live schema. Never invent parameters.
            raw = asyncio.run(fetch_campaign({}))
            raw_bytes = _json_bytes(raw)
            online_raw_stage = _stage_bytes(output_root / "private/campaign-raw.json", raw_bytes)
            raw_path = online_raw_stage
        else:
            raw_path = Path(from_raw)
            raw = _load_raw(raw_path)
        public, status = build_publications(raw, raw_path)
        outputs = {output_root / relative: content for relative, content in public.items()}
        if raw_bytes is not None:
            outputs[output_root / "private/campaign-raw.json"] = raw_bytes
        _publish_atomically(outputs)
        return status
    finally:
        if online_raw_stage is not None:
            online_raw_stage.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从官方 campaign-calendar 同步一次公开日历；原始响应仅保存在 private/。",
        epilog="示例：python scripts/sync_calendar.py --from-raw private/campaign-raw.json",
    )
    parser.add_argument(
        "--from-raw", type=Path,
        help="离线复验已保存的真实 MCP 响应，保留其原始获取时间；省略则在线查询一次。",
    )
    args = parser.parse_args(argv)
    try:
        status = sync_calendar(from_raw=args.from_raw)
    except KeyboardInterrupt:
        print("同步已取消。", file=sys.stderr)
        return 130
    except Exception:
        # Do not stringify JSON, SDK, filesystem, or transport errors; those
        # exceptions may contain private payloads or credential-bearing context.
        print("同步失败，未完成发布；请检查输入、连接或输出目录。", file=sys.stderr)
        return 2
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
