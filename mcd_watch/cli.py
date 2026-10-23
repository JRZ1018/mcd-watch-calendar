"""CLI for verified official queries, deterministic normalization and export."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DECLARATION_BLOB = "136e76f3160317049f19f5ba03f4d0fedd70fc3c"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_source(document: dict, raw_path: Path) -> str:
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    if raw.get("server") != "https://mcp.mcd.cn" or raw.get("result", {}).get("isError"):
        raise ValueError("原始记录不是成功的官方 MCP 查询。")
    if document["retrieved_at"] != raw.get("retrieved_at"):
        raise ValueError("整理文件的 retrieved_at 必须与原始查询记录一致。")
    result = raw["result"]
    texts = [v.get("text", "") for v in result.get("content", []) if v.get("type") == "text"]
    if "structuredContent" in result:
        texts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    if not texts:
        raise ValueError("原始响应没有可引用的文本或结构化数据，请人工检查。")
    for event in document["events"]:
        if not any(event["source_text"] in text for text in texts):
            raise ValueError("某活动的 source_text 不是原始响应中的连续原文，请核对。")
    return hashlib.sha256(raw_bytes).hexdigest()


def preflight() -> int:
    required = ["README.md", "CONTEST_DECLARATION.md", "MCP_INTEGRATION.md",
                "mcp-config.example.json", "LICENSE", "skills/mcd-watch-calendar/SKILL.md",
                "mcd_watch/client.py", "mcd_watch/calendar.py"]
    missing = [name for name in required if not (ROOT / name).is_file()]
    declaration = ROOT / "CONTEST_DECLARATION.md"
    blob = ""
    if declaration.exists():
        content = declaration.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    receipt = ROOT / "evidence/live-verification.json"
    live = False
    if receipt.exists():
        evidence = json.loads(receipt.read_text(encoding="utf-8"))
        count = evidence.get("event_count")
        live = (evidence.get("mode") == "live" and evidence.get("tool") == "campaign-calendar"
                and type(count) is int and count >= 0 and bool(evidence.get("raw_sha256")))
    report = {"missing_files": missing, "official_declaration_matches": blob == DECLARATION_BLOB,
              "live_receipt_present": live,
              "note": "本地检查不能代替参赛者声明确认、GitHub发布和官方报名成功回复。"}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not missing and blob == DECLARATION_BLOB and live else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="麦麦不忘：从官方活动生成可导入日历")
    sub = parser.add_subparsers(dest="command", required=True)
    discover_parser = sub.add_parser("discover", help="连接官方 MCP，保存 campaign-calendar 参数格式")
    discover_parser.add_argument("--out", type=Path, default=Path("private/schema.json"))
    fetch_parser = sub.add_parser("fetch", help="查询官方活动，私下保存原始结果")
    fetch_parser.add_argument("--arguments", type=Path, help="符合已发现 schema 的 JSON 对象文件")
    fetch_parser.add_argument("--out", type=Path, default=Path("private/campaign-raw.json"))
    normalize_parser = sub.add_parser("normalize", help="将已查询的官方结构化结果转换为日历条目")
    normalize_parser.add_argument("--input", type=Path, default=Path("private/campaign-raw.json"))
    normalize_parser.add_argument("--out", type=Path, default=Path("private/events.live.json"))
    export_parser = sub.add_parser("export", help="导出经核对的活动 JSON 为 ICS 和 Markdown")
    export_parser.add_argument("--input", type=Path, required=True)
    export_parser.add_argument("--out", type=Path, default=Path("private/calendar"))
    export_parser.add_argument("--evidence", type=Path, help="live 模式必须指定原始 MCP 响应")
    export_parser.add_argument("--keyword")
    export_parser.add_argument("--starts-after", help="YYYY-MM-DD，与活动区间重叠则保留")
    export_parser.add_argument("--ends-before", help="YYYY-MM-DD，与活动区间重叠则保留")
    export_parser.add_argument("--previous", type=Path, help="上次整理的快照，用于活动变化对比")
    export_parser.add_argument("--receipt", type=Path, help="另存可公开的无凭证验证摘要")
    sub.add_parser("preflight", help="检查赛事必需文件、官方声明和真实查询摘要")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            return preflight()
        if args.command == "normalize":
            from .normalize import normalize_campaign
            document = normalize_campaign(json.loads(args.input.read_text(encoding="utf-8")))
            verify_source(document, args.input)
            write_json(args.out, document)
            print(f"已整理 {len(document['events'])} 条活动日历条目：{args.out}")
            return 0
        if args.command in ("discover", "fetch"):
            from .client import discover, fetch_campaign
            if args.command == "discover":
                value = asyncio.run(discover())
            else:
                arguments = json.loads(args.arguments.read_text(encoding="utf-8")) if args.arguments else {}
                value = asyncio.run(fetch_campaign(arguments))
            write_json(args.out, value)
            print(f"已保存：{args.out}。请在本地核对，原始响应默认不纳入公开源码。")
            return 0
        from .calendar import load_events, to_ics, to_markdown, diff_documents
        document = load_events(args.input)
        raw_hash = None
        if document["mode"] == "live":
            if not args.evidence:
                raise ValueError("live 模式必须提供 --evidence 原始 MCP 响应。")
            raw_hash = verify_source(document, args.evidence)
        elif args.receipt:
            raise ValueError("模拟数据不能生成真实查询验证摘要。")
        filters = {"keyword": args.keyword, "starts_after": args.starts_after, "ends_before": args.ends_before}
        calendar = to_ics(document, **filters)
        markdown = to_markdown(document, **filters)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.with_suffix(".ics").write_bytes(calendar.encode("utf-8"))
        args.out.with_suffix(".md").write_text(markdown, encoding="utf-8")
        if args.previous:
            write_json(args.out.with_suffix(".changes.json"), diff_documents(document, load_events(args.previous)))
        if args.receipt:
            write_json(args.receipt, {"mode": "live", "server": "https://mcp.mcd.cn",
                       "tool": "campaign-calendar", "retrieved_at": document["retrieved_at"],
                       "raw_sha256": raw_hash, "normalized_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
                       "event_count": len(document["events"]), "exported_at": datetime.now(timezone.utc).isoformat(),
                       "review": "Dates and quoted excerpts reviewed against the private MCP response."})
        print(f"已导出：{args.out.with_suffix('.ics')} 与 {args.out.with_suffix('.md')}")
        print("请自行导入日历并按需设置通知；活动信息以官方实时结果为准。")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"操作未完成：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        from .client import CalendarClientError
        if isinstance(exc, CalendarClientError):
            print(f"操作未完成：{exc}", file=sys.stderr)
            return 2
        # Never dump network exceptions or credential-bearing context.
        print("操作未完成：请检查输入或连接；未输出底层敏感信息。", file=sys.stderr)
        return 2
