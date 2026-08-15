import { create } from "zustand";
import {
  uploadFile,
  ingestFile,
  deleteUploadFile,
  listWorkspace,
  type UploadItem,
  type IngestResult,
  type IngestMode,
} from "../api/upload";

// File → base64（去掉 dataURL 前缀），20MB 上限与后端一致
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

interface UploadState {
  uploads: UploadItem[];
  loading: boolean;
  error: string | null;
  // 消化结果消息（成功/失败提示）
  ingestMsg: string | null;

  fetchUploads: (bookId?: string) => Promise<void>;
  uploadAndIngest: (file: File, mode: IngestMode, bookId?: string) => Promise<void>;
  ingest: (filename: string, mode: IngestMode, bookId?: string) => Promise<void>;
  deleteUpload: (filename: string, bookId?: string) => Promise<void>;
  clearMsg: () => void;
}

export const useUploadStore = create<UploadState>((set, get) => ({
  uploads: [],
  loading: false,
  error: null,
  ingestMsg: null,

  fetchUploads: async (bookId = "main") => {
    set({ loading: true, error: null });
    try {
      const ws = await listWorkspace(bookId);
      set({ uploads: ws.uploads, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  uploadAndIngest: async (file, mode, bookId = "main") => {
    set({ loading: true, error: null, ingestMsg: null });
    try {
      if (file.size > 20 * 1024 * 1024) {
        throw new Error("文件超过 20MB 上限");
      }
      const dataB64 = await fileToBase64(file);
      const up = await uploadFile(file.name, dataB64, bookId);
      // 上传成功后立即按所选模式消化（图片等非文本文件无消化路径，仅存档）
      const result = await ingestFile(up.name, mode, bookId);
      const msg = formatIngestMsg(result);
      set({ ingestMsg: msg, loading: false });
      await get().fetchUploads();
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  ingest: async (filename, mode, bookId = "main") => {
    set({ loading: true, error: null, ingestMsg: null });
    try {
      const result = await ingestFile(filename, mode, bookId);
      set({ ingestMsg: formatIngestMsg(result), loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  clearMsg: () => set({ ingestMsg: null, error: null }),

  // S144：删除上传区素材
  deleteUpload: async (filename, bookId = "main") => {
    set({ loading: true, error: null });
    try {
      await deleteUploadFile(filename, bookId);
      await get().fetchUploads(bookId);
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));

function formatIngestMsg(result: IngestResult): string {
  if (result.kind === "card") {
    return `已生成摘要卡《${result.title}》（${result.card_file}）`;
  }
  return `已拆成 ${result.count} 章：${result.chapters
    .map((c) => `#${c.order} ${c.title}`)
    .join("、")}`;
}
