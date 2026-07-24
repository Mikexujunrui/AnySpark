# 贡献指南

感谢你对 AI 小说写作辅助 Agent 的关注！本文档将帮助你了解如何参与项目开发。

## 行为准则

本项目遵循 [Contributor Covenant](https://www.contributor-covenant.org/) 行为准则。参与即表示你同意遵守其条款。

## 贡献者许可协议 (CLA)

**在提交任何代码之前，你必须签署贡献者许可协议。**

请仔细阅读 [CLA.md](./CLA.md)。在本项目的 Pull Request 中勾选 CLA 确认框，即视为你已阅读并同意该协议的全部条款。

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
# 1. Clone 项目
git clone <repo-url>
cd novel-agent

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Mac/Linux

# 3. 安装依赖
pip install -r requirements-dev.txt

# 4. 启动 Neo4j
docker run -d --name novel-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/novel_agent_2024! \
  neo4j:5-community

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 6. 安装 pre-commit hooks
pre-commit install

# 7. 启动后端
python -u src/server.py

# 8. 启动前端（新终端）
cd frontend && npm install && npx vite --port 8190
```

#### 代码规范

- **Python**: 遵循 [ruff](https://docs.astral.sh/ruff/) 规则（已配置在 `pyproject.toml` 中）
- **TypeScript/React**: 遵循 ESLint 规则（已配置在 `frontend/eslint.config.js` 中）
- **提交信息**: 使用清晰的描述性提交信息，建议格式：
  ```
  feat: 添加剧情卡片交互功能
  fix: 修复并行写入时 JSON 丢失问题
  docs: 更新 ARCHITECTURE.md 变更记录
  test: 补充 autopilot 模块单元测试
  refactor: 拆分 agent_loop God Function
  ```

#### 提交流程

1. Fork 本仓库
2. 从 `main` 分支创建功能分支：`git checkout -b feat/your-feature`
3. 编写代码并添加测试
4. 确保所有检查通过：
   ```bash
   ruff check src/
   mypy src/ --ignore-missing-imports
   pytest tests/ --cov=src --cov-fail-under=50
   cd frontend && npx eslint . && npx tsc --noEmit
   ```
5. 提交代码并推送
6. 创建 Pull Request，使用 PR 模板描述变更内容

### 测试要求

- 新增功能需包含对应的单元测试
- Bug 修复需包含回归测试
- PR 中 CI 检查必须全部通过
- 目前最低覆盖率要求：50%

### 项目结构速览

```
src/core/       # 核心模块（Agent 循环、知识库、工作流引擎等）
src/routes/     # FastAPI 路由
src/tools/      # Agent 工具集
src/data/       # 数据持久化层
frontend/src/   # React 前端
docs/           # 技术文档
tests/          # 测试代码
```

## 问题反馈

如有任何问题，欢迎在 [Issues](../../issues) 中提出，或通过 Discussions 讨论。
