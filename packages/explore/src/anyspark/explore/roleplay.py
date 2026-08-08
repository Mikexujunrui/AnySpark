"""
anyspark.explore.roleplay — 角色推演（S48-P4：角色视角的多路探索 + 选优）。

主人拍板设计：**低成本多探索，最后选择最好的作为参考**（复用 pi-multi-agent
的 room_compare 模式，复用的机制不是代码）：
- 低成本：每路轻量上下文（角色卡 + 当前状态 + 场景，不背全量图谱）；并行时间≈单次
- 多探索：N 路隔离并行（复用 explore 的 asyncio.gather + 上下文隔离，防伪多样性），
  每路不同推演策略（最可能/最戏剧化/最反常/最克制）
- 最后选择最好的：LLM 判别器按"符合角色设定 + 场景张力"选优
- 作为参考：输出 best + 备选，供 AI 写作参考/进候选卡/作者选择——不直接写正文

机制硬编码（策略集/并行/判别结构），内容自然语言（策略描述/推演文本/角色卡）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from anyspark.core import Message

# 推演策略集（机制硬编码：多样性靠差异化指令，上下文隔离保证不锚定）
ROLE_STRATEGIES: list[dict[str, str]] = [
    {
        "id": "likely",
        "name": "最可能反应",
        "instruction": (
            "按角色性格逻辑推演最可能的真实反应（心理/言语/动作），克制、可信、符合人物一贯行为。"
        ),
    },
    {
        "id": "dramatic",
        "name": "最戏剧化反应",
        "instruction": (
            "推演最能制造冲突与张力的反应——把角色逼到情绪/抉择的临界点，产生戏剧性变化。"
        ),
    },
    {
        "id": "unexpected",
        "name": "最反常反应",
        "instruction": (
            "推演违背直觉但内部自洽的反应——角色的隐藏面或非常规抉择，避免平庸（防锚定）。"
        ),
    },
    {
        "id": "restrained",
        "name": "最克制反应",
        "instruction": "推演话少意深的克制反应——沉默、微动作、留白，信息藏在没说出口的部分。",
    },
]


@dataclass
class RolePlayCandidate:
    """一路推演产物。"""

    strategy: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"strategy": self.strategy, "text": self.text}


@dataclass
class RolePlayResult:
    """推演结果：最佳 + 备选（作为参考，不直接写正文）。"""

    best: RolePlayCandidate | None = None
    candidates: list[RolePlayCandidate] = field(default_factory=list)
    score_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "best": self.best.to_dict() if self.best else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "score_reason": self.score_reason,
        }


def _build_prompt(role_card: str, state: str, scenario: str, strategy: dict[str, str]) -> str:
    return f"""你是小说角色推演器。以给定角色的视角，推演他在场景中的反应。

【角色设定】
{role_card}

【角色当前状态】
{state or "（未知）"}

【场景】
{scenario}

【推演要求】
{strategy["instruction"]}

直接输出推演内容（心理活动/可能说出的话/动作），不要解释。"""


def _build_judge_prompt(role_card: str, scenario: str, candidates: list[RolePlayCandidate]) -> str:
    lines = [f"【角色设定】\n{role_card}", f"【场景】\n{scenario}", "【候选推演】"]
    for i, c in enumerate(candidates, 1):
        lines.append(f"\n候选 {i}（{c.strategy}）：\n{c.text}")
    lines.append("\n选出最符合角色性格且最有戏剧张力的一个。只输出：'编号：N' 加一行理由。")
    return "\n".join(lines)


def _parse_judge(text: str, n: int) -> int | None:
    import re

    m = re.search(r"编号[:：\s]*(\d+)", text)
    if not m:
        return None
    idx = int(m.group(1)) - 1
    return idx if 0 <= idx < n else None


class RolePlayEngine:
    """角色推演引擎：N 路隔离并行 + 判别选优（复用 explore 基建模式）。"""

    def __init__(self, model: object, n: int = 4) -> None:
        self._model = model
        self._n = min(max(n, 2), 6)

    def play(self, role_card: str, state: str, scenario: str) -> RolePlayResult:
        return asyncio.run(self._play_async(role_card, state, scenario))

    async def _play_async(self, role_card: str, state: str, scenario: str) -> RolePlayResult:
        strategies = ROLE_STRATEGIES[: self._n]
        candidates = await asyncio.gather(
            *[self._call_one(role_card, state, scenario, s) for s in strategies]
        )
        cands = [c for c in candidates if c.text.strip()]
        if not cands:
            return RolePlayResult(candidates=[])
        # 判别选优（最后选择最好的）
        judge_prompt = _build_judge_prompt(role_card, scenario, cands)
        judge_out = await asyncio.to_thread(
            self._model.respond,  # type: ignore[attr-defined]
            [Message(role="system", content=judge_prompt)],
            [],
        )
        idx = _parse_judge(judge_out.text, len(cands))
        best = cands[idx] if idx is not None else cands[0]
        return RolePlayResult(best=best, candidates=cands, score_reason=judge_out.text)

    async def _call_one(
        self, role_card: str, state: str, scenario: str, strategy: dict[str, str]
    ) -> RolePlayCandidate:
        prompt = _build_prompt(role_card, state, scenario, strategy)
        output = await asyncio.to_thread(
            self._model.respond,  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return RolePlayCandidate(strategy=strategy["name"], text=(output.text or "").strip())


def load_role_card(workspace: Any, graph: Any, role: str, book_id: str = "main") -> tuple[str, str]:
    """加载角色卡：文件（卡片/角色卡-{role}.md）优先，缺省从图谱实体描述兜底。

    返回 (role_card, state)——role_card 可能为空（无角色卡也无图谱实体）。
    S63 抽取：role_play 工具与 /api/role/play 原先各自实现了同一套查找逻辑，
    收敛到这里共用（避免同一能力双通道代码漂移）。
    """
    role_card = ""
    card_path = workspace.cards_dir(book_id) / f"角色卡-{role}.md"
    if card_path.exists():
        role_card = card_path.read_text(encoding="utf-8", errors="ignore")
    state = ""
    ent = graph.get_entity(book_id, role) if graph is not None else None
    if ent is not None:
        st = getattr(ent, "state", "") or ""
        desc = getattr(ent, "description", "") or ""
        state = st
        if not role_card.strip():
            role_card = f"# {role}\n{desc}\n\n当前状态：{st}"
    return role_card, state


def run_roleplay(
    model: object,
    role_card: str,
    state: str = "",
    scenario: str = "",
    n: int = 4,
) -> RolePlayResult:
    """便捷入口：角色推演（角色卡 + 当前状态 + 场景 → best + 备选）。"""
    return RolePlayEngine(model, n).play(role_card, state, scenario)
