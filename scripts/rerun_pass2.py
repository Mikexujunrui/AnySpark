"""Re-run Pass 2 foreshadow resolution matching with fixed code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.graph_store import get_store
from data.json_store import json_store
from core.llm_client import chat as llm_chat

BOOK_ID = "1781418567324"
store = get_store(BOOK_ID)

# Reset all foreshadows back to open
store._run(
    "MATCH (f:Fore {project_id: $pid}) WHERE f.status = $s SET f.status = $new",
    {"pid": BOOK_ID, "s": "dangling", "new": "open"}
)
print("Reset dangling -> open")

store._run(
    "MATCH (f:Fore {project_id: $pid}) WHERE f.status = $s SET f.status = $new, f.resolved = false",
    {"pid": BOOK_ID, "s": "resolved", "new": "open"}
)
print("Reset resolved -> open")

# Load chapters
chapters = json_store.load_chapters(BOOK_ID)
print(f"Loaded {len(chapters)} chapters")

# Verify chapter content loads correctly
for i, ch in enumerate(chapters[:3]):
    if "versions" in ch:
        versions = ch.get("versions", [])
        view = versions[-1] if versions else {}
    else:
        view = ch
    content = view.get("content", "")
    title = view.get("title", "")
    print(f"  Ch{i+1}: {len(content)} chars, title={title[:25]}")

# Re-run Pass 2
print("\n=== Running Pass 2 ===")
result = store.match_foreshadow_resolutions(chapters, llm_chat=llm_chat)
print(f"Pass 2: matched={result['matched']}, unmatched={result['unmatched']}, dangling={result['dangling']}, total={result['total']}")

# Check final status
fores = store.list_foreshadows()
open_fs = [f for f in fores if f.status == "open"]
resolved_fs = [f for f in fores if f.status == "resolved"]
dangling_fs = [f for f in fores if f.status == "dangling"]
print(f"\nFinal: {len(open_fs)} open, {len(resolved_fs)} resolved, {len(dangling_fs)} dangling")

# Show resolved foreshadows
print("\n=== Resolved Foreshadows ===")
for f in resolved_fs:
    print(f"  [RESOLVED] {f.text[:50]}")
    print(f"    plant={f.plant_chapter}, resolve={f.resolve_chapter}")
    print(f"    resolution={f.resolution_text[:60]}")

# Show a few dangling
print("\n=== Dangling Foreshadows (first 5) ===")
for f in dangling_fs[:5]:
    kw = f.resolve_keywords[:3] if f.resolve_keywords else []
    print(f"  [DANGLING] {f.text[:50]}")
    print(f"    plant={f.plant_chapter}, kw={kw}, conf={f.confidence}")
