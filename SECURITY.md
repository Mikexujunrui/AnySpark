# 安全策略

## 支持的版本

| 版本 | 支持状态 |
|------|----------|
| 最新 main 分支 | ✅ 活跃支持 |
| 历史版本 | ❌ 不支持 |

## 报告漏洞

如果你发现安全漏洞，**请不要在公开 Issue 中报告**。

请通过以下方式私下报告：

1. 发送邮件至项目维护者（如已设置 security contact）
2. 使用 GitHub 的 [Security Advisories](https://github.com/<owner>/<repo>/security/advisories/new) 功能

请在报告中包含：

- 漏洞的详细描述
- 复现步骤
- 受影响版本
- 可能的修复建议（如有）

我们将在 **7 天内** 确认收到报告，并在 **30 天内** 提供修复方案或缓解措施。

## 安全最佳实践

### API 密钥

- 切勿将 `.env` 文件提交到版本控制（已在 `.gitignore` 中排除）
- 使用强密码保护 Neo4j 数据库
- 定期轮换 API 密钥

### 部署安全

- 生产环境中务必修改 `NEO4J_PASSWORD` 默认密码
- 建议使用反向代理（如 Nginx）启用 HTTPS
- 限制 Neo4j 端口（7474/7687）的对外暴露

### 依赖安全

- 定期运行 `pip list --outdated` 和 `npm outdated` 检查依赖更新
- 关注 [GitHub Dependabot alerts](../../security/dependabot) 中的安全警告
