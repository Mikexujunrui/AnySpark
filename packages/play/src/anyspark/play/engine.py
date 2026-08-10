"""
anyspark.play.engine — 互动推演引擎（扮演角色、多轮选择、推演树）。

回合流程（每轮 1 次 LLM 调用，轻量上下文）：
- create：seed（切入场景）+ role → 生成根节点 scene（当前局势）+ N 个候选行动
- choose：选 A / 自定义输入 → 结算：生成子节点 scene'（上一轮选择的后果 + 他角
  反应 + 新局势）+ 新 N 个候选行动
- branch：回溯分叉——从历史节点重新生成一批新选项（原选项保留）
- 终止：用户喊停 / 模型 options 为空（自然收束）/ 最大深度

选项生成（主人修正，DESIGN §12.27）：**不硬编码策略集**——模型自由发挥生成
3-5 个差异化候选行动（方向由模型按场景与角色自由判断，提示词引导）；自定义位
是唯一硬编码（用户自由输入的行动）。

跨包复用（复制=漂移源）：load_role_card（角色卡加载）+ extract_json_dict（宽容
JSON 解析）都来自 anyspark.explore，单向依赖 core ← explore ← play。
"""

from __future__ import annotations

import asyncio
from typing import Any

from anyspark.core.types import Message
from anyspark.explore import extract_json_dict, load_role_card

from .export import export_path_markdown
from .tree import PlayStore

# 默认选项生成数（提示词要求 3-5 个，解析时容错）
MIN_OPTIONS = 3
MAX_OPTIONS = 5

PROMPT_TEMPLATE = """你是互动推演引擎。用户在玩推演游戏：扮演 {role}，从给定场景出发，
每步做选择，剧情随选择推进。你要生成"结算后的场景 + 下一批候选行动"。

【角色卡】
{role_card}

【当前局势】
{scene}
{history_block}
【任务】
1. 生成结算后的场景描述（2-4 句，自然叙事，落在 {role} 的视角，含后果与当前局势）
2. 站在 {role} 的立场，生成 {n} 个差异化候选行动——从不同行动方向出发
   （推进主线/制造冲突/试探试探/退守观察/出人意料/情感攻势等，具体方向由你按
   场景与角色自由判断），避免雷同平庸
3. 每个候选行动是一句行动描述（"我……"句式）

【防代控（重要）】
- 候选行动只是**建议**——玩家可以自由输入自定义行动，不受选项限制；
  不要生成"你只能从这几条里选"的暗示
- 选项只描述 {role} 自己的行动，**不要预写其他角色的反应/后果**
  （如"我推门进去，她愣住了"——后半句是代控，应写成"我推门进去"，
  她的反应由你结算时生成）

输出严格 JSON（不要多余文字）：
{{"scene": "结算后的场景描述", "options": ["行动A", "行动B", "行动C"]}}

若剧情已自然收束（无合理下一步），options 给空数组，scene 末尾标注"（故事收束）"。"""


class PlayEngine:
    """互动推演引擎：创建/选择/回溯/终止（树存储 + LLM 生成）。"""

    def __init__(
        self,
        store: PlayStore,
        model: object,
        workspace: Any,
        graph: Any | None = None,
    ) -> None:
        self._store = store
        self._model = model
        self._workspace = workspace
        self._graph = graph

    # ------------------------------------------------------------------
    # 创建会话（根节点 + 首批选项）
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        role: str,
        seed: str,
        book_id: str = "main",
        title: str = "",
        max_depth: int = 20,
    ) -> dict[str, Any]:
        role_card, _ = load_role_card(self._workspace, self._graph, role, book_id)
        if not role_card.strip():
            raise ValueError(f"角色卡不存在（可先创建 卡片/角色卡-{role}.md）：{role}")

        prompt = self._build_prompt(role, role_card, seed, history_block="")
        payload = self._generate(prompt)
        scene = str(payload.get("scene", "")).strip()
        options = [str(o).strip() for o in payload.get("options", []) if str(o).strip()]
        if not scene:
            raise RuntimeError("推演失败：模型未生成有效场景")

        session = self._store.create_session(
            role=role, seed=seed, book_id=book_id, title=title, max_depth=max_depth
        )
        root_id = self._store.add_node(session_id=session["id"], parent_id="", depth=0, scene=scene)
        opt_dicts = self._store.add_options(root_id, options[:MAX_OPTIONS])
        self._store.set_current(session["id"], root_id)
        node = self._node_view(self._store.get_node(root_id), opt_dicts)
        ended = not options
        if ended:
            self._store.end_session(session["id"])
        session = self._store.get_session(session["id"]) or session
        return {"session": session, "node": node, "ended": ended}

    # ------------------------------------------------------------------
    # 选择（选项 / 自定义输入）→ 结算生成子节点
    # ------------------------------------------------------------------
    def choose(
        self,
        session_id: str,
        *,
        option_id: str = "",
        custom_text: str = "",
    ) -> dict[str, Any]:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"推演会话不存在：{session_id}")
        if session["status"] == "ended":
            raise ValueError("会话已结束")

        current_id = session["current_node_id"] or ""
        current = self._store.get_node(current_id)
        if current is None:
            raise ValueError("会话无当前节点（数据异常）")

        if not option_id and not custom_text.strip():
            raise ValueError("需要 option_id 或 custom_text")
        if custom_text.strip():
            action = custom_text.strip()
            option_row: dict[str, Any] | None = None
        else:
            option_row = self._store.get_option(option_id)
            if option_row is None:
                raise KeyError(f"选项不存在：{option_id}")
            # 校验该选项属于当前节点（防跨节点选择）
            if option_row["node_id"] != current_id:
                raise ValueError("选项不属于当前节点（请先回溯到对应节点）")
            action = str(option_row["label"]).strip()

        depth = int(current["depth"]) + 1
        max_depth = int(session["max_depth"] or 20)
        if depth > max_depth:
            raise ValueError(f"已达最大深度 {max_depth}（可回溯分叉或结束）")

        role_card, _ = load_role_card(
            self._workspace, self._graph, str(session["role"]), str(session["book_id"])
        )
        history = (
            f"【你上一轮的选择】\n{action}\n"
            "——请先结算这个选择的后果（其他角色如何反应、世界如何变化、发生了什么），再继续。"
        )
        prompt = self._build_prompt(
            str(session["role"]), role_card, str(current["scene"]), history_block=history
        )
        payload = self._generate(prompt)
        scene = str(payload.get("scene", "")).strip()
        options = [str(o).strip() for o in payload.get("options", []) if str(o).strip()]
        if not scene:
            raise RuntimeError("推演失败：模型未生成有效场景")

        child_id = self._store.add_node(
            session_id=session_id,
            parent_id=current_id,
            depth=depth,
            scene=scene,
            chosen_label=action,
        )
        if option_row is not None:
            self._store.choose_option(option_id, child_id)
        else:
            self._store.add_custom_option(current_id, action, child_id)

        ended = not options
        opt_dicts: list[dict[str, Any]] = []
        if options:
            opt_dicts = self._store.add_options(child_id, options[:MAX_OPTIONS])
            self._store.set_current(session_id, child_id)
        else:
            self._store.end_session(session_id)
        node = self._node_view(self._store.get_node(child_id), opt_dicts)
        return {"node": node, "ended": ended}

    # ------------------------------------------------------------------
    # 回溯分叉：从历史节点重新生成一批新选项
    # ------------------------------------------------------------------
    def branch(self, session_id: str, node_id: str) -> dict[str, Any]:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"推演会话不存在：{session_id}")
        node = self._store.get_node(node_id)
        if node is None or node["session_id"] != session_id:
            raise KeyError(f"节点不存在或不属于该会话：{node_id}")
        if session["status"] == "ended":
            raise ValueError("会话已结束")

        role_card, _ = load_role_card(
            self._workspace, self._graph, str(session["role"]), str(session["book_id"])
        )
        prompt = self._build_prompt(
            str(session["role"]), role_card, str(node["scene"]), history_block=""
        )
        payload = self._generate(prompt)
        options = [str(o).strip() for o in payload.get("options", []) if str(o).strip()]
        opt_dicts = self._store.add_options(node_id, options[:MAX_OPTIONS])
        self._store.set_current(session_id, node_id)
        return {"node": self._node_view(node, opt_dicts)}

    # ------------------------------------------------------------------
    # 导出（灵感卡 md，接写正文参考）
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 导出（灵感卡 md，接写正文参考）
    # ------------------------------------------------------------------
    def current_node(self, session_id: str) -> dict[str, Any]:
        """当前节点视图（scene + 候选行动）。"""
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"推演会话不存在：{session_id}")
        node_id = session["current_node_id"] or ""
        node = self._store.get_node(node_id)
        if node is None:
            raise ValueError("会话无当前节点（数据异常）")
        return self._node_view(node, self._store.options_of(node_id))

    def export_markdown(self, session_id: str) -> str:
        """当前路径导出灵感卡 md。"""
        return export_path_markdown(self._store, session_id)

    # ------------------------------------------------------------------
    # 终止
    # ------------------------------------------------------------------
    def stop(self, session_id: str) -> dict[str, Any]:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"推演会话不存在：{session_id}")
        self._store.end_session(session_id)
        return {"ok": True, "session_id": session_id, "status": "ended"}

    # ------------------------------------------------------------------
    # 内部：prompt 构建 / LLM 调用 / 解析 / 视图
    # ------------------------------------------------------------------
    def _build_prompt(self, role: str, role_card: str, scene: str, history_block: str) -> str:
        n = f"{MIN_OPTIONS}-{MAX_OPTIONS} 个"
        return PROMPT_TEMPLATE.format(
            role=role,
            role_card=role_card or "（无角色卡）",
            scene=scene,
            history_block=history_block,
            n=n,
        )

    def _generate(self, prompt: str) -> dict[str, Any]:
        output = asyncio.run(self._respond(prompt))
        text = (output.text or "") if output is not None else ""
        payload = extract_json_dict(text)
        if not payload and text.strip():
            # 宽容：模型可能把 JSON 包在叙述里，提取失败则整段视为 scene 无选项
            payload = {"scene": text.strip(), "options": []}
        return payload

    async def _respond(self, prompt: str) -> Any:
        return await asyncio.to_thread(
            self._model.respond,  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )

    @staticmethod
    def _node_view(node: dict[str, Any] | None, options: list[dict[str, Any]]) -> dict[str, Any]:
        if node is None:
            return {}
        return {
            "id": node["id"],
            "depth": node["depth"],
            "scene": node["scene"],
            "chosen_label": node["chosen_label"] or "",
            "options": [
                {"id": o["id"], "label": o["label"], "is_custom": bool(o["is_custom"])}
                for o in options
            ],
        }
