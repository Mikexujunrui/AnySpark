"""scripts/current_state.py — 生成 docs/CURRENT-STATE.md（系统当前状态全景，自动扫描）。

主人质询驱动（S142）：PROGRESS.md 是历史流水，缺"最终状态/当前状态"视图。
本脚本**机制自动生成**（非手写→永不过期）：扫描真实代码装配 + 读真实 DB，
产出可提交的当前状态文档。哲学保持：机制（扫描/统计/渲染）硬编码，内容
（工具描述/模板名/数据统计）来自真实系统。

用法：
    uv run python scripts/current_state.py          # 生成 docs/CURRENT-STATE.md
    uv run python scripts/current_state.py --json   # 只输出 JSON（数据源，供前端/脚本用）

输出维度：
- 系统规模：阶段数 / API 路由数 / agent 工具数 / workflow 模板数 / 测试数 / 包行数
- 能力清单：46 工具分组 + 前端 tab 入口 + workflow 模板
- 数据状态：章节 / 图谱 / 说明书 / skill / 模板 / 信号 / 材料 / 模型
- 人类可见映射：工具 → 前端入口（审计成果固化）
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sh(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=120)
        return (r.stdout or "").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 1. 系统规模（静态）
# ---------------------------------------------------------------------------
def count_stages() -> int:
    txt = (ROOT / "docs" / "PROGRESS.md").read_text(encoding="utf-8")
    return len(re.findall(r"^## S\d+", txt, flags=re.M))


def count_lines() -> dict[str, int]:
    out = {}
    for pkg in ("core", "align", "app", "workflow", "explore", "check", "template", "graph"):
        d = ROOT / "packages" / pkg / "src" / "anyspark"
        if not d.exists():
            continue
        n = 0
        for f in d.rglob("*.py"):
            n += sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
        out[pkg] = n
    return out


def count_tests() -> int:
    """统计测试函数数（正则：def test_；不含参数化展开——规模参考）。"""
    n = 0
    for f in ROOT.rglob("test_*.py"):
        if "__pycache__" in str(f) or ".venv" in str(f):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        n += len(re.findall(r"^def test_", txt, flags=re.M))
    return n


# ---------------------------------------------------------------------------
# 2. 运行时装配（真实工具/模板/路由）
# ---------------------------------------------------------------------------
def _fake_model() -> object:
    class M:
        model_name = "state-probe"

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="好的。")

    return M()


def collect_runtime() -> dict[str, object]:
    """真实装配 build_app + build_toolkit：工具清单/模板/路由。"""
    from anyspark.server.app import build_app

    app = build_app(model=_fake_model())  # type: ignore[arg-type]
    deps = app.state.deps
    # 路由：openapi 强制展开（_IncludedRouter 懒加载）
    api_paths = sorted(app.openapi()["paths"].keys())
    # 模板
    tpls = deps.workflow_store.list_templates()
    # 工具：真实装配（与 agent_factory 同款）
    from anyspark.core import ToolRegistry
    from anyspark.server.toolkit import ToolContext, build_toolkit

    reg = build_toolkit(
        ToolRegistry(),
        ToolContext(
            chapters=deps.chapters,
            workspace=deps.workspace,
            model=deps.model,
            graph=deps.graph,
            plots=deps.plots,
            plans=deps.plans,
            settings=deps.settings,
            materials=deps.materials,
            ext_tools=deps.ext_tools,
            dim_store=deps.dim_store,
            manual=deps.manual,
            skills_store=deps.skills,
            style_prefs=None,
            workflow_store=deps.workflow_store,
            workflow_engine=deps.workflow_engine,
            workflow_generator=deps.workflow_generator,
            play_engine=deps.play_engine,
            review_panel=deps.review_panel,
            skill_generator=deps.skill_generator,
            signals=deps.signals,
            book_id="main",
            subagent_deps=deps,
            templates=[],
            # S145：补传 library——此前与 agent_factory 同漏，生成的工具清单缺
            # reference_lookup（审计装配自带缺陷，曾掩盖该工具生产缺席）
            library=deps.library,
        ),
    )
    specs = reg.specs()
    return {
        "api_paths": api_paths,
        "templates": [t["name"] for t in tpls],
        "tools": sorted(s.name for s in specs),
    }


# ---------------------------------------------------------------------------
# 3. 数据状态（真实 DB）
# ---------------------------------------------------------------------------
def collect_data() -> dict[str, object]:
    from anyspark.server.app import build_app

    app = build_app(model=_fake_model())  # type: ignore[arg-type]
    deps = app.state.deps
    out: dict[str, object] = {}
    out["chapters"] = len(deps.chapters.list_by_book("main"))
    try:
        out["entities"] = len(deps.graph.list_entities("main"))
    except Exception:
        out["entities"] = 0
    try:
        out["manual"] = len(deps.manual.list("project", "main"))
    except Exception:
        out["manual"] = 0
    try:
        out["skills"] = len(deps.skills.list_skills())
    except Exception:
        out["skills"] = 0
    try:
        out["materials"] = len(deps.materials.list("main"))
    except Exception:
        out["materials"] = 0
    try:
        out["model"] = deps.models.active().model
    except Exception:
        out["model"] = "?"
    return out


# ---------------------------------------------------------------------------
# 4. 前端入口（静态扫描）
# ---------------------------------------------------------------------------
def collect_frontend() -> dict[str, object]:
    bd = (ROOT / "frontend" / "src" / "components" / "BookDetail.tsx").read_text(encoding="utf-8")
    tabs = re.findall(r"key: '([a-z]+)', label: '([^']+)'", bd)
    return {"tabs": tabs}


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def render_md(
    meta: dict[str, object],
    rt: dict[str, object],
    data: dict[str, object],
    fe: dict[str, object],
    lines: dict[str, int],
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    commit = _sh(["git", "log", "-1", "--oneline"])
    stages = count_stages()
    tests = count_tests()

    tools = rt["tools"]
    assert isinstance(tools, list)
    tools = [str(t) for t in tools]
    tpls = rt["templates"]
    assert isinstance(tpls, list)
    tpls = [str(t) for t in tpls]
    tabs = fe["tabs"]
    assert isinstance(tabs, list)
    tabs = [(str(g), str(t)) for g, t in tabs]

    # 工具分组（对齐 toolkit.py 装配语义）
    groups = {
        "写作": [
            t
            for t in tools
            if t
            in (
                "list_chapters",
                "read_chapter",
                "write_chapter",
                "patch_chapter",
                "read_file",
                "write_file",
            )
        ],
        "领域查证/登记": [
            t
            for t in tools
            if t.startswith(
                (
                    "graph_",
                    "skill_",
                    "read_setting",
                    "read_material",
                    "material_",
                    "reference_lookup",
                    "search_chapters",
                    "read_context",
                )
            )
        ],
        "情节/计划/探索": [
            t
            for t in tools
            if t.startswith(("plot_", "plan_", "path_explore", "role_play", "explore_direction"))
        ],
        "心智/信号": [t for t in tools if t.startswith("mind_")],
        "批量/检测/收编": [
            t
            for t in tools
            if t
            in ("batch_rewrite", "batch_review", "check_text", "ingest_document", "register_tool")
        ],
        "工作流/推演/评审/委派": [
            t
            for t in tools
            if t.startswith(("workflow_", "play_", "panel_")) or t in ("run_subagent",)
        ],
        "网络/工具": [t for t in tools if t in ("search_web", "fetch_page")],
    }

    md = []
    md.append("# AnySpark v4 系统当前状态（自动生成）\n")
    md.append(
        f"> 生成：{now} · commit `{commit}` · 阶段 S{stages} · **非手写**：\n"
        "> 由 `scripts/current_state.py` 扫描真实代码/DB 产出，改动后重跑即更新\n"
    )
    md.append("## 一、系统规模\n")
    api_paths = rt["api_paths"]
    assert isinstance(api_paths, list)
    md.append("| 维度 | 数值 |")
    md.append("|---|---|")
    md.append(f"| 已交付阶段 | **S{stages}** |")
    md.append(f"| API 路由 | **{len(api_paths)}** 个 |")
    md.append(f"| Agent 工具 | **{len(tools)}** 个 |")
    md.append(f"| Workflow 模板 | **{len(tpls)}** 个 |")
    md.append(f"| 前端入口 | **{len(tabs)}** 个 tab |")
    md.append(f"| 测试 | **{tests}** 个 |")
    total_lines = sum(lines.values())
    line_detail = ", ".join(f"{k} {v}" for k, v in sorted(lines.items()))
    md.append(f"| 后端代码 | **{total_lines}** 行（{line_detail}） |")
    md.append("")
    md.append("## 二、能力清单\n")
    md.append(f"### Agent 工具（{len(tools)} 个，全量注入主循环 LLM）\n")
    for gname, items in groups.items():
        if items:
            md.append(f"- **{gname}（{len(items)}）**：`{'` `'.join(items)}`")
    md.append("")
    md.append("### Workflow 预置模板\n")
    for t in tpls:
        md.append(f"- {t}")
    md.append("")
    md.append("### 前端入口（人类可见）\n")
    # 功能 tab 与模式徽标（Pro/Split/Flash/Custom）区分
    mode_tabs = {"quality", "split", "flash", "custom"}
    func_tabs = [(g, t) for g, t in tabs if t not in mode_tabs]
    md.append(
        f"功能 tab {len(func_tabs)} 个 + 模式徽标 {len(mode_tabs)} 个（Pro/Split/Flash/Custom）：\n"
    )
    for g, t in func_tabs:
        md.append(f"- `{t}`（{g}）")
    md.append("")
    md.append("## 三、数据状态（真实库 data/anyspark.db）\n")
    md.append("| 数据 | 数量 |")
    md.append("|---|---|")
    md.append(f"| 章节 | **{data['chapters']}** |")
    md.append(f"| 图谱实体 | **{data['entities']}** |")
    md.append(f"| 说明书条目 | **{data['manual']}** |")
    md.append(f"| skill 技巧 | **{data['skills']}** |")
    md.append(f"| 资料/灵感 | **{data['materials']}** |")
    md.append(f"| 当前模型 | `{data['model']}` |")
    md.append("")
    md.append("## 四、人类可见映射（审计成果：AI 产出 → 人能看到）\n")
    md.append("| AI 能力 | 人类查看入口 |")
    md.append("|---|---|")
    md.append("| 章节读/写/改写 | 章节 tab（稿纸）+ 版本历史/恢复 |")
    md.append("| 图谱查证/登记 | 知识库 tab |")
    md.append("| 伏笔/计划 | 伏笔 tab + 大纲 tab |")
    md.append("| 技巧（skill） | 技巧 tab（按 type 分组+包徽标） |")
    md.append("| 资料/灵感 | 资料 tab |")
    md.append("| 批量改写/审读 | 批量 tab（工作流模式+确认闸门+回滚） |")
    md.append("| 工作流模板/任务 | 工作流 tab + 任务轮询 + 断点续跑/批级回滚 |")
    md.append("| AI 笔记/文件（write_file 产物） | **AI文件 tab**（S141 新增） |")
    md.append("| 推演/评审团 | 互动推演 tab + 评审团 tab |")
    md.append("| 网络搜索/精确检索 | 对话流 + 搜索 tab 的 AI 检索入口 |")
    md.append("")
    md.append("---")
    md.append("*由 `uv run python scripts/current_state.py` 重新生成*")
    return "\n".join(md)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    rt = collect_runtime()
    data = collect_data()
    fe = collect_frontend()
    lines = count_lines()

    if args.json:
        payload = {
            "meta": {"stages": count_stages(), "commit": _sh(["git", "log", "-1", "--oneline"])},
            "runtime": rt,
            "data": data,
            "frontend": fe,
            "lines": lines,
            "tests": count_tests(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    md = render_md({}, rt, data, fe, lines)
    (ROOT / "docs" / "CURRENT-STATE.md").write_text(md, encoding="utf-8")
    print(f"✅ 已生成 docs/CURRENT-STATE.md（{len(md)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
