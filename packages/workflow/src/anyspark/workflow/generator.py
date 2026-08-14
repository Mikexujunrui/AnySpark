"""
anyspark.workflow.generator — AI 生成工作流定义（skillgen 同款模式）。

设计（DESIGN §12.22，S59）：
- 用户描述目标（"每章写完后检查设定冲突，有问题就改写，再复检"）→ LLM 产出
  流程定义候选（nodes + edges + gate 条件 + loop）→ 进 workflow_drafts 草稿表
  （未生效）→ 人工确认 promote 转正 / delete 拒绝（对齐 skill_drafts 闸门）。
- 生成时注入"节点类型目录"（schema + 用法示例 + 可复用能力清单），让 LLM 产出
  合法流程；校验器检查节点引用完整性/类型合法/条件语法，非法拒收重试。
- 哲学：机制（目录/校验/解析/闸门）硬编码；内容（流程/指令/条件）模型生成。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anyspark.core import Message, Model

from .condition import validate_rule_syntax
from .definition import WorkflowDef

logger = logging.getLogger(__name__)

# 节点类型目录（生成提示注入：LLM 必须产出合法类型）
NODE_CATALOG = """可用节点类型（kind 字段）：
1. agent — 调模型执行写作/审读/查证指令。
   params: {instruction: 该步做什么（自然语言，必填）,
            system_prompt: 可选补充提示,
            output_key: 该步产出存为变量的名字（缺省用节点 id）,
            delegate: 可选——委派子 Agent 执行（该节点获得完整工具循环：
              可自主调用图谱查询/正文检索/资料库/网络搜索等工具后产出）。
              delegate 格式: {scope: {tools: [工具名...]}, budget: {max_turns: 轮数}}
              tools 留空数组 = 全量工具；建议写清需要的工具白名单（如
              ["graph_query","search_chapters","read_material"]）。
              适合"需要查证后写"的复杂节点（如'查图谱确认人物设定后写这段'）；
              纯文本生成（改写/扩写/审读直接输出）用普通 agent 节点即可。}
2. script — 确定性函数（固定逻辑，如读章节/统计/格式化）。
   params: {function: "read_chapter"（读章节正文，chapter_title=章名）
            或其他内置函数, output_key: 产出变量名}
   read_chapter 的产出用 output_key 命名（如 chapter_text），供 agent 引用。
   其他内置函数：
     read_settings — 读本项目设定档（正典设定）。params: {keyword? 过滤, limit? 缺省40}
       产出：文本块（[分类] 名称：内容），供写作 agent 防 OOC/设定冲突。
     read_graph — 读本项目图谱（人物/地点/状态 + 关系）。params: {keyword? 实体名过滤,
       limit? 缺省20按出场章数取Top N}。产出：实体卡片文本块，供跨章一致/伏笔衔接。
     query_reference — 查参考书（分级检索：原文片段 + 项目型参考书的图谱/设定知识层）。
       params: {keyword 必填, max_per_book? 缺省3}。产出：命中文本块（含知识层）。
     list_chapters — 列章节标题。params: 无。
     review_chapter — 审读章节（检测网）。params: {chapter_title}。
     write_chapter — 写回章节。params: {chapter_title, content 或 text_key}。
     noop — 无操作（占位/出口）。
3. approval — 人工确认点（流程暂停等作者判断/批准）。
   params: {prompt: 给作者看的确认问题}
4. gate — 条件分支。出边（edges）带 condition 决定走向。
   出边 condition 两种：
     rule: {"type":"rule","expression":"{{变量}} > 0 AND {{变量2}} == 'yes'"}
           支持 == != > >= < <= AND OR NOT 括号；{{变量}} 引用前面节点输出
     model: {"type":"model","prompt":"自然语言问题（模型判断）"}
   无 condition 的出边 = 默认分支（条件都不满足时走）。
5. loop — 循环。params: {body: [循环体节点 id 列表],
            max_iterations: 最大次数(必填>0 防死循环),
            continue_condition: 继续条件（rule 表达式，为真继续循环；
                                 留空=固定跑满 max_iterations）}
   loop 出边 = 循环结束后走的下一个节点。

边（edges）：[{source: 节点id, target: 节点id, condition?: {...}}]
每个非 gate 节点最多一条出边；gate 可多条（条件路由）。
输出变量可被后续节点/条件引用（gate 条件常引用前置审读节点的输出）。

示例（章节质量把关流程）：
{
  "name": "章节质量把关",
  "description": "审读→有硬伤则改写→复检，直到通过或满3次",
  "nodes": [
    {"id": "n1", "kind": "agent", "label": "审读", "params": {"instruction": "对当前章节做审读，输出'硬伤数: N'和问题清单", "output_key": "review"}},
    {"id": "n2", "kind": "gate", "label": "有无硬伤", "params": {}},
    {"id": "n3", "kind": "agent", "label": "改写", "params": {"instruction": "按审读问题逐条修改章节", "output_key": "fixed"}},
    {"id": "n4", "kind": "approval", "label": "作者确认", "params": {"prompt": "修改结果是否满意？"}}
  ],
  "edges": [
    {"source": "n1", "target": "n2"},
    {"source": "n2", "target": "n3", "condition": {"type": "rule", "expression": "{{review}} contains '硬伤'", "label": "有硬伤"}},
    {"source": "n2", "target": "n4", "condition": {"type": "rule", "expression": "{{review}} not contains '硬伤'", "label": "无硬伤"}},
    {"source": "n3", "target": "n4"}
  ]
}
"""

GENERATE_PROMPT = (
    "你是 AnySpark 的小说写作工作流设计器。根据用户的写作流程需求，"
    "设计一条结构化工作流（顺序 + 分支 gate + 循环 loop）。\n\n"
    "规则：\n"
    "1. 只输出一个 JSON 对象（流程定义），不要解释不要 Markdown 代码块。\n"
    "2. 流程要贴合小说写作场景：审读/查证/改写/伏笔盘点/设定查证/作者确认等。\n"
    "3. 每个节点必须有明确输入输出（output_key），条件表达式引用前面节点的输出。\n"
    "4. 需要循环（如'直到通过'）用 loop 节点，必须写 max_iterations 防死循环。\n"
    "5. 需要作者判断的地方用 approval 节点。\n"
    "6. 节点 id 用 n1/n2/... 形式，简单有序。\n"
    "7. **审读/改写等 agent 节点必须能拿到章节内容**：先用 script 节点"
    "（function=read_chapter，params.chapter_title=章名，output_key=chapter_text）"
    "读章节，agent 节点 instruction 里用 {{chapter_text}} 引用它；"
    "或 agent 节点 params.chapter_title 直接指定章名（自动附正文）。\n"
    "8. 所有 agent 节点 instruction 里的 {{变量}} 都会在运行时被上游输出替换。\n"
    "9. **需要查证后再写的复杂节点用 delegate 委派子 Agent**：agent 节点加\n"
    "   params.delegate={{scope:{{tools:[工具名]}}, budget:{{max_turns: N}}}}——子 Agent\n"
    "   有完整工具循环（graph_query/search_chapters/read_material/search_web 等），\n"
    "   适合'查图谱/查资料/搜资料后产出'；纯文本生成（改写/扩写/审读）用普通\n"
    "   agent 节点（不带 delegate，干净单次调用更省）。\n\n"
    "节点类型目录：\n{node_catalog}\n\n"
    "用户需求：{goal}\n"
)


def _catalog_escaped() -> str:
    """目录文本转义：{instruction} 等花括号不参与 format。"""
    return NODE_CATALOG.replace("{", "{{").replace("}", "}}")


class WorkflowGenerator:
    """从自然语言需求生成工作流定义候选（草稿）。"""

    def __init__(self, model: Model) -> None:
        self._model = model

    def generate(self, goal: str, max_retry: int = 1) -> WorkflowDef:
        """生成单个合法定义；解析/校验失败时重试，仍失败抛错。"""
        prompt = GENERATE_PROMPT.format(node_catalog=_catalog_escaped(), goal=goal)
        last_err = ""
        for attempt in range(max_retry + 1):
            try:
                out = self._model.respond([Message(role="user", content=prompt)], [])
                raw = (out.text or "").strip()
                data = _extract_json(raw)
                definition = WorkflowDef.from_dict(data)
                errors = definition.validate()
                if errors:
                    last_err = "校验失败: " + "; ".join(errors)
                    logger.warning("生成候选校验失败(第%d次): %s", attempt + 1, last_err)
                else:
                    # S71：接线 normalize_condition_expr——补验 rule 条件语法
                    # （此前定义后校验只查结构，AI 生成的 gate 条件表达式语法错误
                    # 会在运行时才炸；此防线曾是无调用方的死代码）
                    return normalize_condition_expr(definition)
            except Exception as exc:
                last_err = str(exc)[:200]
                logger.warning("生成解析失败(第%d次): %s", attempt + 1, last_err)
        raise ValueError(f"生成工作流失败: {last_err}")


def _extract_json(raw: str) -> dict[str, Any]:
    """从模型输出提取 JSON 对象（宽容：剥代码块/前后杂文本）。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # 找第一个 { 到最后一个 } 的闭合
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    raise ValueError("模型输出不含合法 JSON")


def normalize_condition_expr(definition: WorkflowDef) -> WorkflowDef:
    """补验条件语法（供 generate 后的附加校验；不修改定义则原样返回）。"""
    for e in definition.edges:
        if e.condition and e.condition.get("type") == "rule":
            expr = str(e.condition.get("expression") or "")
            errs = validate_rule_syntax(expr)
            if errs:
                raise ValueError(f"边 {e.id} 条件语法错误: {'; '.join(errs)}")
    return definition
