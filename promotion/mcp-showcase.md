# McD Watch Calendar: an official MCP campaign calendar as subscribable ICS feeds

## Pre-submission checklist

- [ ] This post follows the MCP community guidelines. Maintainer confirmation is pending before publication, including the AI policy's requirements for human understanding and the submitter's own analysis.

## What would you like to share?

McD Watch Calendar is an independent, open-source client that reads McDonald's China's official `campaign-calendar` MCP tool and publishes an ICS subscription, a small browsing page, Markdown, and a constrained JSON document. It also produces optional breakfast, coffee, and collaboration-themed feeds using explicit keyword filters. It is not an official McDonald's product.

**AI disclosure:** OpenAI Codex assisted development of the implementation, tests, and documentation, and drafted this post. The details below describe source code, automated checks, and recorded query artifacts. They do not establish that the maintainer has completed a full human review or supplied their own analysis for this submission.

### How it works

The Python client uses the official MCP SDK's `ClientSession` and Streamable HTTP transport against the fixed endpoint `https://mcp.mcd.cn`. It initializes the connection, follows `tools/list` pagination, and retrieves only the `campaign-calendar` input schema. Arguments are validated against that schema in the same session before calling the tool. The default query passes `{}`; it fails if the discovered schema requires something else, rather than guessing parameters. No other business tool is called.

The normalizer checks the business success status and the expected `structuredContent.data.dailyList` structure. Article content must occur as a continuous excerpt within an actual MCP text-response block before it can become public source evidence. Missing fields, invalid calendar dates, or conflicting content for the same identifier and day stop the update. A genuine empty `dailyList` is allowed; an error response is not converted into an empty calendar.

### The important date distinction

`dailyList[].date` is treated as the date on which the official calendar **displays** an activity. It is not interpreted as the launch date, a coupon deadline, or the end of a promotion.

Each listed day becomes a separate all-day occurrence. Its title includes “活动日历条目” (activity-calendar entry), and its description explains the date meaning. The source excerpt remains attached so readers can check any launch dates and conditions stated in the article. Repeated appearances on different days are not merged into an inferred validity window. The normalizer also makes no “free” claim from a zero-valued price field.

### Calendar identity and interoperability

An occurrence's identifier combines the activity code, or resource ID fallback, with its display date. ICS UIDs are derived deterministically from that identifier and the live/demo namespace. Re-exporting the same occurrence retains its UID when its title or retrieval timestamp changes. Topic feeds reuse those UIDs and have distinct calendar names.

The exporter uses all-day dates, an exclusive `DTEND`, CRLF line endings, text escaping, and folding at 75 UTF-8 octets without splitting characters. Synthetic tests cover these behaviors, stable UIDs, keyword filtering, and shared UIDs between the full calendar and topic feeds. This is automated coverage, not a claim that every calendar application has been tested.

### Private input, constrained public output

Raw MCP responses stay in the ignored `private/` directory. Tokens come from an environment variable or hidden terminal input. Public event records use an explicit field allowlist; account subscription state, subscription-scene fields, app-jump fields, and image lists are not copied into the published documents.

The public verification receipt contains retrieval time, counts, and file hashes. Its raw-response SHA-256 permits comparison when the private record is available; it is not an official signature or independent attestation.

The updater generates and validates all eight public artifacts before replacing published files. Query or validation failures retain the previous successful output. Replacements are atomic per file, with backups and rollback if a later replacement fails. Tests inject staging and replacement failures and check preservation of previous bytes, alongside privacy-field and source-evidence checks.

GitHub Actions attempts synchronization every six hours and publishes the static files through GitHub Pages. Calendar clients control their own refresh and reminder behavior. A recorded live response on 2026-10-23 produced 27 calendar occurrences across 12 display dates; those are not 27 unique promotions. The linked status file reports the latest published retrieval time.

### Feedback sought

Specific feedback would be useful on the clarity of the display-date labeling, all-day ICS behavior in different clients, and how clients handle one occurrence appearing in both a full feed and a topic feed. The implementation and synthetic fixtures are linked below so these questions can be discussed against concrete behavior.

## Relevant Links

- [Source code](https://github.com/JRZ1018/mcd-watch-calendar)
- [Live page](https://jrz1018.github.io/mcd-watch-calendar/)
- [ICS subscription](https://jrz1018.github.io/mcd-watch-calendar/calendar.ics)
- [Published status](https://jrz1018.github.io/mcd-watch-calendar/status.json)
- [MCP integration and data semantics](https://github.com/JRZ1018/mcd-watch-calendar/blob/main/MCP_INTEGRATION.md)
- [Automated tests](https://github.com/JRZ1018/mcd-watch-calendar/tree/main/tests)
- [Workflow and run history](https://github.com/JRZ1018/mcd-watch-calendar/actions)
- [Public verification receipt](https://github.com/JRZ1018/mcd-watch-calendar/blob/main/evidence/live-verification.json)
