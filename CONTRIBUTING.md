# 贡献指南

感谢你对 AI 小说写作辅助 Agent 的关注！本文档将帮助你了解如何参与项目开发。

## 行为准则

本项目遵循 [Contributor Covenant](https://www.contributor-covenant.org/) 行为准则。参与即表示你同意遵守其条款。

## 贡献者许可协议 (CLA)

**在提交任何代码之前，你必须签署贡献者许可协议。**

请仔细阅读 [CLA.md](./CLA.md)。本项目的 CLA 采用**版权转让制**：贡献的著作财产权在提交时即转让给版权持有者（徐俊瑞），版权持有者拥有贡献的完整处置权（含商业闭源再许可）。在本项目的 Pull Request 中勾选 CLA 确认框，即视为你已阅读并同意该协议的全部条款。

> ⚠️ 未签署 CLA 的 Pull Request 将不会被合并。

## 如何贡献

### 报告 Bug

1. 在 [Issues](../../issues) 中搜索是否已有相同问题
2. 使用 **Bug Report** 模板创建新 Issue
3. 包含以下信息：
   - 运行环境（OS、Python 版本、Node.js 版本）
   - 复现步骤
   - 预期行为 vs 实际行为
   - 相关日志片段

### 提出功能建议

1. 在 [Issues](../../issues) 中搜索是否已有类似建议
2. 使用 **Feature Request** 模板创建新 Issue
3. 描述功能的使用场景和预期效果

### 提交代码

#### 开发环境设置

```bash
# 1. 克隆项目
git clone https://github.com/Mikexujunrui/AnySpark.git
cd AnySpark

# 2. 配置真实模型
cp .env.example .env    # 填入你的 DEEPSEEK_API_KEY

# 3. 安装后端依赖（uv workspace）
uv sync

# 4. 安装前端依赖
cd frontend && npm ci && cd ..
```

#### 分支与提交

1. 从 `main` 创建功能分支：`git checkout -b feature/your-feature`
2. 小步提交，每个逻辑改动独立提交
3. 提交信息清晰描述改动内容

#### 代码规范（提交前必跑）

```bash
# 总闸：ruff + mypy + pytest + tsc + eslint + build（自动按改动面分层）
uv run python scripts/gate.py

# 只跑 Python 层
uv run python scripts/gate.py --python

# 只跑前端层
uv run python scripts/gate.py --frontend
```

- Python：遵循 `pyproject.toml` 中的 ruff 规则与 mypy 类型检查
- 前端：遵循 `frontend/` 下的 eslint 与 TypeScript 检查
- 新增包必须同步注册（workspace members / mypy files / ruff src / gate py_pkgs / pytest testpaths）

#### Pull Request 流程

1. 提交前确保总闸通过
2. Push 分支后创建 PR，描述改动目的与验证方式
3. 在 PR 中勾选 **CLA 确认框**
4. 等待评审与合并

---

## 感谢

你的每一份贡献都会让火花更亮。🔥
