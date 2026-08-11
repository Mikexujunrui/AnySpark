import { apiGet, apiPost } from "./client";

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

// 工作区总览（含上传区文件列表，后端固定按 main 书）
export function listWorkspace(): Promise<WorkspaceOverview> {
  return apiGet<WorkspaceOverview>("/api/workspace");
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
