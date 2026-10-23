"""Regression checks for reviewed input and interoperable calendar output."""

from copy import deepcopy
import json
from pathlib import Path
import re
import unittest
import uuid

from mcd_watch.calendar import (diff_documents, load_events, to_ics,
                                to_markdown, validate_document)


def document(mode="demo"):
    return {
        "mode": mode,
        "retrieved_at": "2026-10-23T12:30:45+08:00",
        "events": [{
            "id": "reviewed-001", "title": "模拟早餐提醒",
            "start": "2026-10-24", "end": "2026-10-26",
            "description": "仅用于模拟演示，不代表真实活动。",
            "source_text": "模拟资料：10月24日至26日的演示记录。",
            "source_url": "https://example.com/demo?item=1&region=cn",
        }],
    }


def unfold(text):
    return text.replace("\r\n ", "")


class ValidationTests(unittest.TestCase):
    def test_normalizes_defaults_without_mutation(self):
        data = document()
        del data["events"][0]["end"]
        data["events"][0]["description"] = "第一行\r\n第二行"
        clean = validate_document(data)
        self.assertEqual(clean["events"][0]["end"], "2026-10-24")
        self.assertEqual(clean["events"][0]["description"], "第一行\n第二行")
        self.assertNotIn("end", data["events"][0])

    def test_invalid_fields(self):
        changes = [
            ("id", ""), ("title", "  "), ("title", "x" * 501),
            ("source_text", " "), ("start", "2026-02-30"),
            ("start", "20261024"), ("end", "2026-10-23"),
            ("description", "contains\ttab"), ("description", "lone\rcarriage"),
            ("source_text", "null\0"), ("title", "line\nbreak"),
            ("title", "del\x7f"), ("title", "surrogate\ud800"),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=repr(value)):
                data = document()
                data["events"][0][key] = value
                with self.assertRaises(ValueError):
                    validate_document(data)

    def test_duplicate_ids_after_trimming(self):
        data = document()
        second = deepcopy(data["events"][0])
        second["id"] = " reviewed-001 "
        data["events"].append(second)
        with self.assertRaisesRegex(ValueError, "duplicate event id"):
            validate_document(data)

    def test_timezone_required_and_validated(self):
        invalid = ["2026-10-23T12:00:00", "2026-02-30T12:00:00+08:00",
                   "2026-10-23T25:00:00+08:00", "2026-10-23T12:00:00+24:00",
                   "2026-10-23T12:00:00+08:60", "2026-10-23", "not a time"]
        for timestamp in invalid:
            with self.subTest(timestamp=timestamp):
                data = document()
                data["retrieved_at"] = timestamp
                with self.assertRaises(ValueError):
                    validate_document(data)
        data = document()
        data["retrieved_at"] = "2026-10-23T04:30:45Z"
        self.assertIn("DTSTAMP:20261023T043045Z", to_ics(data))

    def test_schema_and_mode(self):
        for data in (None, [], {}, {**document(), "extra": 1},
                     {**document(), "mode": "real"}, {**document(), "mode": []},
                     {**document(), "events": {}}, {**document(), "events": [None]}):
            with self.subTest(data=repr(data)):
                with self.assertRaises(ValueError):
                    validate_document(data)
        data = document()
        data["events"][0]["unreviewed"] = True
        with self.assertRaises(ValueError):
            validate_document(data)

    def test_urls_are_absolute_and_noninjectable(self):
        invalid = ["http://example.com/", "javascript:alert(1)",
                   "https://user:secret@example.com/", "https:///missing-host",
                   "https://example.com/\r\nEND:VEVENT",
                   "https://example.com/%0aBEGIN:VEVENT", "https://example.com/a b",
                   "https://example.com/\\bad", "https://example.com/<tag>",
                   "https://example.com:99999/", "//example.com/"]
        for url in invalid:
            with self.subTest(url=url):
                data = document("live")
                data["events"][0]["source_url"] = url
                with self.assertRaises(ValueError):
                    validate_document(data)

    def test_load_utf8_bom_and_reject_duplicate_keys(self):
        path = Path(__file__).resolve().parent / f".calendar-{uuid.uuid4().hex}.json"
        try:
            path.write_text(json.dumps(document(), ensure_ascii=False), encoding="utf-8-sig")
            self.assertEqual(load_events(path)["mode"], "demo")
            path.write_text('{"mode":"demo","mode":"live"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_events(path)
            path.write_text("{invalid JSON", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_events(path)
        finally:
            path.unlink(missing_ok=True)


class ICalendarTests(unittest.TestCase):
    def test_all_day_inclusive_end_and_utc_stamp(self):
        result = unfold(to_ics(document()))
        self.assertIn("DTSTART;VALUE=DATE:20261024\r\n", result)
        self.assertIn("DTEND;VALUE=DATE:20261027\r\n", result)
        self.assertIn("DTSTAMP:20261023T043045Z\r\n", result)
        self.assertNotIn("TZID", result)

    def test_single_day_and_year_transition(self):
        data = document()
        data["events"][0]["start"] = "2026-12-31"
        del data["events"][0]["end"]
        self.assertIn("DTEND;VALUE=DATE:20270101", to_ics(data))

    def test_uid_is_stable_and_namespaces_are_separate(self):
        data = document()
        first = re.search(r"UID:(.+)", unfold(to_ics(data))).group(1)
        data["events"][0]["title"] = "修改标题"
        data["retrieved_at"] = "2026-10-24T15:00:00+08:00"
        second = re.search(r"UID:(.+)", unfold(to_ics(data))).group(1)
        self.assertEqual(first, second)
        data["mode"] = "live"
        third = re.search(r"UID:(.+)", unfold(to_ics(data))).group(1)
        self.assertNotEqual(first, third)

    def test_crlf_and_utf8_folding(self):
        data = document()
        data["events"][0]["title"] = "中文麦麦提醒" * 40
        data["events"][0]["description"] = "这是很长的来源描述。" * 60
        result = to_ics(data)
        self.assertTrue(result.endswith("\r\n"))
        self.assertNotIn("\n", result.replace("\r\n", ""))
        self.assertNotIn("\r", result.replace("\r\n", ""))
        for line in result.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)
        self.assertIn("SUMMARY:【模拟演示】" + data["events"][0]["title"], unfold(result))
        self.assertIn("\r\n ", result)

    def test_text_escaping_and_newline_injection(self):
        data = document()
        data["events"][0]["title"] = "文本,分号;反斜线\\"
        data["events"][0]["description"] = "第一行\nEND:VEVENT\nBEGIN:VEVENT"
        result = unfold(to_ics(data))
        self.assertIn(r"SUMMARY:【模拟演示】文本\,分号\;反斜线\\", result)
        self.assertIn(r"第一行\nEND:VEVENT\nBEGIN:VEVENT", result)
        self.assertEqual(result.count("\r\nBEGIN:VEVENT\r\n"), 1)
        self.assertEqual(result.count("\r\nEND:VEVENT\r\n"), 1)

    def test_demo_is_explicit_and_live_omits_demo_wrapper(self):
        self.assertIn("SUMMARY:【模拟演示】", unfold(to_ics(document())))
        data = document("live")
        data["events"][0]["title"] = "经审核来源活动"
        result = unfold(to_ics(data))
        self.assertIn("SUMMARY:经审核来源活动", result)
        self.assertNotIn("X-WR-CALDESC:", result)

    def test_unrepresentable_exclusive_end_is_explained(self):
        data = document()
        data["events"][0]["start"] = "9999-12-31"
        data["events"][0]["end"] = "9999-12-31"
        with self.assertRaisesRegex(ValueError, "exclusive"):
            to_ics(data)


class FilteringAndDiffTests(unittest.TestCase):
    def test_interval_filters_use_inclusive_overlap(self):
        data = document()
        self.assertIn("BEGIN:VEVENT", to_ics(data, starts_after="2026-10-26"))
        self.assertNotIn("BEGIN:VEVENT", to_ics(data, starts_after="2026-10-27"))
        self.assertIn("BEGIN:VEVENT", to_ics(data, ends_before="2026-10-24"))
        self.assertNotIn("BEGIN:VEVENT", to_ics(data, ends_before="2026-10-23"))
        self.assertIn("BEGIN:VEVENT", to_ics(data, starts_after="2026-10-25",
                                            ends_before="2026-10-25"))
        with self.assertRaises(ValueError):
            to_ics(data, starts_after="2026-10-27", ends_before="2026-10-23")

    def test_keyword_matches_title_description_or_evidence(self):
        data = document()
        data["events"][0]["description"] = "Breakfast"
        self.assertIn("BEGIN:VEVENT", to_ics(data, keyword="breakFAST"))
        self.assertIn("BEGIN:VEVENT", to_ics(data, keyword="演示记录"))
        self.assertNotIn("BEGIN:VEVENT", to_ics(data, keyword="未出现"))

    def test_markdown_is_sorted_escaped_and_filtered(self):
        data = document()
        earlier = deepcopy(data["events"][0])
        earlier.update(id="earlier", title="<script>*示例*", start="2026-10-20",
                       end="2026-10-20")
        data["events"].append(earlier)
        result = to_markdown(data)
        self.assertIn("# 【模拟演示】麦麦不忘日历", result)
        self.assertIn("不代表真实活动或优惠", result)
        self.assertIn("&lt;script&gt;\\*示例\\*", result)
        self.assertLess(result.index("&lt;script&gt;"), result.index("模拟早餐提醒"))
        filtered = to_markdown(data, starts_after="2026-10-25")
        self.assertIn("共 1 项活动", filtered)
        self.assertNotIn("&lt;script&gt;", filtered)
        self.assertIn("当前筛选条件下没有活动", to_markdown(data, keyword="不存在"))

    def test_diff_add_change_remove_and_ignore_fetch_time(self):
        before = document()
        removed = deepcopy(before["events"][0])
        removed["id"] = "removed"
        before["events"].append(removed)
        current = document()
        current["retrieved_at"] = "2026-10-25T10:00:00Z"
        self.assertEqual(diff_documents(current, document()),
                         {"added": [], "changed": [], "removed": []})
        current["events"][0]["description"] += "说明已更新"
        added = deepcopy(current["events"][0])
        added["id"] = "added"
        current["events"].append(added)
        self.assertEqual(diff_documents(current, before),
                         {"added": ["added"], "changed": ["reviewed-001"],
                          "removed": ["removed"]})
        with self.assertRaisesRegex(ValueError, "demo and live"):
            diff_documents(document(), document("live"))


if __name__ == "__main__":
    unittest.main()
