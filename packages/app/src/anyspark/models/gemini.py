"""
anyspark.models.gemini — Google Generative AI API 适配器（Gemini 直连，S131）。

实现 core 的 Model + StreamModel 协议，httpx2 手写 HTTP 调用（零新增依赖）。
端点：{base}/v1beta/models/{model}:generateContent（非流式）/
      {base}/v1beta/models/{model}:streamGenerateContent?alt=sse（流式）
鉴权：x-goog-api-key 请求头（API key 直连，不用 OAuth Bearer——小说写作场景 key 足够）。

思考强度映射（同款档位 off/low/medium/high/xhigh/max）：
- None → 不传 thinkingConfig（交模型默认）
- off → thinkingConfig: {thinkingBudget: 0}（显式关闭思考）
- low/medium/high/xhigh/max → thinkingConfig: {thinkingBudget: N}
  budget 映射（token）：low=1024 / medium=4096 / high=8192 / xhigh=16384 / max=32768

工具调用：tools.functionDeclarations；响应 parts.functionCall；
工具结果回填为 user 消息 parts.functionResponse（紧跟对应 functionCall 之后）。

配置：base_url 默认 https://generativelanguage.googleapis.com；
api_key 默认读 GEMINI_API_KEY（/login 同款环境变量名，与 pi 对齐）。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import httpx2 as httpx  # S66：httpx2（下一代 httpx；重命名迁移，API 兼容）

from anyspark.core import (
    Event,
    Message,
    ModelOutput,
    ToolCall,
    sanitize_tool_pairing,
)
from anyspark.core.protocol import ParamSpec, ToolSpec

DEFAULT_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")

# 思考档位 → thinkingBudget（token 计；0=关闭）
THINKING_BUDGETS: dict[str, int] = {
    "off": 0,
    "low": 1024,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
    "max": 32768,
}


def thinking_to_gemini(thinking: str | None) -> dict[str, int] | None:
    """思考强度档位 → generationConfig.thinkingConfig（None=不传交模型默认）。"""
    if not thinking:
        return None
    budget = THINKING_BUDGETS.get(thinking)
    if budget is None:
        raise ValueError(f"非法思考强度 {thinking!r}：可选 off/low/medium/high/xhigh/max")
    return {"thinkingBudget": budget}


def to_gemini_tool(spec: ToolSpec) -> dict[str, Any]:
    """core ToolSpec → Gemini functionDeclarations 定义。

    Gemini 的 FunctionDeclaration schema 要求：
    - type 用**大写枚举**（STRING/INTEGER/NUMBER/BOOLEAN/ARRAY/OBJECT）——小写会被校验器拒
    - type=ARRAY 时**必须提供 items**（内嵌元素 schema）——缺失报
      `properties[xxx].items: missing field`（真实用户报错驱动，含自定义工具的 array 参数）
    - 未知类型退化为 STRING（保守，避免请求被拒）
    """
    type_map: dict[str, str] = {
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }

    def _prop_schema(p: ParamSpec) -> dict[str, Any]:
        t = type_map.get(p.type, "STRING")
        schema: dict[str, Any] = {"type": t, "description": p.description}
        if t == "ARRAY":
            # Gemini 要求数组必须声明元素类型；未知元素类型退化为 STRING
            schema["items"] = {"type": "STRING"}
        elif t == "OBJECT":
            schema["properties"] = {}
        return schema

    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in spec.params:
        properties[p.name] = _prop_schema(p)
        if p.required:
            required.append(p.name)
    return {
        "name": spec.name,
        "description": spec.description,
        "parameters": {
            "type": "OBJECT",
            "properties": properties,
            "required": required,
        },
    }


def to_gemini_contents(
    messages: list[Message],
) -> tuple[str | None, list[dict[str, Any]]]:
    """core Message 列表 → (systemInstruction, contents)。

    Gemini 消息语义（role 只能 user/model）：
    - system → 顶层 systemInstruction
    - assistant 带 metadata.tool_calls → model 角色 + functionCall parts
    - tool 消息 → user 角色 + functionResponse parts（Gemini 允许独立 user 消息，
      无需像 Anthropic 那样合并；functionResponse 紧跟对应 functionCall）
    """
    messages = sanitize_tool_pairing(messages)  # core 通用守卫（S190）
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    # S176：id→name 映射——loop 的 tool 消息只设 tool_call_id 不设 tool_name，
    # Gemini 的 functionResponse.name 需匹配 functionCall.name（工具名），否则配对失败。
    # 从 assistant 声明的 tool_calls 按 id 补 name（转换层修复，不改 loop）。
    id_to_name: dict[str, str] = {}
    for m in messages:
        if m.role == "assistant":
            calls = m.metadata.get("tool_calls")
            if isinstance(calls, list):
                for c in calls:
                    if isinstance(c, dict) and c.get("id") and c.get("name"):
                        id_to_name[str(c["id"])] = str(c["name"])

    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
            continue
        if m.role == "tool":
            tid = m.metadata.get("tool_call_id")
            # S176：优先用 id→name 映射补工具名（loop 不设 tool_name）
            name = (
                id_to_name.get(str(tid or ""))
                or str(m.metadata.get("tool_name") or "")
                or str(tid or "")
            )
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": name,
                                "response": {"result": m.content},
                            }
                        }
                    ],
                }
            )
            continue
        if m.role == "assistant":
            parts: list[dict[str, Any]] = []
            if m.content:
                parts.append({"text": m.content})
            calls = m.metadata.get("tool_calls")
            if isinstance(calls, list):
                for c in calls:
                    if isinstance(c, dict) and c.get("id"):
                        parts.append(
                            {
                                "functionCall": {
                                    "name": str(c.get("name") or ""),
                                    "args": c.get("arguments") or {},
                                }
                            }
                        )
            contents.append({"role": "model", "parts": parts})
        else:
            contents.append({"role": "user", "parts": [{"text": m.content}]})

    # S176：悬挂 functionCall 防御——model 声明了 functionCall 但后续无对应
    # functionResponse（取消/异常/坏数据遗留）→ 移除未配对的 functionCall，
    # 否则 Gemini 配对失败。收集所有 functionResponse.name（按映射后的 name）。
    responded_names: set[str] = set()
    for c in contents:
        if c["role"] == "user":
            for p in c["parts"]:
                if "functionResponse" in p:
                    responded_names.add(str(p["functionResponse"].get("name") or ""))
    for c in contents:
        if c["role"] == "model":
            c["parts"] = [
                p
                for p in c["parts"]
                if "functionCall" not in p
                or str(p["functionCall"].get("name") or "") in responded_names
            ]
            if not c["parts"]:
                c["parts"] = [{"text": ""}]  # model parts 非空

    system = "\n".join(system_parts) if system_parts else None
    # S176：system-only 兜底——内部管道只传 [system] → contents 空 → Gemini 400。
    if not contents and system:
        contents = [{"role": "user", "parts": [{"text": system}]}]
        system = None
    return system, contents


def _parse_parts(parts: list[dict[str, Any]]) -> tuple[str, list[ToolCall]]:
    """Gemini parts → (text, tool_calls)。"""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for part in parts:
        if "text" in part:
            text_parts.append(part["text"] or "")
        elif "functionCall" in part:
            fc = part["functionCall"]
            raw = fc.get("args")
            args: dict[str, Any]
            if isinstance(raw, dict):
                args = raw
            else:  # 截断防护（S21）：args 非对象 → 标记，不执行，让模型重发
                args = {"_raw": json.dumps(raw, ensure_ascii=False), "_malformed": True}
            tool_calls.append(
                ToolCall(
                    name=fc.get("name") or "",
                    arguments=args,
                    id=fc.get("name") or "",  # Gemini 无 call id——用函数名兼作 id
                )
            )
    return "".join(text_parts), tool_calls


class GeminiModel:
    """Google Generative AI 真实调用器（实现 core.Model + StreamModel 协议）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        context_window: int | None = None,
        thinking: str | None = None,
    ) -> None:
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "") or ""
        if not self._api_key:
            raise ValueError("未配置 Gemini API key：请设置 GEMINI_API_KEY 或传 api_key 参数")
        self._model = model or "gemini-2.5-flash"
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._thinking_cfg = thinking_to_gemini(thinking)
        self._context_window = context_window or int(os.getenv("GEMINI_CONTEXT_WINDOW", "1000000"))
        self._client = httpx.Client(trust_env=False, timeout=120.0)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._context_window

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key, "content-type": "application/json"}

    def _payload(self, messages: list[Message], tools: list[ToolSpec]) -> dict[str, Any]:
        system, contents = to_gemini_contents(messages)
        payload: dict[str, Any] = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": [to_gemini_tool(t) for t in tools]}]
        gen: dict[str, Any] = {
            "temperature": self._temperature,
            "maxOutputTokens": self._max_tokens,
        }
        if self._thinking_cfg is not None:
            gen["thinkingConfig"] = self._thinking_cfg
        payload["generationConfig"] = gen
        return payload

    def _url(self, stream: bool) -> str:
        endpoint = ":streamGenerateContent?alt=sse" if stream else ":generateContent"
        return f"{self._base_url}/v1beta/models/{self._model}{endpoint}"

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        """真实调用 Gemini，返回模型无关的 ModelOutput（非流式）。"""
        payload = self._payload(messages, tools)
        resp = self._client.post(self._url(stream=False), json=payload, headers=self._headers())
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini 无候选输出: {json.dumps(data, ensure_ascii=False)[:300]}")
        cand = candidates[0]
        content = cand.get("content") or {}
        text, tool_calls = _parse_parts(content.get("parts") or [])
        fr = cand.get("finishReason") or ""
        truncated = fr == "MAX_TOKENS"
        usage: dict[str, int] | None = None
        u = data.get("usageMetadata")
        if isinstance(u, dict):
            usage = {
                "prompt_tokens": int(u.get("promptTokenCount") or 0),
                "completion_tokens": int(u.get("candidatesTokenCount") or 0),
                "total_tokens": int(u.get("totalTokenCount") or 0),
            }
        return ModelOutput(
            text=text,
            tool_calls=tool_calls,
            truncated=truncated,
            reasoning="",  # Gemini 思考内容默认不进响应（需显式 includeThoughts，暂不启用）
            usage=usage,
            finish_reason=fr,
        )

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Any], None] | None = None,
    ) -> ModelOutput:
        """流式协议：SSE 增量 parts → text_delta / toolcall_delta 事件。"""
        payload = self._payload(messages, tools)
        text_parts: list[str] = []
        # S178：用列表而非以 name 为键的 dict——同名工具调用并行（如两次 read_chapter）
        # 在 dict 下会覆盖丢失；列表保留每个 functionCall。
        tool_acc: list[dict[str, Any]] = []
        truncated = False
        finish_reason = ""
        usage: dict[str, int] | None = None
        current_data: list[str] = []

        with self._client.stream(
            "POST",
            self._url(stream=True),
            json=payload,
            headers=self._headers(),
        ) as resp:
            if resp.status_code != 200:
                # httpx2 流式响应未消费：直接访问 .text 抛 ResponseNotRead——先 read 再取错误详情
                try:
                    resp.read()
                    detail = resp.text[:300]
                except Exception:
                    detail = "(无法读取错误详情)"
                raise RuntimeError(f"Gemini API {resp.status_code}: {detail}")
            for line in resp.iter_lines():
                if line == "":
                    if current_data:
                        try:
                            chunk = json.loads("\n".join(current_data))
                        except json.JSONDecodeError:
                            chunk = None
                        if chunk:
                            cands = chunk.get("candidates") or []
                            if cands:
                                parts = (cands[0].get("content") or {}).get("parts") or []
                                gfr = cands[0].get("finishReason") or ""
                                if gfr:
                                    finish_reason = gfr
                                if gfr == "MAX_TOKENS":
                                    truncated = True
                                for part in parts:
                                    if "text" in part:
                                        t = part["text"] or ""
                                        text_parts.append(t)
                                        if on_event is not None:
                                            on_event(
                                                Event(type="text_delta", payload={"content": t})
                                            )
                                    elif "functionCall" in part:
                                        fc = part["functionCall"]
                                        name = fc.get("name") or ""
                                        raw = fc.get("args")
                                        args_str = (
                                            json.dumps(raw, ensure_ascii=False)
                                            if isinstance(raw, dict)
                                            else str(raw or "")
                                        )
                                        tool_acc.append({"name": name, "args": args_str})
                                        if on_event is not None:
                                            on_event(
                                                Event(
                                                    type="toolcall_delta",
                                                    payload={"content": args_str},
                                                )
                                            )
                            u = chunk.get("usageMetadata")
                            if isinstance(u, dict):
                                usage = {
                                    "prompt_tokens": int(u.get("promptTokenCount") or 0),
                                    "completion_tokens": int(u.get("candidatesTokenCount") or 0),
                                    "total_tokens": int(u.get("totalTokenCount") or 0),
                                }
                    current_data = []
                elif line.startswith("data:"):
                    current_data.append(line[len("data:") :].strip())

        tool_calls: list[ToolCall] = []
        for acc in tool_acc:
            raw = acc["args"]
            try:
                args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                # 截断防护（S21）：参数非法→标记，不执行，让模型重发
                args = {"_raw": raw, "_malformed": True}
            # S178：id 用 name + 序号（Gemini functionCall 无 id 字段，同名需区分）
            tid = f"{acc['name']}_{len(tool_calls)}"
            tool_calls.append(ToolCall(name=acc["name"], arguments=args, id=tid))
        return ModelOutput(
            text="".join(text_parts),
            tool_calls=tool_calls,
            truncated=truncated,
            reasoning="",
            usage=usage,
            finish_reason=finish_reason,
        )
