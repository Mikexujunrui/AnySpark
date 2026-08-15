import { apiDelete, apiGet, apiPost } from "./client";

// 上传区文件项（GET /api/workspace → uploads）
export interface UploadItem {
  name: string;
  size: number;
  path: string;
}

// 工作区总览（S48：上传存档 / 章节文件 / 卡片）
export interface WorkspaceOverview {
  project: string;
  root: string;
  uploads: UploadItem[];
  chapters: { filename: string; path: string }[];
  cards: { filename: string; path: string }[];
}

// 上传结果（POST /api/upload）
export interface UploadResult {
  ok: boolean;
  name: string;
  path: string;
  size: number;
}

// 消化结果（POST /api/ingest）——card 模式产出摘要卡，chapters 模式拆成多章
export type IngestResult =
  | {
      ok: boolean;
      kind: "card";
      title: string;
      card_file: string;
      material_id: string;
    }
  | {
      ok: boolean;
      kind: "chapters";
      count: number;
      chapters: { order: number; title: string; chars: number }[];
    };

export type IngestMode = "auto" | "chapters" | "card";

// 上传文件到上传区（base64 JSON，零新依赖）
export function uploadFile(
  filename: string,
  dataB64: string,
  bookId: string = "main"
): Promise<UploadResult> {
  return apiPost<UploadResult>("/api/upload", {
    filename,
    data_b64: dataB64,
    book_id: bookId,
  });
}

// 工作区总览（S48：上传存档 / 章节文件 / 卡片；S79 按书）
export function listWorkspace(bookId = "main"): Promise<WorkspaceOverview> {
  return apiGet<WorkspaceOverview>(`/api/workspace?book_id=${bookId}`);
}

// S79：上传区文件访问 URL（图片缩略图/下载）
export function uploadFileUrl(bookId: string, name: string): string {
  return `/api/upload/${encodeURIComponent(bookId)}/${encodeURIComponent(name)}`;
}

// 消化上传区文件：长文拆章 / 短文本摘要卡
export function ingestFile(
  filename: string,
  mode: IngestMode = "auto",
  bookId: string = "main"
): Promise<IngestResult> {
  return apiPost<IngestResult>("/api/ingest", {
    filename,
    mode,
    book_id: bookId,
  });
}

// S144：删除上传区素材（传错/重复清理）
export function deleteUploadFile(
  filename: string,
  bookId: string = "main"
): Promise<{ ok: boolean; name: string }> {
  return apiDelete<{ ok: boolean; name: string }>(
    `/api/upload/${encodeURIComponent(bookId)}/${encodeURIComponent(filename)}`
  );
}
