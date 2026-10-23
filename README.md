# 麦麦不忘 · McD Watch Calendar

[在线体验](https://jrz1018.github.io/mcd-watch-calendar/) · [订阅日历](https://jrz1018.github.io/mcd-watch-calendar/calendar.ics) · [报名申请](https://github.com/M-China/mcd-developer-innovation-challenge/issues/1096)

把麦当劳官方活动日历变成可订阅、可导入的日历，让活动信息出现在平时查看日程的地方。

本项目面向希望集中查看活动、按关键词筛选信息的用户。配套 [Skill](skills/mcd-watch-calendar/SKILL.md) 调用麦当劳中国 MCP，保留来源原文，生成标准 `.ics` 日历和 Markdown 摘要。也可以直接运行 Python 命令，无需模型 API。

这是麦当劳程序员创意开发大赛的独立参赛作品，非麦当劳官方产品。开发工具为 Codex；未申报 WorkBuddy 专项奖励。

## 能做什么

- 只查询官方 `campaign-calendar`，把返回的日历条目整理为全天日程。
- 按关键词、日期筛选，查看前后快照中新增、变更、移除的条目。
- 导出 `.ics`、Markdown 和结构化 JSON；同一条目的 UID 保持稳定。
- 使用 GitHub Actions 每 6 小时尝试更新公开日历；查询或校验失败时保留上次成功的文件。

**日期含义：日程日期是官方活动日历的展示日期，不代表当天开售、领券截止或活动结束。** 同一活动在多个展示日期出现时，会生成多个条目。原文中的适用条件、开售日期、门店范围等仍以麦当劳官方渠道为准。本项目不领券、不下单、不兑换积分。

## 查看与订阅

访问 [日历主页](https://jrz1018.github.io/mcd-watch-calendar/)，或把以下地址添加到支持 URL 订阅的日历客户端：

```text
https://jrz1018.github.io/mcd-watch-calendar/calendar.ics
```

站点已部署，订阅文件已验证返回 HTTP 200 和 `text/calendar`。也可以从仓库下载 [calendar.ics](docs/calendar.ics)，或阅读 [文字摘要](docs/calendar.md)。

只想关注某类活动，可以在主页切换主题后复制订阅地址，或直接使用 [早餐](https://jrz1018.github.io/mcd-watch-calendar/feeds/breakfast.ics)、[咖啡](https://jrz1018.github.io/mcd-watch-calendar/feeds/coffee.ics)、[联名周边](https://jrz1018.github.io/mcd-watch-calendar/feeds/collabs.ics) 日历。主题按标题和来源原文关键词筛选；网页的自由搜索及日期开关只影响列表，不改变订阅内容。

订阅刷新可能延迟，刷新频率和提醒通知由日历客户端控制；导入一个下载的 `.ics` 文件只获得当时的快照。项目没有常驻后台进程，不承诺实时提醒。日历覆盖当次官方响应的范围，不保证全年或全部门店活动。

2026 年 10 月 23 日已完成一次真实 MCP 查询与本地核对：**27 条活动日历条目，覆盖 12 个展示日期**。这不是 27 个独立活动的计数。后续结果以 [当前状态](docs/status.json) 的获取时间为准；验证摘要见 [evidence/live-verification.json](evidence/live-verification.json)。

## 本地开始

需要 Python 3.12 或更高版本。以下命令用于 Windows PowerShell；始终调用虚拟环境解释器，无需修改脚本执行策略。

```powershell
git clone https://github.com/JRZ1018/mcd-watch-calendar.git
cd mcd-watch-calendar
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

先用随项目提供的合成数据离线体验，不需要 Token：

```powershell
.\.venv\Scripts\python.exe -m mcd_watch export --input examples/events.demo.json --out private/demo-calendar
```

得到 `private/demo-calendar.ics` 和 `private/demo-calendar.md`。演示数据及导出标题均明确标记“模拟演示”，不代表真实活动或优惠。

### 查询真实活动

在 [麦当劳 MCP 开放平台](https://open.mcd.cn/mcp) 使用手机号验证登录，进入控制台激活 MCP Token。交互终端中的 `discover`、`fetch` 会提示隐藏输入 Token；也可通过环境变量 `MCD_MCP_TOKEN` 提供。不要把真实 Token 写入项目文件、命令示例或提交记录。[配置示例](mcp-config.example.json) 仅使用环境变量占位符，客户端需自行支持相应替换方式。

```powershell
.\.venv\Scripts\python.exe -m mcd_watch discover --out private/schema.json
.\.venv\Scripts\python.exe -m mcd_watch fetch --out private/campaign-raw.json
.\.venv\Scripts\python.exe -m mcd_watch normalize --input private/campaign-raw.json --out private/events.live.json
.\.venv\Scripts\python.exe -m mcd_watch export --input private/events.live.json --evidence private/campaign-raw.json --out private/live-calendar
```

`fetch` 默认参数为 `{}`，使用当次连接发现的 schema 验证后再查询。原始响应只保存在已忽略的 `private/`，`normalize` 只保留活动字段；导出真实日历时必须提供原始记录进行原文核对。接口结构发生变化时会报错，需重新核对，不能把失败结果当成“没有活动”。

筛选导出的例子：

```powershell
.\.venv\Scripts\python.exe -m mcd_watch export --input private/events.live.json --evidence private/campaign-raw.json --out private/filtered --keyword 早餐 --starts-after 2026-10-23 --ends-before 2026-10-31
```

用 `--previous 上次快照.json` 生成活动变化的 `.changes.json`。日期筛选按区间重叠保留条目；官方响应转换的条目均为其展示日期当天。

### 更新公开日历

一次完成在线查询、规范化和公开文件生成：

```powershell
.\.venv\Scripts\python.exe scripts/sync_calendar.py
```

已有本地原始响应时，可离线复验并重新生成：

```powershell
.\.venv\Scripts\python.exe scripts/sync_calendar.py --from-raw private/campaign-raw.json
```

输出为 `docs/calendar.ics`、`docs/calendar.md`、`docs/events.json`、`docs/status.json` 和公开验证摘要。只发布活动字段，不发布账户订阅状态、原始响应或凭证。

部署自己的订阅源时，在仓库 Actions Secret 中设置 `MCD_MCP_TOKEN`，启用定时工作流和 GitHub Pages。计划任务每 6 小时尝试运行，也可手动触发；实际运行和日历客户端刷新均可能延迟。使用自己的仓库时，请把页面和文档中的订阅地址改为自己的部署地址。

## 检查与来源

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m mcd_watch preflight
```

测试使用合成数据，覆盖日期校验、ICS 转义与折行、UID、筛选、响应规范化及只读客户端行为。`preflight` 检查参赛文件、官方声明原文和真实查询摘要；它不能替代官方参赛资格审核或报名成功回复。

接入与核验细节见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。活动规则见 [官方赛事仓库](https://github.com/M-China/mcd-developer-innovation-challenge)，接口说明见 [官方 MCP 仓库](https://github.com/M-China/mcd-mcp-server)。

## 许可

原创代码和文档采用 [MIT License](LICENSE)。麦当劳商标、官方服务内容及原样保留的 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md) 不在本项目的授权范围内，适用其权利人的条款。输出仅供信息整理参考。
