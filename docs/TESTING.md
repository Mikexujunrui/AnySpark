# 测试策略指南

> 本文档说明火花的测试分层、运行方式、编写规范和使用模式。当前测试套件覆盖 **34 个测试文件、451+ 个测试用例**。

---

## 快速命令

```bash
# 运行全部测试
pytest

# 运行指定测试文件
pytest tests/test_agent_loop.py

# 运行指定测试类/函数
pytest tests/test_agent_loop.py::test_agent_loop_basic
pytest tests/test_agent_loop.py::TestAgentLoop

# 显示详细输出
pytest -v

# 显示 print 输出（调试用）
pytest -s

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=term

# 运行指定标记的测试
pytest -m slow

# 前序质量门
python -m ruff check src/ tests/
python -m mypy src/ --ignore-missing-imports
```

---

## 测试分层

测试按范围和复杂度分为三层：

### 单元测试（占比 ~70%）

测试纯函数和独立模块逻辑，不依赖外部服务。

| 测试文件 | 覆盖内容 | 用例数 |
|----------|---------|-------|
| `test_config.py` | 配置加载、环境变量解析 | — |
| `test_json_store.py` | JSON 存储 CRUD | — |
| `test_git_store.py` | Git 版本存储操作 | — |
| `test_event_bus.py` | 事件总线发布/订阅 | — |
| `test_pacing_analyzer.py` | 叙事节奏分析算法 | — |
| `test_voice_fingerprint.py` | 角色语言指纹提取 | — |
| `test_dedup.py` | SimHash + Jaccard 查重 | — |
| `test_cost_tracker.py` | Token 成本追踪 | — |
| `test_inspiration_box.py` | 灵感碎片 CRUD | — |
| `test_foreshadow_matcher.py` | TF-IDF 伏笔匹配 | — |
| `test_semantic_diff.py` | 语义 Diff 生成 | — |
| `test_reference_analyzer.py` | 参考书分析引擎 | — |
| `test_skills.py` | 技能加载和执行 | — |
| `test_subagent_plan_guard.py` | 子 Agent 规划守卫 | — |
| `test_agent_types.py` | Agent 类型系统 | — |
| `test_chapter_result.py` | 章节结果处理 | — |
| `test_mode_tracking.py` | 模式追踪 | — |
| `test_edit_ops.py` | 编辑操作原语 | — |
| `test_hallucination.py` | 幻觉检测 | — |
| `test_parts.py` | Part 结构化消息 | — |
| `test_permissions.py` | 权限校验 | — |
| `test_exporter.py` | 导出格式 | — |
| `test_simulation_store.py` | 推演存储 | — |

**特点**：
- 快速（毫秒级），适合频繁运行
- 使用 `pytest` + `tmp_path` 隔离文件系统
- 使用 Monkeypatch 替换配置依赖

### 集成测试（占比 ~20%）

测试模块间交互和 2-3 层调用链。

| 测试文件 | 覆盖内容 |
|----------|---------|
| `test_agent_loop.py` | Agent 主循环 |
| `test_executor_utils.py` | 工具执行器 |
| `test_context_manager.py` | 上下文管理器 |
| `test_workflow_execute.py` | 工作流引擎执行 |
| `test_chapter_dependency.py` | 章节依赖图 |
| `test_continuation.py` | 续写流水线 |
| `test_deep_style.py` | 深度文风分析 |
| `test_ai_flavor_scanner.py` | AI 味扫描引擎 |
| `test_narrative_logic.py` | 叙事逻辑引擎 |
| `test_generation_writing.py` | 写作生成 |
| `test_reference_context.py` | 参考书上下文注入 |
| `test_optimizations.py` | 上下文压缩优化 |

**特点**：
- 中等速度（百毫秒到秒级）
- 使用 `tmp_data_dir` Fixture 隔离数据目录
- 依赖多个模块协同工作

### 系统测试（占比 ~10%）

测试完整业务流程和 API 接口。

| 测试文件 | 覆盖内容 |
|----------|---------|
| `test_autopilot.py` | Autopilot 完整流程 |
| `test_smart_autopilot.py` | 智能 Autopilot 规划 |
| `test_book_transform.py` | 全书批量变换 |
| `test_list_books.py` | 书籍列表 API |
| `test_chat_routes.py` | 聊天路由 |
| `test_volumes.py` | 分卷管理 |
| `test_supervisor.py` | 监督器 |
| `test_scheduler.py` | 调度器 |
| `test_task_queue.py` | 任务队列 |
| `test_search.py` | 搜索功能 |
| `test_plot_chain.py` | 剧情链 |

**特点**：
- 较慢（秒级），标记为 `pytest.mark.slow` 可选
- 测试完整用户场景
- 覆盖前后端 API 接口

---

## 编写规范

### Fixture 使用

所有测试使用 `conftest.py` 中定义的 `tmp_data_dir` Fixture，确保数据隔离：

```python
def test_something(tmp_data_dir):
    """测试不污染真实数据目录。"""
    # 所有数据文件操作会自动重定向到 tmp_path
```

提供的共享 Fixture：

```python
# 示例章节数据
def sample_chapters():
    # 返回 3 章包含标题和内容的示例章节数据

# 示例实体数据
def sample_entities():
    # 返回角色、地点等示例实体
```

### 测试文件命名

```
test_<module_name>.py    # 测试文件命名与源码模块对应
```

### 测试函数命名

```python
def test_<功能描述>():          # 正向测试
def test_<功能描述>_<边界>():    # 边界条件测试
def test_<功能描述>_error():    # 异常/错误路径测试
```

### 断言风格

- 使用原生 `assert` 语句
- 浮点数比较使用 `pytest.approx`
- 异常测试使用 `pytest.raises`

```python
def test_calculate_score():
    result = calculator(data)
    assert result["total"] == 42
    assert len(result["items"]) > 0
    assert result["score"] == pytest.approx(3.14, rel=1e-3)

def test_invalid_input():
    with pytest.raises(ValueError, match="无效参数"):
        validator(None)
```

---

## Mock 模式

### 替换数据目录

```python
def test_with_isolated_storage(tmp_data_dir):
    """tmp_data_dir 自动替换 DATA_DIR，无需手动 clean up。"""
    from core.config import DATA_DIR
    assert str(DATA_DIR) == str(tmp_data_dir)
```

### Mock LLM 调用

对于依赖 LLM 的模块，通过 Monkeypatch 替换 LLM 调用：

```python
def test_agent_loop_basic(tmp_data_dir, monkeypatch):
    async def mock_llm_response(*args, **kwargs):
        return {
            "choices": [{
                "index": 0,
                "message": {
                    "content": "分析完成。",
                    "role": "assistant",
                    "tool_calls": None
                },
                "finish_reason": "stop"
            }]
        }

    monkeypatch.setattr("core.agent_loop.chat", mock_llm_response)
    # 执行测试...
```

---

## 配置

`pytest.ini` 文件：

```ini
[pytest]
testpaths = tests
pythonpath = src
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

关键配置说明：
- `pythonpath = src`：测试时自动将 `src/` 加入 `sys.path`
- `asyncio_mode = auto`：测试函数自动识别为 async 或 sync
- `conftest.py` 中 `sys.path.insert(0, ...)` 确保导入正确

---

## 质量门控

每次 CI 运行的质量门控序列：

```
1. ruff check src/ tests/       # 代码风格和常见错误
2. mypy src/                    # 类型检查
3. pytest                        # 全部测试通过
4. tsc --noEmit                  # 前端类型检查
5. eslint . --max-warnings 90   # 前端代码规范
6. npm run build                 # 前端构建
```

本地提交前建议运行 #1 和 #3 保证基本质量。

---

## 注意事项

1. **不依赖网络**：测试环境不应访问外部服务（LLM API、GitHub 等）
2. **不依赖真实数据**：使用 Fixture 或 Factory 生成测试数据
3. **并行安全**：每个测试用例使用独立的 `tmp_data_dir`，互不干扰
4. **避免文件泄漏**：使用 `tmp_path` 而非硬编码路径
5. **Mock 外部依赖**：LLM、文件系统、网络请求等外部依赖必须 Mock
