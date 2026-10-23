"""Synthetic offline fixtures; no saved official response is bundled here."""

from copy import deepcopy
import json
import unittest

from mcd_watch.normalize import NormalizationError, normalize_campaign


def make_raw():
    article_text = "合成活动说明：2026年10月20日起供应，数量有限，以门店为准。"
    return {
        "server": "https://mcp.mcd.cn",
        "retrieved_at": "2026-10-23T08:00:00+00:00",
        "schema": {"type": "object"},
        "result": {
            "isError": False,
            "content": [{
                "type": "text",
                "text": "## 合成活动\n\n" + article_text + "\n\n日历展示日期另列。",
            }],
            "structuredContent": {
                "success": True,
                "code": 200,
                "message": "合成成功消息",
                "data": {
                    "subscribedEvents": [{"accountMarker": "must-not-copy"}],
                    "dailyList": [{
                        "date": "2026-10-23",
                        "dateText": "合成展示标签",
                        "events": [{
                            "activityCode": "synthetic-campaign",
                            "resourceId": "synthetic-resource",
                            "price": "0",
                            "subscribeScene": "must-not-copy",
                            "articleDto": {
                                "title": "合成活动",
                                "content": article_text,
                                "imgList": ["https://example.invalid/private-image"],
                                "appJumpUrl": "app://must-not-copy",
                            },
                        }],
                    }],
                },
            },
        },
    }


def first_event(raw):
    return raw["result"]["structuredContent"]["data"]["dailyList"][0]["events"][0]


class NormalizeCampaignTests(unittest.TestCase):
    def test_official_structure_becomes_live_calendar_display_entry(self):
        raw = make_raw()
        clean = normalize_campaign(raw)
        self.assertEqual(set(clean), {"mode", "retrieved_at", "events"})
        self.assertEqual(clean["mode"], "live")
        self.assertEqual(clean["retrieved_at"], raw["retrieved_at"])
        event = clean["events"][0]
        self.assertEqual(event["id"], "synthetic-campaign:2026-10-23")
        self.assertEqual(event["title"], "合成活动｜活动日历条目")
        self.assertEqual(event["start"], "2026-10-23")
        self.assertEqual(event["end"], event["start"])
        self.assertIn("官方活动日历的展示日期", event["description"])
        self.assertIn("不代表当天新开售", event["description"])
        self.assertEqual(event["source_text"], first_event(raw)["articleDto"]["content"])
        self.assertIn(event["source_text"], raw["result"]["content"][0]["text"])
        self.assertNotIn("source_url", event)

    def test_no_private_or_unrequested_fields_and_zero_price_is_not_free(self):
        clean = normalize_campaign(make_raw())
        exported = json.dumps(clean, ensure_ascii=False)
        for forbidden in (
            "must-not-copy", "private-image", "subscribedEvents", "subscribeScene",
            "appJumpUrl", "imgList", "accountMarker", "免费", "price",
        ):
            self.assertNotIn(forbidden, exported)

    def test_each_listed_day_remains_separate(self):
        raw = make_raw()
        days = raw["result"]["structuredContent"]["data"]["dailyList"]
        next_day = deepcopy(days[0])
        next_day["date"] = "2026-10-24"
        days.append(next_day)
        events = normalize_campaign(raw)["events"]
        self.assertEqual(len(events), 2)
        self.assertNotEqual(events[0]["id"], events[1]["id"])
        self.assertEqual([event["start"] for event in events], ["2026-10-23", "2026-10-24"])

    def test_same_day_same_identifier_same_content_is_deduplicated(self):
        raw = make_raw()
        events = raw["result"]["structuredContent"]["data"]["dailyList"][0]["events"]
        events.append(deepcopy(events[0]))
        self.assertEqual(len(normalize_campaign(raw)["events"]), 1)

    def test_same_day_identifier_conflict_fails_without_raw_data(self):
        raw = make_raw()
        events = raw["result"]["structuredContent"]["data"]["dailyList"][0]["events"]
        duplicate = deepcopy(events[0])
        duplicate["articleDto"]["content"] = "private-conflicting-content"
        raw["result"]["content"][0]["text"] += "\nprivate-conflicting-content"
        events.append(duplicate)
        with self.assertRaisesRegex(NormalizationError, "Conflicting") as caught:
            normalize_campaign(raw)
        self.assertNotIn("private-conflicting-content", str(caught.exception))
        self.assertNotIn("synthetic-campaign", str(caught.exception))

    def test_resource_id_is_used_when_activity_code_is_missing(self):
        raw = make_raw()
        del first_event(raw)["activityCode"]
        event = normalize_campaign(raw)["events"][0]
        self.assertEqual(event["id"], "synthetic-resource:2026-10-23")

    def test_empty_daily_list_is_a_valid_empty_calendar(self):
        raw = make_raw()
        raw["result"]["structuredContent"]["data"]["dailyList"] = []
        raw["result"]["content"] = []
        self.assertEqual(normalize_campaign(raw)["events"], [])

    def test_missing_daily_list_is_an_error(self):
        raw = make_raw()
        del raw["result"]["structuredContent"]["data"]["dailyList"]
        with self.assertRaisesRegex(NormalizationError, "dailyList"):
            normalize_campaign(raw)

    def test_failed_business_status_is_an_error(self):
        for changed_field, value in (("success", False), ("success", 1),
                                     ("code", 401), ("code", "200")):
            with self.subTest(field=changed_field, value=value):
                raw = make_raw()
                raw["result"]["structuredContent"][changed_field] = value
                with self.assertRaisesRegex(NormalizationError, "unsuccessful"):
                    normalize_campaign(raw)

    def test_missing_business_status_is_an_error(self):
        raw = make_raw()
        del raw["result"]["structuredContent"]["success"]
        with self.assertRaisesRegex(NormalizationError, "status fields"):
            normalize_campaign(raw)

    def test_tool_error_is_an_error(self):
        raw = make_raw()
        raw["result"]["isError"] = True
        with self.assertRaisesRegex(NormalizationError, "tool reported an error"):
            normalize_campaign(raw)

    def test_unknown_structure_and_server_are_rejected(self):
        for raw in ({}, {"server": "https://example.invalid"},
                    {"server": "https://mcp.mcd.cn", "retrieved_at": "now", "result": {}}):
            with self.subTest(raw=raw):
                with self.assertRaises(NormalizationError):
                    normalize_campaign(raw)

    def test_article_evidence_must_exist_in_one_continuous_text_block(self):
        raw = make_raw()
        content = first_event(raw)["articleDto"]["content"]
        raw["result"]["content"] = [
            {"type": "text", "text": content[:10]},
            {"type": "text", "text": content[10:]},
        ]
        with self.assertRaisesRegex(NormalizationError, "verbatim"):
            normalize_campaign(raw)

    def test_invalid_date_and_timestamp_are_calendar_validation_errors(self):
        for field, value in (("date", "2026-02-30"), ("retrieved_at", "yesterday")):
            with self.subTest(field=field):
                raw = make_raw()
                if field == "date":
                    raw["result"]["structuredContent"]["data"]["dailyList"][0][field] = value
                else:
                    raw[field] = value
                with self.assertRaisesRegex(NormalizationError, "invalid calendar") as caught:
                    normalize_campaign(raw)
                self.assertNotIn(value, str(caught.exception))

    def test_normalization_does_not_mutate_input(self):
        raw = make_raw()
        original = deepcopy(raw)
        normalize_campaign(raw)
        self.assertEqual(raw, original)


if __name__ == "__main__":
    unittest.main()
