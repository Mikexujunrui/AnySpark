import { useEffect, useRef, useState } from "react";
import { useUploadStore } from "../stores/uploadStore";
import { uploadFileUrl, type IngestMode } from "../api/upload";
import PanelHeader from "./ui/PanelHeader";

interface UploadPanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
  bookId?: string; // S79：素材库按书（BookDetail 传当前书）
}

const MODE_LABELS: Record<IngestMode, string> = {
  auto: "自动判别",
  chapters: "强制拆章",
  card: "强制摘要卡",
};

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export default function UploadPanel({ open, onClose, embedded = false, bookId = "main" }: UploadPanelProps) {
  const uploads = useUploadStore((s) => s.uploads);
  const loading = useUploadStore((s) => s.loading);
  const error = useUploadStore((s) => s.error);
  const ingestMsg = useUploadStore((s) => s.ingestMsg);
  const fetchUploads = useUploadStore((s) => s.fetchUploads);
  const uploadAndIngest = useUploadStore((s) => s.uploadAndIngest);
  const ingest = useUploadStore((s) => s.ingest);
  const clearMsg = useUploadStore((s) => s.clearMsg);

  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<IngestMode>("auto");
  const [busyName, setBusyName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      fetchUploads(bookId);
      clearMsg();
      setFile(null);
      setMode("auto");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [open, fetchUploads, clearMsg]);

  if (!open) return null;

  const handleUpload = async () => {
    if (!file) return;
    setBusyName(file.name);
    await uploadAndIngest(file, mode, bookId);
    setBusyName(null);
  };

  const handleIngest = async (name: string, m: IngestMode) => {
    setBusyName(name);
    await ingest(name, m, bookId);
    setBusyName(null);
  };

  // S79：图片类型判断（素材库缩略图）
  function isImage(name: string): boolean {
    return /\.(png|jpe?g|gif|webp|bmp)$/i.test(name);
  }

  return (
    <div className={embedded ? "h-full flex flex-col" : "fixed inset-0 z-50 flex"}>
      {/* 遮罩 */}
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}

      {/* 面板 */}
      <div className={embedded ? "h-full w-full flex flex-col" : "relative ml-auto w-[560px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl"}>
        {/* 头部 */}
        <PanelHeader
          compact
          maxW={false}
          icon="upload"
          iconClass="text-sky-400"
          title="上传区 · 文档消化"
          desc="txt/md/docx 提取 → 规则拆章 → 摘要卡"
          actions={
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800 transition-colors" title="关闭">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          }
        />

        {/* 上传表单 */}
        <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.markdown,.docx,.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="text-xs text-zinc-400 file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:bg-zinc-700 file:text-zinc-200 file:text-xs hover:file:bg-zinc-600"
            />
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as IngestMode)}
              className="bg-zinc-800 text-zinc-300 text-xs px-2 py-1.5 rounded border border-zinc-700"
              title="消化模式"
            >
              {(Object.keys(MODE_LABELS) as IngestMode[]).map((m) => (
                <option key={m} value={m}>{MODE_LABELS[m]}</option>
              ))}
            </select>
            <button
              onClick={handleUpload}
              disabled={!file || loading}
              className="text-xs px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded shrink-0"
            >
              {busyName ? "上传消化中..." : "上传并消化"}
            </button>
          </div>
          <p className="text-[11px] text-zinc-600">
            支持 txt / md / docx / pdf + 图片（≤20MB）。文本按模式消化：长文拆章、短文本摘要卡；图片作为素材存放（未来多模态接入）。
          </p>
        </div>

        {/* 提示区 */}
        {error && (
          <div className="mx-4 mt-3 px-3 py-2 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded">
            {error}
          </div>
        )}
        {ingestMsg && (
          <div className="mx-4 mt-3 px-3 py-2 bg-green-500/10 border border-green-500/30 text-green-400 text-xs rounded whitespace-pre-wrap">
            {ingestMsg}
          </div>
        )}

        {/* 上传区文件列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            上传区（{uploads.length}）
          </h3>
          {loading && !uploads.length ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : uploads.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">上传区暂无文件</p>
          ) : (
            uploads.map((u) => (
              <div
                key={u.name}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 flex items-center justify-between gap-3"
              >
                {isImage(u.name) ? (
                  <img
                    src={uploadFileUrl(bookId, u.name)}
                    alt={u.name}
                    className="w-14 h-14 rounded object-cover bg-zinc-900 shrink-0"
                    title={u.name}
                  />
                ) : (
                  <div className="w-14 h-14 rounded bg-zinc-900 border border-zinc-800 flex items-center justify-center shrink-0 text-zinc-600">
                    <span className="text-[9px] px-1 truncate max-w-full">{(u.name.split(".").pop() || "file").toUpperCase()}</span>
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-sm text-zinc-200 truncate" title={u.name}>{u.name}</p>
                  <p className="text-[11px] text-zinc-500">{formatSize(u.size)}{isImage(u.name) ? " · 图片素材" : ""}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value as IngestMode)}
                    className="bg-zinc-800 text-zinc-300 text-[11px] px-1.5 py-1 rounded border border-zinc-700"
                  >
                    {(Object.keys(MODE_LABELS) as IngestMode[]).map((m) => (
                      <option key={m} value={m}>{MODE_LABELS[m]}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleIngest(u.name, mode)}
                    disabled={loading}
                    className="text-[11px] px-2 py-1 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-zinc-200 rounded"
                  >
                    {busyName === u.name ? "消化中..." : "消化"}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
