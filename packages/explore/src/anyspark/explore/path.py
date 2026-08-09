"""
anyspark.explore.path — 路径探索（叙事树节点之间串联的小方向探索）。

设计（DESIGN §12.29）：三层探索粒度的中间层——
大方向 explore（整本书怎么写）→ **桥梁 path（A→B 怎么串）** → 场景内 play（这一步做什么）。

输入：起点 A + 终点 B（自然语言，或叙事树节点内容）+ 约束（可选）
输出：N 条候选路径，每条 = 一条中间事件链（A → 事件1 → 事件2 → B）+ 串联说明
机制：单次 LLM 调用自由生成 N 条不同路径（对齐 S65 教训：不硬编码策略集，
提示词引导多样性——直推/铺垫/反转/绕行/视角切换作示例非强制）；用户判别选优。
落点：默认只返回参考文本；archive=true 时把选中路径写入叙事树（candidate）——
不自动污染树，显式才落。

哲学：机制（路径结构/JSON 解析/宽容降级）硬编码；内容（事件链/说明）自然语言。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anyspark.core.types import Message

from .strategy import extract_json_dict

# 路径数范围（默认 4，2-6）
MIN_PATHS = 2
MAX_PATHS = 6

PROMPT_TEMPLATE = """你是小说路径探索器。给定叙事的起点和终点，生成 {n} 条**不同思路**的
中间串联路径候选，供作者选择——每条路径是一串中间事件，把起点自然引到终点。

【起点】
{from_desc}

【终点】
{to_desc}
{constraints_block}
【任务】
站在小说创作角度，生成 {n} 条真正不同的串联路径：
- 每条路径 2-5 个中间事件（A → 事件1 → 事件2 → B），事件用一句动作/变故/发现描述
- 路径之间要真正不同：可直推、多层铺垫、中途反转、旁支绕行、视角切换等——
  方向由你按起点终点的张力自由判断，避免雷同平庸
- 每条附一句 note：说明这条路径的戏剧效果与适合的节奏（如"快速推进，适合想尽快
  进入对峙"），以及 style：给这条路径一个方向标签（如"直接推进/多层铺垫/意外反转/
  旁支绕行"）

输出严格 JSON（不要多余文字）：
{{"paths": [{{"events": ["事件1", "事件2"], "note": "说明", "style": "方向标签"}}]}}"""


@dataclass
class PathCandidate:
    """一条路径候选：中间事件链 + 串联说明。"""

    events: list[str] = field(default_factory=list)
    note: str = ""
    style: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"events": self.events, "note": self.note, "style": self.style}


@dataclass
class PathExploreResult:
    """路径探索结果：N 条候选（用户判别选优，不自动定案）。"""

    paths: list[PathCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"paths": [p.to_dict() for p in self.paths]}


def _build_prompt(from_desc: str, to_desc: str, constraints: list[str] | None, n: int) -> str:
    if constraints:
        c_block = "\n【已固化设定约束（不得冲突，避开）】\n- " + "\n- ".join(constraints)
    else:
        c_block = ""
    return PROMPT_TEMPLATE.format(
        from_desc=from_desc.strip() or "（未描述）",
        to_desc=to_desc.strip() or "（未描述）",
        constraints_block=c_block,
        n=n,
    )


class PathExplorer:
    """路径探索引擎：单次 LLM 调用自由生成 N 条候选路径（轻量上下文）。"""

    def __init__(self, model: object, n: int = 4) -> None:
        self._model = model
        self._n = min(max(n, MIN_PATHS), MAX_PATHS)

    def explore(
        self,
        from_desc: str,
        to_desc: str,
        constraints: list[str] | None = None,
    ) -> PathExploreResult:
        prompt = _build_prompt(from_desc, to_desc, constraints, self._n)
        output = self._model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return self._parse(output.text or "")

    def _parse(self, raw: str) -> PathExploreResult:
        payload = extract_json_dict(raw)
        raw_paths = payload.get("paths")
        if not isinstance(raw_paths, list):
            # 宽容：整段视为单路径的说明
            if raw.strip():
                return PathExploreResult(
                    paths=[PathCandidate(events=[], note=raw.strip(), style="")]
                )
            return PathExploreResult(paths=[])
        candidates: list[PathCandidate] = []
        for p in raw_paths[: self._n]:
            if not isinstance(p, dict):
                continue
            events = p.get("events")
            if not isinstance(events, list):
                events = []
            events = [str(e).strip() for e in events if str(e).strip()]
            if not events:
                continue  # 空事件链丢弃（无中间事件的路径无参考价值）
            candidates.append(
                PathCandidate(
                    events=events,
                    note=str(p.get("note", "")).strip(),
                    style=str(p.get("style", "")).strip(),
                )
            )
        return PathExploreResult(paths=candidates)


def explore_path(
    model: object,
    from_desc: str,
    to_desc: str,
    constraints: list[str] | None = None,
    n: int = 4,
) -> PathExploreResult:
    """便捷入口：起点 A → 终点 B 的 N 条串联路径候选（作为参考，不直接写正文）。"""
    return PathExplorer(model, n).explore(from_desc, to_desc, constraints)
