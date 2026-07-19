"""Workflow Agent — generates workflows from user conversation using LLM."""

import json

from .llm_client import chat

WORKFLOW_SYSTEM = """你是一个小说写作工作流规划师。根据用户的写作需求，生成一个多步骤的工作流定义。

# 可用的步骤类型 (type)

## 基础写作类
- extract: 知识提取 — 从用户提供的文本中提取结构化设定
  config: { "text": "提取文本（可留空由用户输入）", "mode": "incremental" }
- write: AI写作 — 在知识约束下生成小说正文
  config: { "instruction": "写作指令", "mode": "strict/suggest", "chapter": "章节名", "ref_chapters": ["#1","#2"] }
  注: ref_chapters 是参考章节，用于参考当前书或参考书的章节内容。
  格式: "#N"（当前书第 N 章） 或 "book_id:#N"（参考书 book_id 的第 N 章，用 list_reference_chapters 查询可用章节）
  用户提到"参考原著"/"参考另一本书的章节"时，必须使用 "book_id:#N" 格式。
- edit: 编辑润色 — 对已有文本进行润色/扩写/缩写
  config: { "instruction": "编辑指令", "mode": "polish/expand/compact" }
- generate_outline: 生成大纲 — 根据当前知识库生成章节大纲
  config: { "instruction": "大纲生成指令" }

## 知识管理类
- search: 搜索知识库 — 检索已有设定和角色信息
  config: { "query": "搜索关键词" }
- validate: 一致性校验 — 检查写作文本是否与知识库一致
  config: { "text": "待校验文本（可留空校验上次写作结果）" }
- plan: 剧情规划 — 根据当前知识库状态提供剧情建议
  config: { "prompt": "规划需求描述" }

## 高保真改写类（原著改写流程）
- read: 读取章节 — 读取当前书或参考书的章节内容
  config: { "chapter_id": "#N", "ref_book_id": "参考书ID（可选）" }
- decompose: 拆解剧情链 — 将章节拆解为结构化场景节点
  config: { "chapter_id": "#N（可选，自动用上一个read的章节）", "ref_book_id": "参考书ID（可选）" }
- annotate: 标注改写模式 — 预览或设置每个节点的改写方式（keep/tweak/rewrite）
  config: { "preview": true/false, "annotations": [{"scene_index": 0, "edit_mode": "tweak", "edit_instructions": "..."}] }
- rewrite: 按链复写 — 根据剧情链逐节点复写章节
  config: { "chain_id": "剧情链ID（可选）", "chapter_title": "输出标题", "style_profile": "风格约束" }
- compare_plot: 情节对比 — LLM对比两个文本的情节差异
  config: { "text_a": "文本A", "text_b": "文本B" }
- diff: 版本差异 — 程序化行级diff对比两个章节版本
  config: { "chapter_a": "#N", "chapter_b": "#M" }

## 用户交互类
- review: 用户审阅 — 暂停等待用户确认（简单场景）
  config: { "message": "提示信息" }
- ask_user: 结构化用户确认 — 带选项的问题（复杂场景）
  config: { "question": "问题文本", "options": ["选项A", "选项B"], "questions": [{"question":"...","options":[{"label":"...","description":"..."}],"multiple":false}] }

# 工作流格式
{
  "name": "工作流名称",
  "steps": [
    {"type": "extract", "label": "步骤说明", "config": {...}},
    ...
  ]
}

# 规则
- 根据用户意图智能组合步骤
- 每个步骤的 label 用简短中文描述
- config 中填写有意义的参数，不要留不相关的空字段
- 如果用户说"参考前文"/"根据前面章节"/"续写"，write 步骤必须包含 ref_chapters
- 如果用户提到"原著"/"参考书"/"另一本书"的章节，ref_chapters 必须用 "book_id:#N" 格式
- 如果用户没说清楚参考来源，先用 list_reference_chapters 查看可用章节，再询问用户要注入哪些

# 典型工作流模板

## 高保真原著改写
read(ref_book_id, #N) → decompose → annotate(preview=true) → ask_user(选择每个节点的处理方式) → annotate(写入确认) → rewrite

## 常规写作+校验
generate_outline → review(确认大纲) → write → validate

## 批量提取+写作
extract → search(验证提取结果) → write

## 版本对比
read(#N) → diff(#N_old, #N_new) → review"""

PASS_SYSTEM = """你是一个小说写作多步骤助手。根据工作流定义逐步执行。

当前工作流步骤执行完毕后的最终结果，需要综合所有步骤的输出给出最终总结。

如果遇到 review 步骤，请生成让用户确认的具体问题和选项。"""


def generate_workflow(user_intent: str, project_context: str = "") -> dict:
    """Generate a workflow definition from user intent."""
    prompt = f"{'当前项目背景：' + project_context[:1000] if project_context else ''}\n\n用户需求：{user_intent}\n\n请生成工作流 JSON："
    response = chat(prompt, system=WORKFLOW_SYSTEM, temperature=0.3, task="workflow")

    try:
        json_str = response.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {
            "name": "自定义工作流",
            "steps": [
                {"type": "write", "label": "AI写作", "config": {"instruction": user_intent, "mode": "strict"}},
                {"type": "validate", "label": "一致性校验", "config": {}},
            ],
        }


def suggest_workflows(prompt: str, available_steps: list[str] | None = None) -> list[dict]:
    """Suggest multiple workflow options based on user prompt."""
    system = """根据用户的写作需求，提供 2-3 个不同的工作流方案建议。
每个方案有不同的侧重点（如：快速写作、完整打磨、深度规划）。

输出 JSON 数组：
[{"name": "方案名", "description": "简短说明", "steps": [{"type": "...", "label": "..."}]}]"""

    response = chat(prompt, system=system, temperature=0.5, task="workflow")
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return []
