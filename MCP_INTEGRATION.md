# 麦当劳 MCP 接入与核验

本项目将官方活动日历转换为可订阅的 ICS 和可读摘要，使用户在自己的日历中集中查看活动信息。配套 Skill 和 Python 工具使用同一条只读数据流程。

## 实际使用的服务和工具

| 项目 | 使用方式 |
| --- | --- |
| Server | `https://mcp.mcd.cn`，麦当劳中国官方远程 MCP |
| 传输 | Streamable HTTP |
| 身份验证 | `Authorization: Bearer <MCD_MCP_TOKEN>`，从环境变量或隐藏交互输入读取 |
| 能力发现 | `initialize` 后执行 `tools/list`，支持分页，仅提取 `campaign-calendar` 的 `inputSchema` |
| 业务调用 | 仅 `tools/call` → `campaign-calendar` |
| 本次调用参数 | `{}` |

2026 年 10 月 23 日发现的 schema 包含可选 `specifiedDate` 字段；本次没有传入该字段。项目不会依据字段名称自行猜测日期格式或历史查询范围，参数必须先通过同一会话发现的 JSON Schema 校验。默认调用整理官方当前返回的活动日历，不承诺任意月份、全年或全部门店活动。

Token 通过 [官方开放平台](https://open.mcd.cn/mcp) 的手机号登录、控制台激活流程取得。公开的 [mcp-config.example.json](mcp-config.example.json) 只有环境变量占位符；实际替换取决于使用的 MCP 客户端。Token 只用于向固定官方地址鉴权，不写入公开文件。

## 查询、转换和发布流程

1. `mcd_watch/client.py` 连接固定官方地址，发现工具 schema、校验参数，调用 `campaign-calendar`。网络异常和工具错误只输出经过处理的提示，不输出请求头或原始响应。
2. 原始结果保存在本地 `private/`。`mcd_watch/normalize.py` 检查业务成功状态及 `structuredContent.data.dailyList`，只提取展示日期、活动标识、标题和正文。
3. 活动正文必须连续存在于 MCP 文本响应中。缺失字段、无效日期或同一天同一标识内容冲突时停止，不补造日期或活动。
4. `mcd_watch/calendar.py` 生成全天 ICS 和 Markdown。稳定活动标识加展示日期确定 UID；ICS 使用 CRLF、UTF-8 75 字节折行和排他的 `DTEND`。
5. `scripts/sync_calendar.py` 连接上述流程，生成 `docs/calendar.ics`、`docs/calendar.md`、`docs/events.json`、`docs/status.json` 以及 `evidence/live-verification.json`。只有成功后才更新公开文件。

公开输出不复制原始响应中的账号订阅状态、订阅场景、App 跳转链接或图片列表，也不把未解释的 `price` 字段转换为“免费”。项目未调用领券、下单、取消订单、积分兑换或抽奖工具。

**日期语义：** `dailyList[].date` 是活动日历的展示日期，不能据此认定活动当天开售或当天截止。每个展示日期上的活动各自生成一个全天条目，标题附“活动日历条目”，说明中保留该含义和来源正文。同一活动在多天出现时不会合并推断其有效期；活动规则仍以官方原文及实际渠道为准。

GitHub Actions 每 6 小时尝试同步，GitHub Pages 发布固定订阅地址。计划运行可能延迟；文件成功发布后，客户端仍按自己的频率刷新和设置提醒。项目没有常驻后台服务。部署后的日历地址为 `https://jrz1018.github.io/mcd-watch-calendar/calendar.ics`，可用性需以实际 Pages 部署结果为准。

## 2026 年 10 月 23 日真实调用记录

本次真实调用的获取时间为 `2026-10-23T04:29:08.284650+00:00`，即北京时间 12:29:08。调用工具为 `campaign-calendar`，参数 `{}`。规范化并核对后得到 **27 条活动日历条目，覆盖 12 个展示日期**；这不等于 27 个独立活动。

原始响应保留在本地忽略目录，不公开。公开的 [验证摘要](evidence/live-verification.json) 记录获取时间、工具、条目数量和 SHA-256：

```text
本次原始响应 SHA-256
936ca08562d6b8ef1e380a2c33b32b6fee2860322d5a36c0f542bb892c1e54b4
```

此哈希用于持有原始记录时复核文件一致性，不是官方签名或第三方独立认证。摘要和公开日历会随成功同步更新，历史查询时间与当前公开状态应分别阅读。测试目录中的数据均为合成示例，不用来冒充真实查询；演示导出会显式标记“模拟演示”。

## 参赛文件与使用边界

赛事要求的 `README.md`、`MCP_INTEGRATION.md`、`mcp-config.example.json`、源码和官方参赛声明随仓库提供。`CONTEST_DECLARATION.md` 使用官方原文，Git blob SHA 为 `136e76f3160317049f19f5ba03f4d0fedd70fc3c`；`preflight` 会检查其字节内容。

本项目使用 Codex 开发，没有使用 WorkBuddy 开发的记录，因此不提交 `workbuddy.md`，不申报 WorkBuddy 专项奖励。项目为独立参赛作品，非麦当劳官方产品；官方服务内容与商标适用其权利人的条款。

规则与接口依据：[完整赛事规则](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/activityGuidelines.md)、[官方 MCP 使用指南](https://github.com/M-China/mcd-mcp-server)、[官方参赛声明](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/CONTEST_DECLARATION.md)。
