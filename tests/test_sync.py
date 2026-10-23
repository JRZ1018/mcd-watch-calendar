"""Offline synchronization and failure-preservation tests with synthetic data."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from scripts import sync_calendar as sync


def make_raw():
    article = "Synthetic campaign starts October 20; availability is subject to the official rules."
    return {
        "server": "https://mcp.mcd.cn",
        "retrieved_at": "2026-10-23T08:00:00+00:00",
        "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "result": {
            "isError": False,
            "content": [{"type": "text", "text": "## Synthetic campaign\n" + article}],
            "structuredContent": {
                "success": True, "code": 200,
                "traceId": "PRIVATE-TRACE-MARKER",
                "data": {
                    "subscribedEvents": [{"account": "PRIVATE-ACCOUNT-MARKER"}],
                    "dailyList": [{"date": "2026-10-23", "events": [{
                        "activityCode": "synthetic-campaign",
                        "resourceId": "synthetic-resource",
                        "price": "0",
                        "subscribeScene": "PRIVATE-SUBSCRIPTION-MARKER",
                        "articleDto": {
                            "title": "Synthetic campaign", "content": article,
                            "appJumpUrl": "app://PRIVATE-APP-MARKER",
                            "imgList": ["https://example.invalid/PRIVATE-IMAGE-MARKER"],
                        },
                    }]}],
                },
            },
        },
    }


class SyncCalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw_path = self.root / "private/input.json"
        self.raw_path.parent.mkdir()
        self.write_raw(make_raw())

    def tearDown(self):
        self.temp.cleanup()

    def write_raw(self, raw):
        self.raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def snapshot_public(self):
        return {name: (self.root / name).read_bytes() for name in sync.PUBLIC_PATHS}

    def seed_public(self):
        for relative in sync.PUBLIC_PATHS:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(("original:" + relative).encode())
        return self.snapshot_public()

    def test_offline_sync_publishes_only_whitelisted_data_and_paths(self):
        status = sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(status["event_count"], 1)
        self.assertEqual(status["day_count"], 1)
        self.assertEqual(status["retrieved_at"], "2026-10-23T08:00:00+00:00")
        self.assertEqual(set(status), {
            "mode", "server", "tool", "retrieved_at", "event_count", "day_count",
            "range_start", "range_end",
        })
        created = {str(path.relative_to(self.root)).replace(os.sep, "/")
                   for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(created, set(sync.PUBLIC_PATHS) | {"private/input.json"})
        public = self.snapshot_public()
        for payload in public.values():
            for marker in (b"PRIVATE-", b"traceId", b"subscribedEvents", b"appJumpUrl", b"imgList"):
                self.assertNotIn(marker, payload)
        events = json.loads(public["docs/events.json"])
        self.assertEqual(set(events), {"mode", "retrieved_at", "events"})
        self.assertEqual(set(events["events"][0]), {
            "id", "title", "start", "end", "description", "source_text",
        })
        receipt = json.loads(public["evidence/live-verification.json"])
        self.assertEqual(receipt["raw_sha256"], hashlib.sha256(self.raw_path.read_bytes()).hexdigest())
        self.assertEqual(receipt["normalized_sha256"], hashlib.sha256(public["docs/events.json"]).hexdigest())
        self.assertTrue(receipt["source_text_verified"])
        self.assertTrue(receipt["calendar_dates_are_display_dates"])
        self.assertEqual(receipt["retrieved_at"], status["retrieved_at"])
        self.assertIn(b"BEGIN:VEVENT\r\n", public["docs/calendar.ics"])

    def test_business_failure_preserves_every_previous_public_file(self):
        before = self.seed_public()
        raw = make_raw()
        raw["result"]["structuredContent"]["success"] = False
        self.write_raw(raw)
        with self.assertRaises(ValueError):
            sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(self.snapshot_public(), before)

    def test_topic_feeds_filter_name_and_preserve_shared_event_uids(self):
        raw = make_raw()
        prototype = raw["result"]["structuredContent"]["data"]["dailyList"][0]["events"][0]
        campaigns = []
        for index, keyword in enumerate(("早餐", "麦咖啡", "联名")):
            campaign = deepcopy(prototype)
            campaign["activityCode"] = f"synthetic-topic-{index}"
            campaign["articleDto"].update(title=keyword + "合成示例", content=keyword + "合成原文，不代表真实活动。")
            campaigns.append(campaign)
        raw["result"]["structuredContent"]["data"]["dailyList"][0]["events"] = campaigns
        raw["result"]["content"][0]["text"] = "\n".join(c["articleDto"]["content"] for c in campaigns)
        self.write_raw(raw)
        sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        main = (self.root / "docs/calendar.ics").read_bytes().decode().replace("\r\n ", "")
        main_uids = {line for line in main.split("\r\n") if line.startswith("UID:")}
        for path, (keyword, label) in sync.TOPIC_FEEDS.items():
            content = (self.root / path).read_bytes().decode()
            unfolded = content.replace("\r\n ", "")
            self.assertEqual(content.count("BEGIN:VEVENT\r\n"), 1)
            self.assertIn("X-WR-CALNAME:麦麦不忘 · " + label + "\r\n", content)
            self.assertIn("SUMMARY:" + keyword + "合成示例", unfolded)
            uids = {line for line in unfolded.split("\r\n") if line.startswith("UID:")}
            self.assertEqual(len(uids), 1)
            self.assertTrue(uids.issubset(main_uids))
            for line in content.split("\r\n"):
                self.assertLessEqual(len(line.encode("utf-8")), 75)

    def test_missing_structure_does_not_become_an_empty_success(self):
        before = self.seed_public()
        raw = make_raw()
        del raw["result"]["structuredContent"]["data"]["dailyList"]
        self.write_raw(raw)
        with self.assertRaises(ValueError):
            sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(self.snapshot_public(), before)

    def test_source_verification_failure_preserves_publication(self):
        before = self.seed_public()
        raw = make_raw()
        raw["result"]["content"] = [{"type": "text", "text": "Unrelated response"}]
        self.write_raw(raw)
        with self.assertRaises(ValueError):
            sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(self.snapshot_public(), before)

    def test_empty_activity_query_is_a_valid_zero_event_publication(self):
        raw = make_raw()
        raw["result"]["structuredContent"]["data"]["dailyList"] = []
        self.write_raw(raw)
        status = sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(status["event_count"], 0)
        self.assertEqual(status["day_count"], 0)
        self.assertIsNone(status["range_start"])
        self.assertIsNone(status["range_end"])
        self.assertNotIn("BEGIN:VEVENT", (self.root / "docs/calendar.ics").read_text())

    def test_staging_failure_preserves_all_original_bytes(self):
        before = self.seed_public()
        real_stage = sync._stage_bytes
        calls = 0

        def fail_later(target, content):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError("Synthetic disk write failure")
            return real_stage(target, content)

        with patch.object(sync, "_stage_bytes", side_effect=fail_later):
            with self.assertRaises(OSError):
                sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(self.snapshot_public(), before)
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_replace_failure_rolls_back_all_previously_replaced_files(self):
        before = self.seed_public()
        real_replace = os.replace
        calls = 0

        def fail_second_replace(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Synthetic replace failure")
            return real_replace(source, target)

        with patch.object(sync.os, "replace", side_effect=fail_second_replace):
            with self.assertRaises(OSError):
                sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertEqual(self.snapshot_public(), before)
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_replace_failure_removes_newly_created_files(self):
        real_replace = os.replace
        calls = 0

        def fail_second_replace(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Synthetic replace failure")
            return real_replace(source, target)

        with patch.object(sync.os, "replace", side_effect=fail_second_replace):
            with self.assertRaises(OSError):
                sync.sync_calendar(from_raw=self.raw_path, output_root=self.root)
        self.assertFalse(any((self.root / name).exists() for name in sync.PUBLIC_PATHS))

    def test_online_sync_calls_only_fetch_with_empty_arguments_and_caches_privately(self):
        raw = make_raw()
        original = deepcopy(raw)
        query = AsyncMock(return_value=raw)
        with patch.object(sync, "fetch_campaign", query):
            status = sync.sync_calendar(output_root=self.root)
        query.assert_awaited_once_with({})
        self.assertEqual(raw, original)
        self.assertEqual(status["event_count"], 1)
        cached = self.root / "private/campaign-raw.json"
        self.assertEqual(json.loads(cached.read_bytes()), raw)
        receipt = json.loads((self.root / "evidence/live-verification.json").read_bytes())
        self.assertEqual(receipt["raw_sha256"], hashlib.sha256(cached.read_bytes()).hexdigest())
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_live_schema_failure_does_not_guess_arguments_or_replace_outputs(self):
        before = self.seed_public()
        query = AsyncMock(side_effect=ValueError("Required live argument missing"))
        with patch.object(sync, "fetch_campaign", query):
            with self.assertRaises(ValueError):
                sync.sync_calendar(output_root=self.root)
        query.assert_awaited_once_with({})
        self.assertEqual(self.snapshot_public(), before)
        self.assertFalse((self.root / "private/campaign-raw.json").exists())

    def test_main_failure_is_nonzero_and_does_not_print_raw_exception(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(sync, "sync_calendar", side_effect=RuntimeError("PRIVATE-SECRET")),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = sync.main(["--from-raw", str(self.raw_path)])
        self.assertNotEqual(code, 0)
        self.assertNotIn("PRIVATE-SECRET", stdout.getvalue() + stderr.getvalue())

    def test_help_runs_from_an_unrelated_working_directory_without_network(self):
        process = subprocess.run(
            [sys.executable, str(Path(sync.__file__).resolve()), "--help"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--from-raw", process.stdout)


if __name__ == "__main__":
    unittest.main()
