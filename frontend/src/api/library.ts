import { apiDelete, apiGet, apiPost, apiPut } from "./client";

export interface LibraryBook {
  id: string;
  name: string;
  source: string;
  chapters: number;
  created_at: string;
}

export interface RefItem {
  type: "library" | "project";
  id: string;
  name?: string;
  source?: string;
  chapters?: number;
  path?: string;
}

// 书库
export async function listLibrary(): Promise<LibraryBook[]> {
  return apiGet<LibraryBook[]>("/api/library");
}

export async function createLibraryBook(name: string): Promise<LibraryBook> {
  return apiPost<LibraryBook>("/api/library", { name });
}

export async function importLibraryText(
  bookId: string,
  content: string,
  title?: string,
): Promise<{ ok: boolean; book_id: string; chapters: number }> {
  return apiPost("/api/library/import", { book_id: bookId, content, title: title || "" });
}

export async function deleteLibraryBook(bookId: string): Promise<{ ok: boolean }> {
  return apiDelete(`/api/library/${bookId}`);
}

// S103：书库 → skill 提炼（拆书模式，生成草稿待确认）
export async function refineLibrarySkill(
  bookId: string,
  hint = "",
): Promise<{
  ok: boolean;
  draft: { id: string; name: string };
  drafts?: { id: string; name: string }[];
}> {
  return apiPost(`/api/library/${bookId}/refine-skill`, { hint });
}

// 项目-参考书关联
export async function getReferences(bookId: string): Promise<RefItem[]> {
  return apiGet<RefItem[]>(`/api/books/${bookId}/references`);
}

export async function setReferences(
  bookId: string,
  refs: { type: "library" | "project"; id: string }[],
): Promise<{ ok: boolean; book_id: string; refs: RefItem[] }> {
  return apiPut(`/api/books/${bookId}/references`, { refs });
}
