"""README 效果图演示数据灌入脚本（S262）。

用途：在【隔离的演示数据根】里复现 README 截图所用的全部演示内容——
演示小说《雾城夜雨》（前两章为内置 fixture，第三章由 agent 真实续写）、
图谱抽取、伏笔登记、书库导入、拆书工作流（产技巧草稿）。

前置：
- 后端已启动且【模型注册表里有可用激活配置】（.env 种子或前端注册均可）
- 建议隔离演示：停后端 → 把 data/ 改名移走 → 空 data/ 起后端 → 跑本脚本
  → 截图（scripts/readme_shots.js）→ 停后端 → 删演示 data/ → 移回原数据
- 真实模型调用（决策 B：禁模拟），全程约 3~6 分钟

用法：uv run python scripts/readme_demo.py [baseUrl]
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
BOOK = "雾城夜雨"

CH1 = """雨下了三天，雾城的排水系统终于认输。

陈渡把脚翘在桌上，数着天花板渗水的霉斑。侦探所在二楼，楼下是家面馆，汤气顺着地板缝爬上来，把整间屋子腌出一种咸腥的味道。生意不好做——这座城市的罪恶最近都在白天发生，体面得让侦探失业。

门被敲响的时候，他正准备关灯。

来人没有进门，只从门缝塞进来一个牛皮纸信封，然后消失在楼梯的阴影里。信封很沉。陈渡倒在桌上倒出来：一枚黄铜怀表，表盖内侧刻着两个字母 C.D.；还有半张当票，钟表铺老周的章，当物一栏被撕掉了。

C.D.——陈渡（Chen Du），或者，二十年前沉船案里死掉的船长陈定。

窗外一道闪电。陈渡把怀表揣进兜里，抓起帽子。老周的钟表铺在城南，雨再大，也得去看看。"""

CH2 = """钟表铺的灯还亮着，人却不在。

陈渡推门进去，满屋的挂钟滴滴答答，几十个钟面指着不同的时刻，像几十个各怀心事的人。柜台后头的账本摊开，正是那半张当票的存根——当物：怀表，黄铜；当主那一栏，签着一个娟秀的"林"字。

"林什么？"

"林晚。"身后有人替他答了。陈渡回头，门口站着的女人收了伞，雨水顺着伞尖在地上积成一小滩。她看起来二十七八，大衣的料子好得和这片街区格格不入。

"那块表是我的。"她说，"但我来，是想请你查另一件事——二十年前，雾城号沉船。船长陈定，是我父亲。"

陈渡摸了摸兜里的怀表。C.D.，陈定。他的名字和他只差一个字，而这绝不会是巧合。他父亲当年，也在那条船上。

挂钟忽然齐齐停了一拍。老周铺子深处，传来一声极轻的、走错了节奏的滴答。"""

BRIEF = """# 雾城夜雨

民国架空港城「雾城」的侦探悬疑短篇。侦探陈渡收到一枚刻着 C.D. 的黄铜怀表与半张当票，被卷入二十年前「雾城号」沉船旧案。来委托的神秘女子林晚是当年船长的女儿，而陈渡的父亲也在那条船上。

基调：冷硬派 noir，雨雾意象，短句节奏；每章末尾留钩子。核心悬念：怀表为何出现在当铺、老周为何失踪、沉船案真相与两位父辈的关系。"""


def api(method: str, path: str, body: dict | None = None, timeout: int = 900) -> dict | list:
    req = urllib.request.Request(
        BASE + urllib.parse.quote(path, safe="/?&="),
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> None:
    # 项目 + 简介（重复创建返回 409/已存在，忽略）
    for name, brief in (
        (BOOK, BRIEF),
        (
            "星渡",
            "# 星渡\n\n构思中的科幻长篇：世代飞船「星渡号」上，第一代移民的后裔在抵达前夜发现了航向被篡改的证据。主题：记忆、继承与选择的权利。",
        ),
    ):
        try:
            api("POST", "/api/books", {"content": name})
        except urllib.error.HTTPError as e:
            if e.code not in (409,):
                raise
        api("POST", "/api/brief", {"book_id": name, "content": brief})

    # 前两章（fixture）+ 伏笔
    for title, content in (("第一章 雨夜来信", CH1), ("第二章 空铺子", CH2)):
        api("POST", "/api/chapters", {"book_id": BOOK, "title": title, "content": content})
    for content, cat, pri, ref, order in (
        ("黄铜怀表刻着 C.D.——陈渡或船长陈定，表为何被当掉又送回来", "伏笔", "must", "第一章", 1),
        ("当票存根签着「林」字——林晚与钟表铺老周的关系", "伏笔", "must", "第二章", 2),
        ("挂钟齐齐停了一拍，铺子深处走错节奏的滴答声", "线索", "soft", "第二章", 2),
    ):
        api(
            "POST",
            "/api/plot/item",
            {
                "book_id": BOOK,
                "content": content,
                "category": cat,
                "priority": pri,
                "chapter_ref": ref,
                "planted_order": order,
            },
        )

    # 图谱抽取（真实模型）
    chs = api("GET", f"/api/chapters?book_id={BOOK}")
    for ch in chs:  # type: ignore[union-attr]
        print(
            "extract:",
            ch["title"],
            api(
                "POST",
                "/api/graph/extract",
                {"book_id": BOOK, "chapter_ref": ch["title"], "text": ch["content"]},
            ),
        )

    # 第三章：agent 真实续写（写章→自查→登记伏笔闭环）
    r = api(
        "POST",
        "/api/chat",
        {
            "book_id": BOOK,
            "message": "请续写第三章（800字左右）：陈渡与林晚夜访二十年前沉船案的旧档案，发现老周的名字出现在雾城号的乘客名单上。章末留钩子，并登记「老周与沉船案有关」这条伏笔。",
        },
    )
    print("chat conv:", r.get("conversation_id"))  # type: ignore[union-attr]

    # 书库导入 + 拆书工作流（产技巧草稿，供技巧面板截图）
    lib = api("POST", "/api/library", {"name": f"{BOOK}（演示）"})
    lid = lib["id"]  # type: ignore[index]
    chs = api("GET", f"/api/chapters?book_id={BOOK}")
    text = "\n\n".join(f"{c['title']}\n{c['content']}" for c in chs)  # type: ignore[union-attr]
    api("POST", "/api/library/import", {"book_id": lid, "content": text, "title": BOOK})
    wfs = api("GET", "/api/workflows")
    tpl = next(w for w in wfs if w["name"] == "拆书提炼")  # type: ignore[union-attr]
    print(
        "workflow:",
        api(
            "POST",
            f"/api/workflows/{tpl['id']}/run",
            {"book_id": BOOK, "params": {"library_book_id": lid}},
        ),
    )
    print("DONE —— 工作流后台运行，待 status=done 后跑 scripts/readme_shots.js")


if __name__ == "__main__":
    main()
