"""Project-level creative constitution.

The constitution is user-authored and book-scoped.  It is injected into both
the tool-routing Agent and the dedicated prose writer so slash shortcuts,
Autopilot, and normal chat all follow the same rules.
"""

from data.json_store import json_store

MAX_CONSTITUTION_CHARS = 20000

RECOMMENDED_CONSTITUTION = """# 本书不可违背的创作规则
1. 已有正文、人物事实、时间线和明确设定优先于模型的自由发挥。
2. 不得擅自改写、删除或覆盖已经导入和已经存在的章节。
3. 续写只从最后一个已有章节之后开始；需要修改旧章时必须先明确指出并征得我确认。
4. 不得新增会改变主线的重要人物、能力、关系、地点或历史；确有必要时先提出建议，不直接写入正文。
5. 严格执行我本轮给出的情节目的、人物动机、视角、语气和禁止项。
6. 文风可以学习参考书的节奏、句式、叙事距离和用词习惯，但不得把参考书中无关作品的人物或设定带入本书。
7. 不用空泛总结、套路转折、强行升华和解释性旁白代替具体场景。
8. 对无法从正文或知识库确认的信息保持克制；不确定时保留空白或向我询问。
9. 正文生成后先评审一致性与文风偏差，不得为了通过评审而偷偷重写整章。
10. 任何修改都应保留版本历史，并向我说明修改范围。"""


def get_creative_constitution(book_id: str) -> str:
    if not book_id:
        return ""
    try:
        book = json_store.get_book(book_id)
    except Exception:
        return ""
    if book.get("constitutionEnabled", True) is False:
        return ""
    value = str(book.get("creativeConstitution", "") or "").strip()
    return value[:MAX_CONSTITUTION_CHARS]


def build_constitution_system_section(book_id: str) -> str:
    constitution = get_creative_constitution(book_id)
    if not constitution:
        return ""
    return f"""# 本书创作宪法（项目级硬约束）

以下规则由用户为本书明确制定。在所有文学规划、正文生成、修改、评审和 Auto
任务中持续有效。除平台安全规则外，它高于一般风格建议、默认工作流和模型自身
偏好。若本轮要求与宪法冲突，先指出具体冲突并询问用户，不得静默忽略。

{constitution}

# 宪法执行方式
- 写前逐条检查相关规则；规则不明确时选择更保守、少改动的方案。
- 写后核对人物事实、时间线、视角、禁止项和已存在章节保护。
- 不得声称“已遵守”代替实际检查。"""
