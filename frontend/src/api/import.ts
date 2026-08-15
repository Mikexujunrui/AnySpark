// Import — V4 上传/消化映射：uploadDocument→/api/upload；拆章/导入→/api/ingest。
// batchExtractKnowledge→/api/graph/extract。
import { post } from "./http";

export async function uploadDocument(file: File, bookId?: string): Promise<unknown> {
  // 文件 → base64（V4 /api/upload 零依赖 base64 JSON）
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  const dataB64 = dataUrl.split(",")[1] || "";
  return post("/api/upload", { filename: file.name, data_b64: dataB64, book_id: bookId || "main" });
}

export async function detectChapters(): Promise<unknown> {
  return Promise.resolve({ chapters: [] });
}

export async function importChapters(file: File, bookId?: string): Promise<unknown> {
  const res = await uploadDocument(file, bookId);
  return post("/api/ingest", { filename: (res as any).name || file.name, mode: "chapters", book_id: bookId || "main" });
}

export async function batchExtractKnowledge(text: string, bookId?: string): Promise<unknown> {
  return post("/api/graph/extract", { chapter_ref: "批量抽取", text, book_id: bookId || "main" });
}
