# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Reviews, volumes, materials, workflows, plot chains, and tasks storage."""

import logging
from datetime import datetime
from pathlib import Path

from core.book_locks import book_lock
from core.config import DATA_DIR
from core.errors import NotFoundError

logger = logging.getLogger(__name__)


class MetaStoreMixin:
    """Mixin providing review/volume/material/workflow/plot-chain/task methods.  Requires BaseStore."""

    def load_reviews(self, book_id: str) -> list[dict]:
        return self._read_json(self._reviews_file(book_id))

    def save_review(self, book_id: str, review: dict):
        with book_lock(book_id):
            reviews = self.load_reviews(book_id)
            reviews.append(review)
            self._write_json(self._reviews_file(book_id), reviews)

    def update_review(self, book_id: str, review: dict):
        """Replace an existing review (matched by id) instead of appending a duplicate."""
        with book_lock(book_id):
            reviews = self.load_reviews(book_id)
            for i, r in enumerate(reviews):
                if r.get("id") == review.get("id"):
                    reviews[i] = review
                    self._write_json(self._reviews_file(book_id), reviews)
                    return
            reviews.append(review)
            self._write_json(self._reviews_file(book_id), reviews)

    def get_review(self, book_id: str, review_id: str) -> dict:
        reviews = self.load_reviews(book_id)
        for r in reviews:
            if r.get("id") == review_id:
                return r
        raise NotFoundError(f"评审报告不存在: {review_id}")

    def delete_review(self, book_id: str, review_id: str):
        with book_lock(book_id):
            reviews = self.load_reviews(book_id)
            reviews = [r for r in reviews if r.get("id") != review_id]
            self._write_json(self._reviews_file(book_id), reviews)

    # ── Volumes ──

    def load_volumes(self, book_id: str) -> list[dict]:
        return self._read_json(self._volumes_file(book_id))

    def save_volumes(self, book_id: str, volumes: list[dict]):
        self._write_json(self._volumes_file(book_id), volumes)

    def add_volume(self, book_id: str, title: str, story_line: str = "") -> dict:
        import uuid
        with book_lock(book_id):
            volumes = self.load_volumes(book_id)
            # Dedup: if same title already exists, return existing volume
            existing = next((v for v in volumes if v.get("title") == title), None)
            if existing:
                return existing
            # Use uuid-based ID to avoid timestamp collisions in rapid creation
            vid = str(int(datetime.now().timestamp() * 1000)) + uuid.uuid4().hex[:4]
            volume = {
                "id": vid,
                "title": title,
                "storyLine": story_line,
                "chapters": [],
                "order": len(volumes),
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
            volumes.append(volume)
            self.save_volumes(book_id, volumes)
            return volume

    def _resolve_volume(self, volumes: list[dict], volume_id: str) -> dict | None:
        """Find volume by exact ID match, then prefix match (for truncated IDs from list_volumes)."""
        # Exact match
        exact = next((v for v in volumes if v["id"] == volume_id), None)
        if exact:
            return exact
        # Prefix match
        prefix_matches = [v for v in volumes if v["id"].startswith(volume_id)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        return None

    def _resolve_workflow(self, workflows: list[dict], workflow_id: str) -> dict | None:
        """Find workflow by exact ID match, then prefix match (for truncated IDs from list_workflows)."""
        # Exact match
        exact = next((w for w in workflows if w["id"] == workflow_id), None)
        if exact:
            return exact
        # Prefix match
        prefix_matches = [w for w in workflows if w["id"].startswith(workflow_id)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        return None

    def update_volume(self, book_id: str, volume_id: str, data: dict) -> dict:
        with book_lock(book_id):
            volumes = self.load_volumes(book_id)
            vol = self._resolve_volume(volumes, volume_id)
            if not vol:
                raise NotFoundError(f"分卷不存在: {volume_id}")
            for key in ("title", "storyLine", "order"):
                if key in data:
                    if key == "order":
                        vol[key] = int(data[key])
                    else:
                        vol[key] = data[key]
            vol["updatedAt"] = datetime.now().isoformat()
            self.save_volumes(book_id, volumes)
            return vol

    def delete_volume(self, book_id: str, volume_id: str):
        with book_lock(book_id):
            volumes = self.load_volumes(book_id)
            vol = self._resolve_volume(volumes, volume_id)
            if not vol:
                return  # Already deleted or not found, silent
            volumes = [v for v in volumes if v["id"] != vol["id"]]
            # Re-index order
            for i, v in enumerate(volumes):
                v["order"] = i
            self.save_volumes(book_id, volumes)

    def add_chapter_to_volume(self, book_id: str, volume_id: str, chapter_id: str):
        with book_lock(book_id):
            volumes = self.load_volumes(book_id)
            self.load_chapters(book_id)
            vol = self._resolve_volume(volumes, volume_id)
            if not vol:
                raise NotFoundError(f"分卷不存在: {volume_id}")
            if chapter_id not in vol["chapters"]:
                vol["chapters"].append(chapter_id)
                vol["updatedAt"] = datetime.now().isoformat()
            # Remove from other volumes (use resolved vol["id"] for comparison, not prefix)
            for v in volumes:
                if v["id"] != vol["id"] and chapter_id in v["chapters"]:
                    v["chapters"] = [c for c in v["chapters"] if c != chapter_id]
                    v["updatedAt"] = datetime.now().isoformat()
            self.save_volumes(book_id, volumes)

    def remove_chapter_from_volume(self, book_id: str, chapter_id: str):
        with book_lock(book_id):
            volumes = self.load_volumes(book_id)
            for v in volumes:
                if chapter_id in v["chapters"]:
                    v["chapters"] = [c for c in v["chapters"] if c != chapter_id]
                    v["updatedAt"] = datetime.now().isoformat()
            self.save_volumes(book_id, volumes)

    # ── Reference Books ──

    def set_reference_books(self, book_id: str, ref_ids: list[str]):
        with book_lock("_global"):
            books = self.load_books()
            for b in books:
                if b["id"] == book_id:
                    b["referenceBookIds"] = ref_ids
                    b["updatedAt"] = datetime.now().isoformat()
                    break
            self.save_books(books)

    def get_reference_books(self, book_id: str) -> list[str]:
        try:
            book = self.get_book(book_id)
            return book.get("referenceBookIds", [])
        except (KeyError, TypeError):
            return []

    # ── Materials (global, shared across all projects) ──

    _materials_file = DATA_DIR / "materials.json"

    def load_materials(self) -> list[dict]:
        return self._read_json(self._materials_file)

    def save_materials(self, mats: list[dict]):
        self._write_json(self._materials_file, mats)

    def add_material(self, title: str, content: str, tags: list[str] | None = None,
                     source: str = "", source_url: str = "") -> dict:
        with book_lock("_global"):
            mats = self.load_materials()
            mid = f"m_{int(datetime.now().timestamp() * 1000)}"
            mat = {
                "id": mid,
                "title": title,
                "content": content,
                "tags": tags or [],
                "source": source,
                "source_url": source_url,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
            mats.append(mat)
            self.save_materials(mats)
            return mat

    def update_material(self, mid: str, data: dict) -> dict:
        with book_lock("_global"):
            mats = self.load_materials()
            resolved = self._resolve_by_id(mats, mid)
            if not resolved:
                raise NotFoundError(f"资料不存在: {mid}")
            full_id = resolved["id"]
            for m in mats:
                if m["id"] == full_id:
                    for key in ("title", "content", "tags", "source", "source_url"):
                        if key in data:
                            m[key] = data[key]
                    m["updatedAt"] = datetime.now().isoformat()
                    self.save_materials(mats)
                    return m
            raise NotFoundError(f"资料不存在: {mid}")

    def delete_material(self, mid: str):
        with book_lock("_global"):
            mats = self.load_materials()
            resolved = self._resolve_by_id(mats, mid)
            if resolved:
                mats = [m for m in mats if m["id"] != resolved["id"]]
                self.save_materials(mats)

    def get_material(self, mid: str) -> dict:
        mats = self.load_materials()
        resolved = self._resolve_by_id(mats, mid)
        if resolved:
            return resolved
        raise NotFoundError(f"资料不存在: {mid}")

    # ── Material Subscriptions (per-book) ──

    def load_material_subs(self, book_id: str) -> list[str]:
        return self._read_json(self._material_subs_file(book_id))

    def save_material_subs(self, book_id: str, subs: list[str]):
        self._write_json(self._material_subs_file(book_id), subs)

    def subscribe_material(self, book_id: str, mid: str):
        # Resolve truncated ID to full ID first
        mats = self.load_materials()
        full_id = self._resolve_full_id(mats, mid)
        with book_lock(book_id):
            subs = self.load_material_subs(book_id)
            if full_id not in subs:
                subs.append(full_id)
                self.save_material_subs(book_id, subs)

    def unsubscribe_material(self, book_id: str, mid: str):
        # Resolve truncated ID to full ID first
        mats = self.load_materials()
        full_id = self._resolve_full_id(mats, mid)
        with book_lock(book_id):
            subs = self.load_material_subs(book_id)
            subs = [s for s in subs if s != full_id]
            self.save_material_subs(book_id, subs)

    # ── Workflows (global, shared across all projects) ──

    _global_wfs_file = DATA_DIR / "workflows.json"

    def _wf_subs_file(self, book_id: str) -> Path:
        return DATA_DIR / f"workflow_subs_{book_id}.json"

    def load_workflows_global(self) -> list[dict]:
        return self._read_json(self._global_wfs_file)

    def save_workflows_global(self, wfs: list[dict]):
        self._write_json(self._global_wfs_file, wfs)

    def load_workflows(self, book_id: str) -> list[dict]:
        subs = self.load_workflow_subs(book_id)
        all_wfs = self.load_workflows_global()
        return [w for w in all_wfs if w["id"] in subs]

    def load_workflow_subs(self, book_id: str) -> list[str]:
        return self._read_json(self._wf_subs_file(book_id))

    def save_workflow_subs(self, book_id: str, subs: list[str]):
        self._write_json(self._wf_subs_file(book_id), subs)

    def add_workflow(self, book_id: str, name: str, steps: list[dict]) -> dict:
        with book_lock("_global"):
            wfs = self.load_workflows_global()
            wid = str(int(datetime.now().timestamp() * 1000))
            wf = {
                "id": wid,
                "name": name,
                "steps": steps,
                "createdAt": datetime.now().isoformat(),
            }
            wfs.append(wf)
            self.save_workflows_global(wfs)
        # Auto-subscribe the creating project
        with book_lock(book_id):
            subs = self.load_workflow_subs(book_id)
            subs.append(wid)
            self.save_workflow_subs(book_id, subs)
        return wf

    def delete_workflow(self, book_id: str, wid: str):
        with book_lock("_global"):
            wfs = self.load_workflows_global()
            wf = self._resolve_workflow(wfs, wid)
            if wf:
                wfs = [w for w in wfs if w["id"] != wf["id"]]
                self.save_workflows_global(wfs)

    def subscribe_workflow(self, book_id: str, wid: str):
        with book_lock("_global"):
            wfs = self.load_workflows_global()
            wf = self._resolve_workflow(wfs, wid)
            full_id = wf["id"] if wf else wid
        with book_lock(book_id):
            subs = self.load_workflow_subs(book_id)
            if full_id not in subs:
                subs.append(full_id)
                self.save_workflow_subs(book_id, subs)

    def unsubscribe_workflow(self, book_id: str, wid: str):
        with book_lock("_global"):
            wfs = self.load_workflows_global()
            wf = self._resolve_workflow(wfs, wid)
            full_id = wf["id"] if wf else wid
        with book_lock(book_id):
            subs = self.load_workflow_subs(book_id)
            subs = [s for s in subs if s != full_id]
            self.save_workflow_subs(book_id, subs)

    def get_workflow(self, wid: str) -> dict:
        wfs = self.load_workflows_global()
        wf = self._resolve_workflow(wfs, wid)
        if wf:
            return wf
        raise NotFoundError(f"工作流不存在: {wid}")

    def update_workflow(self, wid: str, updates: dict) -> dict:
        """Update workflow name and/or steps. Returns updated workflow."""
        with book_lock("_global"):
            wfs = self.load_workflows_global()
            wf = self._resolve_workflow(wfs, wid)
            if not wf:
                raise NotFoundError(f"工作流不存在: {wid}")
            if "name" in updates and updates["name"]:
                wf["name"] = updates["name"]
            if "steps" in updates and updates["steps"]:
                wf["steps"] = updates["steps"]
            wf["updatedAt"] = datetime.now().isoformat()
            self.save_workflows_global(wfs)
            return wf

    # ── Plot Chain (剧情链) ──

    def load_plot_chains(self, book_id: str) -> list[dict]:
        return self._read_json(self._plot_chain_file(book_id), [])

    def save_plot_chains(self, book_id: str, chains: list[dict]):
        self._write_json(self._plot_chain_file(book_id), chains)

    def save_plot_chain(self, book_id: str, chain: dict) -> dict:
        """Save a plot chain. Auto-generates id and created_at."""
        with book_lock(book_id):
            chains = self.load_plot_chains(book_id)
            chain["id"] = f"chain_{int(datetime.now().timestamp() * 1000)}"
            chain["created_at"] = datetime.now().isoformat()
            chains.append(chain)
            self.save_plot_chains(book_id, chains)
            return chain

    def get_plot_chain(self, book_id: str, chain_id: str) -> dict:
        """Get plot chain by exact ID or prefix match."""
        chains = self.load_plot_chains(book_id)
        # Exact match first
        chain = next((c for c in chains if c.get("id") == chain_id), None)
        if chain:
            return chain
        # Prefix match
        prefix_matches = [c for c in chains if c.get("id", "").startswith(chain_id)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        raise NotFoundError(f"剧情链不存在: {chain_id}")

    def get_latest_plot_chain(self, book_id: str) -> dict | None:
        chains = self.load_plot_chains(book_id)
        return chains[-1] if chains else None

    # ── Agent Tasks (待办清单) ──

    def load_task_lists(self, book_id: str) -> list[dict]:
        data = self._read_json(self._tasks_file(book_id), {"task_lists": []})
        return data.get("task_lists", [])

    def _save_task_lists(self, book_id: str, lists: list[dict]):
        self._write_json(self._tasks_file(book_id), {"task_lists": lists})

    def create_task_list(self, book_id: str, title: str, items: list[dict]) -> dict:
        """Create a new task list. Auto-removes completed lists to prevent stale accumulation."""
        with book_lock(book_id):
            lists = self.load_task_lists(book_id)
            lists = [t for t in lists if t.get("status") not in ("done", "failed")]
            tl = {
                "id": f"tasks_{int(datetime.now().timestamp() * 1000)}",
                "title": title,
                "created_at": datetime.now().isoformat(),
                "status": "pending",
                "items": [
                    {
                        "index": i,
                        "label": item.get("label", f"任务{i+1}"),
                        "status": "pending",
                        "tool": item.get("tool", ""),
                        "result_summary": None,
                        "updated_at": None,
                    }
                    for i, item in enumerate(items)
                ],
            }
            lists.append(tl)
            self._save_task_lists(book_id, lists)
            return tl

    def get_task_list(self, book_id: str, task_list_id: str = None) -> dict:
        """Get task list by ID, or latest if None."""
        lists = self.load_task_lists(book_id)
        if task_list_id:
            # Exact match first, then prefix
            tl = next((t for t in lists if t["id"] == task_list_id), None)
            if not tl:
                prefix_matches = [t for t in lists if t["id"].startswith(task_list_id)]
                if len(prefix_matches) == 1:
                    tl = prefix_matches[0]
        else:
            tl = lists[-1] if lists else None
        if not tl:
            raise NotFoundError("任务清单不存在")
        return tl

    def update_task_item(self, book_id: str, task_list_id: str, index: int,
                         status: str, result_summary: str = None) -> dict:
        """Update a task item's status. Auto-calculates list status."""
        with book_lock(book_id):
            lists = self.load_task_lists(book_id)
            tl = self._find_task_list(lists, task_list_id)
            item = next((it for it in tl["items"] if it["index"] == index), None)
            if not item:
                raise NotFoundError(f"任务项 {index} 不存在")
            item["status"] = status
            if result_summary:
                item["result_summary"] = result_summary
            item["updated_at"] = datetime.now().isoformat()
            # Auto-calculate list status
            statuses = [it["status"] for it in tl["items"]]
            if all(s in ("done", "skipped") for s in statuses):
                tl["status"] = "done"
            elif any(s == "in_progress" for s in statuses):
                tl["status"] = "in_progress"
            elif any(s == "failed" for s in statuses):
                tl["status"] = "failed"
            else:
                tl["status"] = "pending"
            self._save_task_lists(book_id, lists)
            return tl

    def add_task_items(self, book_id: str, task_list_id: str, items: list[dict]) -> dict:
        """Add items to existing task list."""
        with book_lock(book_id):
            lists = self.load_task_lists(book_id)
            tl = self._find_task_list(lists, task_list_id)
            start_idx = len(tl["items"])
            for i, item in enumerate(items):
                tl["items"].append({
                    "index": start_idx + i,
                    "label": item.get("label", ""),
                    "status": "pending",
                    "tool": item.get("tool", ""),
                    "result_summary": None,
                    "updated_at": None,
                })
            self._save_task_lists(book_id, lists)
            return tl

    def _find_task_list(self, lists: list[dict], task_list_id: str = None) -> dict:
        """Helper to find task list by ID or latest."""
        if task_list_id:
            tl = next((t for t in lists if t["id"] == task_list_id), None)
            if not tl:
                prefix_matches = [t for t in lists if t["id"].startswith(task_list_id)]
                if len(prefix_matches) == 1:
                    tl = prefix_matches[0]
        else:
            tl = lists[-1] if lists else None
        if not tl:
            raise NotFoundError("任务清单不存在")
        return tl


def _split_paragraphs(content: str) -> list[dict]:
    """Split content into paragraphs, returning list of {index, text, start, end}."""
    paragraphs = []
    parts = content.split('\n\n')
    pos = 0
    for i, part in enumerate(parts):
        paragraphs.append({"index": i, "text": part, "start": pos, "end": pos + len(part)})
        pos += len(part) + 2  # +2 for '\n\n'
    return paragraphs


def _locate_in_paragraph(paragraphs: list[dict], segment_id: int,
                         confirm: str) -> tuple[int, str] | None:
    """Locate text within a specific paragraph using segment_id + confirm.

    Returns (absolute_position_in_content, matched_text) or None.
    """
    if segment_id < 0 or segment_id >= len(paragraphs):
        return None
    para = paragraphs[segment_id]
    if not confirm:
        # No confirm, return whole paragraph as anchor
        return (para["start"], para["text"])
    # Search within this paragraph
    result = _fuzzy_find(para["text"], confirm)
    if result:
        rel_pos, matched = result
        return (para["start"] + rel_pos, matched)
    return None


def _fuzzy_find(content: str, find: str) -> tuple[int, str] | None:
    """Multi-strategy text locator for patch operations.

    Returns (position_in_content, actual_matched_text) so the caller uses
    the real text for replacement length. Returns None if all strategies fail.

    Strategies: exact → strip → full-width norm → shorter anchor → whitespace norm
    """
    # 1. Exact
    pos = content.find(find)
    if pos >= 0:
        return (pos, find)

    # 2. strip
    stripped = find.strip()
    if stripped and stripped != find:
        pos = content.find(stripped)
        if pos >= 0:
            return (pos, stripped)

    # 3. Full-width normalization
    import re
    half_to_full = str.maketrans(
        ",?!;:()",
        "\uff0c\uff1f\uff01\uff1b\uff1a\uff08\uff09")
    full_to_half = str.maketrans(
        "\uff0c\uff1f\uff01\uff1b\uff1a\uff08\uff09",
        ",?!;:()")
    norm_find = find.translate(full_to_half).translate(half_to_full)
    if norm_find != find:
        pos = content.find(norm_find)
        if pos >= 0:
            return (pos, norm_find)

    # 4. Shorter anchor (first 60%, at least 10 chars)
    short_len = max(10, int(len(find) * 0.6))
    shorter = find[:short_len]
    if shorter != find and shorter.strip():
        pos = content.find(shorter)
        if pos >= 0:
            return (pos, shorter)

    # 5. Whitespace-normalized — safest: returns the actual matched content span
    norm_find = re.sub(r'\s+', '', find)
    norm_content = re.sub(r'\s+', '', content)
    if norm_find and len(norm_find) > 5:
        pos = norm_content.find(norm_find)
        if pos >= 0:
            # Map back: find the actual content span that corresponds to norm_find
            cleaned_len = 0
            orig_start = 0
            for i, c in enumerate(content):
                if cleaned_len >= pos:
                    orig_start = i
                    break
                if not c.isspace():
                    cleaned_len += 1
            # Find the actual end in original content
            cleaned_end = 0
            orig_end = orig_start
            for i in range(orig_start, len(content)):
                if cleaned_end >= len(norm_find):
                    orig_end = i
                    break
                if not content[i].isspace():
                    cleaned_end += 1
                orig_end = i + 1
            actual = content[orig_start:orig_end]
            return (orig_start, actual)

    return None



