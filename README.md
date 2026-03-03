# tiangong-electricity-check
# 自动电费查询（GitHub Actions版）

本项目基于抓包分析，模拟天津工业大学校园网电费查询接口，利用 GitHub Actions 定时执行 Python 脚本，并通过企业微信机器人推送电费余额。支持每天 8:00 和 20:00 自动查询，也可手动触发。

## ✨ 功能特点
- 定时查询：每天 8:00、20:00（北京时间）自动运行。
- 企业微信推送：查询结果（成功或失败）实时推送到企业微信群。
- 低电量提醒：可配置阈值，仅当电量低于阈值时通知（`NOTIFY_MODE=low_balance`），或每次查询都通知（`always`）。
- 安全配置：所有敏感信息（Token、Cookie、Webhook）均通过 GitHub Secrets 加密存储。

## 📁 文件结构
```
.
├── .github/workflows/check-electricity.yml   # GitHub Actions 工作流
├── scripts/check_electricity.py              # 电费查询脚本
└── README.md                                  # 本文件
```

## 🔧 准备工作
你需要从手机抓包工具（如Reqable）获取以下信息：
- **`SYNJONES_AUTH_TOKEN`**：请求头 `synjones-auth` 中 `bearer` 后面的字符串（JWT）。
- **`REQUEST_COOKIE`**：请求头 `Cookie` 的完整内容，例如 `TGC="third_login:xxx"; UserId=xxx`。
- **宿舍参数**：`feeitemid`、`type`、`level`、`campus`、`building`、`floor`、`room`（已从你的抓包中提取默认值，若更换宿舍需修改）。
- **企业微信机器人 Webhook URL**：从企业微信群聊中添加机器人后获得。

## 🔒 GitHub Secrets 配置
将以下变量添加到你的 GitHub 仓库中（Settings → Secrets and variables → Actions）。**所有值必须替换为你自己的真实信息，不可使用示例中的占位符。**

| Secret 名称 | 说明 | 示例（请替换为真实值） |
|------------|------|--------------------------|
| `SYNJONES_AUTH_TOKEN` | JWT Token（不带 `bearer` 前缀） | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `REQUEST_COOKIE` | 完整的 Cookie 字符串 | `TGC="third_login:TGT-xxxxxx..."; UserId=xxxxxx...` |
| `WECOM_WEBHOOK` | 企业微信机器人 Webhook URL | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `AUTHORIZATION` | Basic 认证（通常不变） | `Basic ...` |
| `FEEITEM_ID` | 费用项 ID | `428` |
| `FEE_TYPE` | 类型 | `IEC` |
| `FEE_LEVEL` | 层级 | `4` |
| `CAMPUS` | 校区 | `天津工业大学&天津工业大学` |
| `BUILDING` | 楼栋 ID 和名称 | `20161008...&西苑..号楼` |
| `FLOOR` | 楼层 ID 和名称 | `6&6层` |
| `ROOM` | 房间 ID 和名称 | `20161009...&1栋...` |
| `NOTIFY_MODE` | 通知模式：`always`（每次查询都通知）或 `low_balance`（低于阈值才通知） | `always` |
| `LOW_BALANCE_THRESHOLD` | 低电量阈值（当 `NOTIFY_MODE=low_balance` 时有效） | `10` |

> **注意**：`SYNJONES_AUTH_TOKEN` 和 `REQUEST_COOKIE` 有时效性，过期后需重新抓包更新。其他参数如宿舍信息不变则无需修改。

## 🚀 部署步骤
1. **将本项目文件推送到你的 GitHub 仓库**（确保目录结构正确）。
2. **在仓库中配置上述 Secrets**。
3. **GitHub Actions 会自动启用**，并根据 `.github/workflows/check-electricity.yml` 中的定时任务运行（每天 8:00、20:00 北京时间）。
4. 你也可以**手动触发测试**：在 Actions 页面选择 `Check Electricity` 工作流，点击 `Run workflow`。

## 📨 通知效果示例
成功时收到的消息：
```
【电费提醒】
楼栋：西苑*号楼
房间：*栋***
时间：2026-03-04 08:00:00 UTC+8
剩余电量：55.66 度
```

失败时收到的消息：
```
【电费查询失败】
时间：2026-03-04 20:00:00 UTC+8
错误：业务错误码 500: 未知异常，请联系管理员
```

## ❓ 常见问题
**Q：为什么 GitHub Actions 运行失败，返回 500 错误？**  
A：最常见的原因是 `SYNJONES_AUTH_TOKEN` 或 `REQUEST_COOKIE` 已过期，请重新抓包更新 Secrets。也可能是宿舍参数发生了变化，请核对请求体参数。

**Q：如何修改查询时间？**  
A：编辑 `.github/workflows/check-electricity.yml` 中的 `cron` 表达式（使用 UTC 时间）。例如 `0 0,12 * * *` 对应北京时间 8:00 和 20:00。

**Q：为什么我设置了 `NOTIFY_MODE=low_balance` 但没有收到通知？**  
A：请检查当前电量是否真的低于 `LOW_BALANCE_THRESHOLD`，以及脚本能否正确提取电量数值（查看 Actions 日志中“剩余电量”字段）。

**Q：GitHub Actions 的 IP 会被学校屏蔽吗？**  
A：有可能。如果本地脚本运行正常但 Actions 始终返回 500，可考虑更换 CI 平台（如 Gitee Go、阿里云函数计算）或自行配置代理。本项目暂不包含代理支持，如需可自行添加。

## 📝 许可证
MIT

---

如果仍有问题，欢迎在仓库 Issues 中提出，并提供 Actions 运行日志以便排查。
