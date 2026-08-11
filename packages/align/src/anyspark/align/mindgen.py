"""anyspark.align.mindgen — 心智生成端（档位 L2 建议 + L3 自然语言生成档位）。

对应 DESIGN §12.18 / S35 遗留（"L2/L3 按需"）：
- **L2（AI 建议档位）**：LLM 读 collab 类心智条目 + 可选档位列表 → 建议最合适档位
  （含理由；现有档位都不合适时给出新建建议）。与 MindPlanner 的关键词启发式
  （`_infer_agency`）互补：启发式做无 LLM 时的 fallback，L2 提供语义判断——
  "你看着办但大事先问我"这类复杂协作偏好只有 LLM 能正确推断。
- **L3（自然语言生成档位）**：用户一句自然语言描述 → LLM 生成档位候选
  （名称/描述/温度）→ 人工确认后走既有 `/api/agency/add` 落库
  （人工确认闸门，对齐 S54 skillgen"候选→确认生效"哲学——错误档位不直接进表）。

哲学：机制（提示词结构/宽容解析/温度钳制）硬编码；内容（建议/档位描述）模型生成。
"""

from __future__ import annotations

from typing import Any

from anyspark.core.jsonutil import (
    parse_json_array,
    parse_json_object,
    strip_fence,
)

from .agency import AgencyLevel
from .manual import ManualEntry

# ---------------------------------------------------------------------------
# L2：AI 建议档位
# ---------------------------------------------------------------------------

_AGENCY_SUGGEST_PROMPT = """你是写作协作系统的"档位顾问"。档位 = AI 的能动性
（主动程度：AI 做多少、问多少、自己发挥多少），只描述主动程度，
不涉及文风/内容偏好（那些是另一套心智系统，不在这里考虑）。

以下是已沉淀的【用户协作偏好】（collab 类心智条目，自然语言）：
{entries}

以下是可选的【档位】：
{levels}

请推荐最合适的一个档位：
1. 综合用户协作偏好判断（习惯性确认→低档位；希望放手→高档位；混合则取中间）。
2. 从下方档位列表选一个 id；如果现有档位都不合适，level_id 填空字符串，
   并在 note 里给出你建议的新档位（名称+一句描述+温度 0-1）。
3. reason 一句自然语言理由，可引用用户原话。

输出（严格 JSON 对象，不要其它文字）：
{{"level_id": "档位id", "reason": "一句理由", "note": "新建档位建议或空字符串"}}
"""


def build_agency_suggest_prompt(entries: list[ManualEntry], levels: list[AgencyLevel]) -> str:
    """L2 建议提示词（app 层用真实 LLM 调用，模型无关）。"""
    e = "\n".join(f"- {s.content}" for s in entries[:10]) or "（无协作偏好条目）"
    lv = "\n".join(f"- {x.id}：{x.name}（{x.description}，温度 {x.temperature}）" for x in levels)
    return _AGENCY_SUGGEST_PROMPT.replace("{entries}", e).replace("{levels}", lv)


def parse_agency_suggest_result(raw: str) -> dict[str, str]:
    """宽容解析 L2 建议结果 JSON 对象。"""
    data = _parse_json_object(raw)
    if not data:
        return {"level_id": "", "reason": "", "note": ""}
    return {
        "level_id": str(data.get("level_id", "")),
        "reason": str(data.get("reason", "")),
        "note": str(data.get("note", "")),
    }


# ---------------------------------------------------------------------------
# L3：自然语言生成档位
# ---------------------------------------------------------------------------

_AGENCY_GEN_PROMPT = """你是写作协作系统的"档位设计器"。根据用户的一句自然语言描述，
设计能动性档位（AI 主动程度：做什么/问多少/自己发挥多少）。输出 {n} 个候选。

用户描述：
{description}

要求：
1. 名称：2-6 个汉字，概括该档位的主动程度。
2. 描述：一句明确无歧义的自然语言，说明 AI 该做什么、不该做什么（怎么写交给心智，不涉及文风）。
3. 温度：0.2-1.0 之间的小数（越自主温度越高）。
4. 候选之间要有明显区分。

输出（严格 JSON 数组，不要其它文字）：
[{{"name": "自主推进", "description": "AI 自主续写并推进剧情，重大转折前才询问。",
"temperature": 0.9}}]
"""


def build_agency_gen_prompt(description: str, n: int = 3) -> str:
    """L3 生成提示词（app 层用真实 LLM 调用，模型无关）。"""
    return _AGENCY_GEN_PROMPT.replace("{description}", description).replace("{n}", str(n))


def parse_agency_gen_result(raw: str) -> list[dict[str, Any]]:
    """宽容解析 L3 候选 JSON 数组（钳制温度 0-1，非法项丢弃）。"""
    out: list[dict[str, Any]] = []
    for item in _parse_json_array(raw):
        name = str(item.get("name", "")).strip()
        desc = str(item.get("description", "")).strip()
        if not name or not desc:
            continue
        try:
            temp = float(item.get("temperature", 0.7))
        except (TypeError, ValueError):
            temp = 0.7
        out.append({"name": name, "description": desc, "temperature": max(0.0, min(1.0, temp))})
    return out


# ---------------------------------------------------------------------------
# 宽容 JSON 解析（对象 + 数组；对齐 extract._parse_json_array 风格）
# ---------------------------------------------------------------------------


def _strip_fence(text: str) -> str:
    """去 ```json ... ``` 围栏（R1 收敛到 core.jsonutil）。"""
    return strip_fence(text)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """宽容解析 JSON 对象（R1 收敛到 core.jsonutil）。"""
    return parse_json_object(text)


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """宽容解析 JSON 数组（R1 收敛到 core.jsonutil）。"""
    data = parse_json_array(text)
    if data is None:
        return []
    return [d for d in data if isinstance(d, dict)]
