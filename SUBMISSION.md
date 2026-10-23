# 参赛交付记录

作品：**麦麦不忘 · McD Watch Calendar**。基于麦当劳中国官方 MCP，将活动日历展示条目转换为可订阅的 ICS 日历。

## 交付入口

- 在线体验：https://jrz1018.github.io/mcd-watch-calendar/
- 源码仓库：https://github.com/JRZ1018/mcd-watch-calendar
- 版本与源码包：https://github.com/JRZ1018/mcd-watch-calendar/releases/tag/v0.1.0
- 官方报名申请：https://github.com/M-China/mcd-developer-innovation-challenge/issues/1096
- 完整订阅：https://jrz1018.github.io/mcd-watch-calendar/calendar.ics
- 主题订阅：[早餐](https://jrz1018.github.io/mcd-watch-calendar/feeds/breakfast.ics)、[咖啡](https://jrz1018.github.io/mcd-watch-calendar/feeds/coffee.ics)、[联名周边](https://jrz1018.github.io/mcd-watch-calendar/feeds/collabs.ics)

## 图片要求与官方规则核对

以[官方完整活动规则](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/activityGuidelines.md)和[赛事使用指南](https://github.com/M-China/mcd-developer-innovation-challenge)为准。

| 项目 | 要求与完成情况 |
| --- | --- |
| 报名截止 | 北京时间 2026-10-25 23:59；本项目已于 10-23 提交 |
| 定榜 | 北京时间 2026-10-26 00:00 的公开 Star 数据 |
| 项目资格 | 个人 GitHub 公开仓库；仓库于 2026-10-23 创建，处于允许的创建时间范围 |
| 真实 MCP | 已实际完成 campaign-calendar 查询，来源原文逐条核对 |
| 必需材料 | README.md、MCP_INTEGRATION.md、mcp-config.example.json、源码及官方 CONTEST_DECLARATION.md 齐全 |
| 官方声明 | 保留官方原文字节，Git blob SHA：136e76f3160317049f19f5ba03f4d0fedd70fc3c |
| 报名方式 | 已按标准四行格式提交官方 Issue #1096；系统确认状态见下方 |
| WorkBuddy | 普通参赛不强制使用；本项目如实记录 Codex 开发，不申报 WorkBuddy 专项奖励 |
| 排名与奖励 | 按真实公开 Star 排名，Star 为 0 不进入榜单；原则上前 100 个项目及末位并列项目进入奖励范围，另需资格审核 |
| 兑奖截止 | 获奖后须按官方通知，于 2026-11-14 前完成信息提交或兑换 |

## 已验证的结果

- Windows 本地与 GitHub Actions 均通过 **56 项测试**；Skill 校验通过。
- 首次真实查询取得 **27 条日历条目、12 个展示日期**。后续状态与获取时间见 [docs/status.json](docs/status.json)。
- 完整、早餐、咖啡、联名周边四个 ICS 地址均验证 HTTP 200 和 `text/calendar`。部署时条目数分别为 27、7、7、6，后续随成功查询变化。
- 桌面及 390px 手机视口已实际检查；没有水平溢出。搜索、主题筛选、原文展开及订阅地址切换验证通过。
- [云端运行记录](https://github.com/JRZ1018/mcd-watch-calendar/actions/runs/39907736671)确认测试、真实查询、文件更新与 Pages 部署全部成功。
- 原始响应保留在本地忽略目录；公开文件仅包含活动白名单字段。定时任务的访问凭证保存在 GitHub Actions Secret。
- v0.1.0 ZIP 由 Git 跟踪文件生成并通过 CRC 检查，不包含 private 目录。

所有日历日期都是官方的**展示日期**，不是推断的开售日或截止日。同一活动可能在多个日期出现。订阅源每六小时尝试更新，客户端刷新及通知可能延迟。

## 报名确认

申请已于北京时间 **2026-10-23 13:35:31** 提交，官方账号 **M-China-Official** 于 **13:59:18** 回复确认：

> 您的作品已成功参赛，您可以通过官方项目的排行榜.md查看排名

[查看官方成功回执](https://github.com/M-China/mcd-developer-innovation-challenge/issues/1096#issuecomment-6358521537)。成功参赛不代表获奖，最终奖项仍以官方资格审核及定榜结果为准。
