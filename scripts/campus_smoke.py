"""AnySpark v4 — 校园场景真实模型冒烟（S248 演示预演）。

用真实 DeepSeek 走通校园场景，验证「真实产出示例」而非仅管线连通：
  persona      写作引擎文体切换（academic vs fiction 人设与产出差异）
  check        学术检测规则包（故意埋瑕疵的学术段落 → 真实检测发现）
  review       审稿回复工作流（真实意见 → 逐条回应 → 回复信）
  multiplatform 多平台改写（一稿 → 公众号/小红书版本）
  proposal     申报书起草（大纲 → 逐节 → 汇编）
  all          依次全部

运行：uv run python scripts/campus_smoke.py [场景名]
数据隔离：workflow 走临时库（不污染 data/anyspark.db）。
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def scenario_d2() -> None:
    """D2/D3：真实 arXiv 导入 → 引用导出 → LaTeX 导出（纯机制，零模型调用）。"""
    import tempfile

    from anyspark.library import LibraryStore, import_arxiv_paper
    from anyspark.library.citation import fmt_bibtex, fmt_gbt7714

    store = LibraryStore(str(Path(tempfile.mkdtemp()) / "t.db"))
    out = import_arxiv_paper(store, "1706.03762")  # Attention Is All You Need
    meta = store.get_book(out["book_id"])["cite_meta"]
    _show("arXiv 导入 cite_meta", str(meta), 400)
    _show("GB/T 7714", fmt_gbt7714(meta), 300)
    _show("BibTeX", fmt_bibtex(meta), 500)


def scenario_project() -> None:
    """完整示例项目（全真实）：arXiv 导入×3 → 拆论文 → 文献综述 → 学术写作
    → 检测 → 引用导出 → LaTeX 导出。临时库隔离。
    """
    from anyspark.server.tools_writing import WritingTools
    from anyspark.server.workspace import Workspace
    from anyspark.store.sqlite import ChapterStore

    model = _real_model()
    db = Path(tempfile.mkdtemp()) / "project.db"
    client = _app(model, db)
    client.post("/api/genre", json={"genre": "academic", "book_id": "main"})

    # 1) 真实网络导入三篇注意力/LLM 论文
    ids = ["1706.03762", "1810.04805", "2005.14165"]  # Attention/BERT/GPT-3
    bids: list[str] = []
    for aid in ids:
        r = client.post("/api/library/import-arxiv", json={"arxiv_id": aid})
        assert r.status_code == 200, r.text
        bids.append(r.json()["book_id"])
    print(f"\n① 导入 3 篇真实论文 → {bids}")

    # 2) 拆论文（真实模型，摘要级语料）
    t = _run_workflow(client, "拆论文", {"library_book_id": bids[0]}, timeout_s=360)
    assert t["status"] == "done", t.get("error")
    _show("② 拆论文 → 方法论 skill 草稿", _final_output(t), 600)

    # 3) 文献综述（真实模型，三篇要点汇编）
    t = _run_workflow(
        client,
        "文献综述",
        {"paper_ids": ",".join(bids), "topic": "注意力机制与大语言模型的演进"},
        timeout_s=600,
    )
    assert t["status"] == "done", t.get("error")
    _show("③ 文献综述草稿", _final_output(t), 1200)

    # 4) 学术写作（文体=academic）→ 入章
    ws = Workspace(root=Path(tempfile.mkdtemp()))
    chapters = ChapterStore(str(db))
    tools = WritingTools(chapters, book_id="main", workspace=ws, model=model)
    intro = tools._clean_write(
        title="引言",
        intent="写一段论文引言（约150字）：注意力机制如何推动大语言模型发展",
        references="",
    )
    _show("④ 学术写作（引言）", intro, 500)
    assert client.post(
        "/api/chapters",
        json={"book_id": "main", "title": "第一章 引言", "content": intro},
    ).status_code == 200

    # 5) 学术检测（真实模型规则包）
    r = client.post(
        "/api/check", json={"text": intro, "target": "引言", "book_id": "main"}
    )
    findings = r.json().get("findings") or []
    print(f"\n⑤ 学术检测：{r.json().get('hard_count', len(findings))} 项发现")
    for f in findings[:2]:
        print(f"   - [{f.get('category')}] {str(f.get('message'))[:80]}")

    # 6) 引用导出 + LaTeX
    r = client.get(f"/api/library/{bids[0]}/citations?style=bibtex").json()
    _show("⑥a 引用条目（BibTeX）", str(r["entry"]), 350)
    tex = client.get("/api/export/book?format=latex&book_id=main").text
    has_sec = "\\section" in tex
    print(f"\n⑥b LaTeX 导出：{len(tex)} 字符，含 \\section → {has_sec}")


# 故意埋瑕疵的学术段落（术语漂移/口语化/无据断言/数据不一致）
FLAWED_ACADEMIC = (
    "本研究探讨了手机依赖这个问题。大学生们每天都离不开智能手机，"
    "显然手机依赖会严重影响睡眠质量，众所周知熬夜对身体不好。"
    "我们采用问卷调查法收集了数据，问卷显示了明显的负相关关系（r=-0.53）。"
    "结果表明手机依赖度越高睡眠越差，这证明了减少手机使用就能提高睡眠质量，"
    "相关性系数达到-0.5左右。综上所述，学校应该重视这个问题。"
)

REVIEW_COMMENTS = (
    "1. 创新性不足，与现有研究区别不明显；\n"
    "2. 实验仅使用问卷自报数据，缺乏客观测量；\n"
    "3. 部分表述口语化，如'每天都离不开'。"
)


def _real_model() -> Any:  # type: ignore[name-defined]

    from anyspark.models.deepseek import DeepSeekModel

    return DeepSeekModel()


def _app(model: Any, db: Path):  # type: ignore[name-defined]
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    return TestClient(build_app(model=model, db_path=db))


def _run_workflow(client, name: str, params: dict, timeout_s: int = 240) -> dict:
    tpls = client.get("/api/workflows").json()
    tpl = next(t for t in tpls if t["name"] == name)
    task_id = client.post(
        f"/api/workflows/{tpl['id']}/run", json={"book_id": "main", "params": params}
    ).json()["task_id"]
    t: dict = {}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(2)
    t["status"] = "timeout"
    return t


def _final_output(t: dict) -> str:
    """取终局节点（merge/finish）产出；node_states 非执行序，不能 reversed 取尾。"""
    ns = t.get("node_states") or []
    for n in ns:
        if n.get("node_id") in ("merge", "finish") and n.get("output"):
            return str(n["output"])
    for n in reversed(ns):
        if n.get("output"):
            return str(n["output"])
    return ""


def _show(title: str, text: str, limit: int = 900) -> None:
    print(f"\n{'─' * 20} {title} {'─' * 20}")
    print(text[:limit] + ("…（截断）" if len(text) > limit else ""))


def scenario_persona() -> None:
    """写作引擎文体切换：同一意图，academic 与 fiction 的人设与产出对比。"""
    from anyspark.server.tools_writing import WritingTools
    from anyspark.server.workspace import Workspace
    from anyspark.store.sqlite import ChapterStore

    model = _real_model()
    root = Path(tempfile.mkdtemp())
    ws = Workspace(root=root)
    chapters = ChapterStore(Path(tempfile.mkdtemp()) / "ch.db")
    tools = WritingTools(chapters, book_id="main", workspace=ws, model=model)
    intent = "写一段论文引言（约200字）：大学生手机依赖对睡眠质量的影响"
    for genre in ("academic", "fiction"):
        ws.write_genre("main", genre)
        text = tools._clean_write(title="测试", intent=intent, references="")
        _show(f"persona[{genre}] 产出", text, 500)


def scenario_check() -> None:
    """学术检测规则包：瑕疵段落 → 真实检测发现（应命中术语/语言规范等）。"""
    model = _real_model()
    db = Path(tempfile.mkdtemp()) / "app.db"
    client = _app(model, db)
    client.post("/api/genre", json={"genre": "academic", "book_id": "main"})
    r = client.post(
        "/api/check",
        json={"text": FLAWED_ACADEMIC, "target": "测试段落", "book_id": "main"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    report = str(data.get("report") or data)
    _show("check[academic] 检测报告", report, 1400)


def scenario_review() -> None:
    """审稿回复：真实意见 → 逐条回应 → 回复信草稿。"""
    model = _real_model()
    db = Path(tempfile.mkdtemp()) / "app.db"
    client = _app(model, db)
    from anyspark.store.sqlite import ChapterStore

    ChapterStore(str(db)).upsert(
        "main",
        "第一章 引言",
        "本研究通过问卷调查探讨大学生手机依赖与睡眠质量的关系，"
        "发现两者呈负相关，建议学校加强手机使用管理。",
        1,
    )
    t = _run_workflow(
        client,
        "审稿回复",
        {"comments": REVIEW_COMMENTS, "manuscript_title": "第一章 引言"},
    )
    assert t["status"] == "done", t.get("error")
    _show("review 回复信", _final_output(t))


def scenario_multiplatform() -> None:
    """多平台改写：一稿 → 公众号/小红书版本。"""
    model = _real_model()
    db = Path(tempfile.mkdtemp()) / "app.db"
    client = _app(model, db)
    from anyspark.store.sqlite import ChapterStore

    ChapterStore(str(db)).upsert(
        "main",
        "第一章",
        "研究发现大学生手机依赖与睡眠质量显著负相关：睡前刷短视频超1小时，"
        "入睡时间平均推迟40分钟。专家建议睡前一小时远离手机，培养阅读替代习惯。",
        1,
    )
    t = _run_workflow(
        client,
        "多平台改写",
        {"chapter_title": "第一章", "platforms": "公众号,小红书"},
    )
    assert t["status"] == "done", t.get("error")
    _show("multiplatform 交付稿", _final_output(t))


def scenario_proposal() -> None:
    """申报书起草：大纲 → 逐节起草 → 汇编。"""
    model = _real_model()
    db = Path(tempfile.mkdtemp()) / "app.db"
    client = _app(model, db)
    t = _run_workflow(
        client,
        "申报书起草",
        {
            "topic": "校园数字健康助手：基于使用习惯分析的大学生手机依赖干预小程序",
            "key_points": "行为数据本地分析;温和干预提醒;隐私不出手机;宿舍-社团联动推广",
        },
        timeout_s=300,
    )
    assert t["status"] == "done", t.get("error")
    _show("proposal 申报书草稿", _final_output(t), 1200)


def main() -> None:
    scenarios = {
        "persona": scenario_persona,
        "check": scenario_check,
        "review": scenario_review,
        "multiplatform": scenario_multiplatform,
        "proposal": scenario_proposal,
        "d2": scenario_d2,
        "project": scenario_project,
    }
    chosen = sys.argv[1:] or ["check"]
    for name in chosen:
        assert name in scenarios, f"未知场景：{name}（可选：{list(scenarios)} / all）"
    if "all" in chosen:
        chosen = list(scenarios)
    for name in chosen:
        print(f"\n{'=' * 25} 场景：{name} {'=' * 25}")
        scenarios[name]()


from typing import Any  # noqa: E402  # 置底避免循环观感无意义——保持导入集中在此

if __name__ == "__main__":
    main()
