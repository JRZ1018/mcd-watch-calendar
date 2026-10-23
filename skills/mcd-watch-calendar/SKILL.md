---
name: mcd-watch-calendar
description: "查询麦当劳官方 MCP 活动日历，按兴趣与日期筛选，导出带原文证据的 ICS 日历或解释订阅方法。用于活动提醒和活动日历条目整理。"
---

在完整的 mcd-watch-calendar 仓库根目录运行命令。先阅读根目录的 MCP_INTEGRATION.md 了解已验证接口；依赖按 README.md 安装。

用户希望“最近有什么活动”“把早餐活动加到日历”等时：

1. 运行 `python -m mcd_watch discover` 获取 `campaign-calendar` 当前参数格式。Token 从 `MCD_MCP_TOKEN` 或终端隐藏输入读取；聊天中已有凭证可在已授权的本地调用中使用，公开文件仅保留环境变量占位符。
2. 运行 `python -m mcd_watch fetch` 查询默认日历。只有在最新发现的 schema 支持时，才在本地 JSON 文件中提供 `specifiedDate`，通过 `--arguments` 传入；不推测其他参数。
3. 运行 `python -m mcd_watch normalize`。这会将 `dailyList[].date` 转为单日展示条目，保留 `articleDto.content` 原文。展示日期不等于开售日或有效期；`price=0` 不是免费承诺。若结构改变、业务错误或证据缺失，报告失败，不用模拟数据替代真实结果。
4. 根据用户兴趣与日期导出，例如：

   ```powershell
   python -m mcd_watch export --input private/events.live.json --evidence private/campaign-raw.json --out private/breakfast --keyword 早餐 --starts-after 2026-10-23
   ```

   相对日期按北京时间解释，替换示例日期。`--previous` 可比较先前的 live 快照。日期筛选为含边界的区间重叠。
5. 返回 ICS 和 Markdown 路径、条目数、资料获取时间，并说明导入或订阅后由日历客户端控制刷新与通知。未实际导入不能声称已创建用户的日历或后台提醒。

用户要自动订阅时，使用 README 中已部署的 HTTPS feed。需要自行部署时，`python scripts/sync_calendar.py` 会验证查询并生成 `docs/` 下的公开活动文件；仓库 Actions 每六小时尝试更新。只有用户明确要求发布或修改订阅源时才推送修改。

公开交付只包含活动白名单字段与不含凭证的验证摘要。`private/` 中的完整响应可能包含账户相关字段，保留在本地。仅查询 `campaign-calendar`，不调用领券、下单、积分兑换或抽奖等工具。
