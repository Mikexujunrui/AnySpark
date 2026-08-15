# 安全策略

## 支持的版本

| 版本 | 支持状态 |
|------|----------|
| 最新 main 分支 | ✅ 活跃支持 |
| 历史版本 | ❌ 不支持 |

## 报告漏洞

如果你发现安全漏洞，**请不要在公开 Issue 中报告**。

请通过以下方式私下报告：

1. 使用 GitHub 的 [Security Advisories](https://github.com/Mikexujunrui/AnySpark/security/advisories/new) 功能
2. 或直接邮件联系维护者：mikexujunrui@mail.ustc.edu.cn

请在报告中包含：

- 漏洞的详细描述
- 复现步骤
- 受影响版本
- 可能的修复建议（如有）

我们将在 **7 天内** 确认收到报告，并在 **30 天内** 提供修复方案或缓解措施。

## 安全最佳实践

### API 密钥

- 切勿将 `.env` 文件提交到版本控制（已在 `.gitignore` 中排除）
- 定期轮换 API 密钥
- 不要在任何 Issue / PR / 讨论中粘贴真实密钥

### 用户数据

- 所有用户数据（小说、章节、图谱、配置）保存在运行时的 `data/` 目录，已在 `.gitignore` 中排除
- 备份请直接复制整个 `data/` 目录
- 安装版用户数据位于 `%APPDATA%\AnySpark\data`（Windows）/ `~/Library/Application Support/AnySpark/data`（macOS）

### 依赖安全

- 定期运行 `uv pip list --outdated` 和 `npm outdated` 检查依赖更新
- 关注 [GitHub Dependabot alerts](../../security/dependabot) 中的安全警告
