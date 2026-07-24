# 文档索引

本目录包含项目的全部技术文档。以下为各文档的用途和目标读者。

| 文档 | 目标读者 | 内容 |
|------|----------|------|
| [README.md](../README.md) | 所有人 | 项目概述、功能特性、快速开始、配置说明、API 文档、数据目录说明 |
| [CHANGELOG.md](../CHANGELOG.md) | 所有人 | 版本变更日志，记录所有重要新增/修复/重构 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 贡献者 | 贡献指南：开发环境、代码规范、提交流程、测试要求 |
| [SECURITY.md](../SECURITY.md) | 所有人 | 安全策略与漏洞报告流程 |
| [TECH_STACK.md](TECH_STACK.md) | 开发者 | 实际采用的技术栈（v3.0），前端/后端/数据层/AI/部署 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 开发者、架构师 | 系统架构设计、分层说明、数据主流向、版本变更记录 |
| [MODULES.md](MODULES.md) | 开发者 | 23 个核心模块定义与实现状态，含接口说明和依赖关系 |
| [FRONTEND.md](FRONTEND.md) | 前端开发者 | 前端架构设计、组件目录、状态管理、SSE 交互模式、开发指引 |
| [TESTING.md](TESTING.md) | 贡献者 | 测试分层策略、运行命令、编写规范、Mock 模式 |
| [EXTENDING.md](EXTENDING.md) | 开发者 | 扩展开发指南：插件系统、YAML 技能、文风模板、评审员自定义 |
| [ROADMAP.md](ROADMAP.md) | 项目经理、贡献者 | 开发路线图（历史规划）与版本历史（v4-v12 实施记录） |
| [IMPROVEMENTS.md](IMPROVEMENTS.md) | 贡献者 | 改进跟踪 (36/36 项已完成)，变更日志与新增文件清单 |

## 阅读顺序建议

1. **新成员入门**：README.md → TECH_STACK.md → ARCHITECTURE.md
2. **模块开发**：MODULES.md → ARCHITECTURE.md（对应分层）
3. **前端开发**：FRONTEND.md → api.ts → store.ts
4. **测试编写**：TESTING.md → conftest.py → 对应模块测试文件
5. **扩展开发**：EXTENDING.md → plugins/example_style.py → skills/default.yaml
6. **架构决策**：ARCHITECTURE.md → IMPROVEMENTS.md
7. **规划新功能**：ROADMAP.md → MODULES.md → IMPROVEMENTS.md
8. **参与贡献**：CONTRIBUTING.md → SECURITY.md
