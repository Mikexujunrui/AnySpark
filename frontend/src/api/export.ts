// 导出 API

export function exportBook(format: "txt" | "md" | "epub" = "md"): void {
  window.open(`/api/export/book?format=${format}`, "_blank");
}

export function exportChapter(chapterId: string, format: "txt" | "md" = "txt"): void {
  window.open(`/api/chapters/${chapterId}/export?format=${format}`, "_blank");
}
