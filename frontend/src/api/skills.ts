import { apiFetch } from "./client";

export interface Skill {
  id: string;
  name: string;
  description?: string;
  content: string;
  tags?: string;
  type?: string;
  target?: string;
  ext?: string;
  pack_id?: string;
  enabled?: boolean;
  created_at: string;
  updated_at: string;
}

export function listSkills(): Promise<Skill[]> {
  return apiFetch<Skill[]>("/api/skills");
}

export function createSkill(
  name: string,
  content: string,
  description?: string,
  target?: string
): Promise<Skill> {
  return apiFetch<Skill>("/api/skills", {
    method: "POST",
    body: JSON.stringify({ name, content, description, target }),
  });
}

export function updateSkill(
  id: string,
  data: { name?: string; content?: string; description?: string; target?: string; enabled?: boolean }
): Promise<Skill> {
  return apiFetch<Skill>(`/api/skills/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteSkill(id: string): Promise<void> {
  return apiFetch<void>(`/api/skills/${id}`, {
    method: "DELETE",
  });
}

// ── S103 技能草稿（书库/资料提炼 → 人工确认转正） ──
export interface SkillDraft {
  id: string;
  name: string;
  description?: string;
  content: string;
  example?: string;
  tags?: string;
  target?: string;
  source?: string;
  created_at: string;
}

export function listSkillDrafts(): Promise<SkillDraft[]> {
  return apiFetch<SkillDraft[]>("/api/skills/drafts");
}

export function promoteSkillDraft(draftId: string): Promise<Skill> {
  return apiFetch<Skill>(`/api/skills/drafts/${draftId}/promote`, {
    method: "POST",
  });
}

export function deleteSkillDraft(draftId: string): Promise<void> {
  return apiFetch<void>(`/api/skills/drafts/${draftId}`, {
    method: "DELETE",
  });
}

// ── S118 提案 D：skill 文件导入导出（内容生态货币）──

export function exportSkillFile(skillId: string): void {
  // 导出标准 skill 文件（front-matter 五段式）——原生 fetch 拿 blob（apiFetch 是 JSON-only）
  fetch(`/api/skills/${skillId}/export`)
    .then((res) => {
      if (!res.ok) throw new Error(`导出失败: ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // 从 Content-Disposition 提取文件名（filename*=UTF-8''...），fallback skill.md
      const cd = "";
      a.download = cd || "skill.md";
      a.click();
      URL.revokeObjectURL(url);
    })
    .catch((e) => console.error("导出 skill 失败", e));
}

export interface SkillImportResult {
  ok: boolean;
  kind?: string;
  title?: string;
  draft_id?: string;
  error?: string;
}

export async function importSkillFile(file: File, bookId = "main"): Promise<SkillImportResult> {
  // 复用上传区 + ingest 判别路由（S118）：上传 → ingest 识别 front-matter skill → 草稿
  const b64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] || "");
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  const up = await apiFetch<{ ok: boolean }>("/api/upload", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, data_b64: b64, book_id: bookId }),
  });
  if (!up.ok) return { ok: false, error: "上传失败" };
  try {
    const ing = await apiFetch<SkillImportResult>("/api/ingest", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, book_id: bookId }),
    });
    if (ing.kind === "skill") {
      return { ok: true, kind: "skill", title: ing.title, draft_id: ing.draft_id };
    }
    return { ok: true, kind: ing.kind, title: ing.title, error: "未识别为 skill（已按普通文档消化）" };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}
