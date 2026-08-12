import { apiFetch } from "./client";

/* ── 关键点/伏笔 ── */

export interface PlotPoint {
  id: string;
  book_id: string;
  category: string;
  content: string;
  chapter_ref: string;
  status: string; // open | resolved
  attention: string; // care | ignore
  priority: string; // must | soft
  planted_order: number;
  resolved_chapter: string;
  created_at: string;
}

export interface PlotItemCreate {
  content: string;
  category?: string;
  chapter_ref?: string;
  priority?: string;
  planted_order?: number;
}

export interface PlotPatch {
  status?: string;
  attention?: string;
  priority?: string;
  resolved_chapter?: string;
}

// S101c：全部按 book_id 隔离（此前无参读 main 的伏笔——跨项目泄漏）
export function listPlots(bookId: string): Promise<PlotPoint[]> {
  return apiFetch<PlotPoint[]>(`/api/plot?book_id=${encodeURIComponent(bookId)}`);
}

export function generatePlot(bookId: string, settings?: string): Promise<PlotPoint[]> {
  return apiFetch<PlotPoint[]>("/api/plot", {
    method: "POST",
    body: JSON.stringify({ book_id: bookId, settings: settings ?? "" }),
  });
}

export function updatePlot(plotId: string, req: PlotPatch): Promise<PlotPoint> {
  return apiFetch<PlotPoint>(`/api/plot/${plotId}`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

export function addPlotItem(bookId: string, req: PlotItemCreate): Promise<PlotPoint> {
  return apiFetch<PlotPoint>("/api/plot/item", {
    method: "POST",
    body: JSON.stringify({ ...req, book_id: bookId }),
  });
}

export function deletePlot(plotId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/plot/${plotId}`, {
    method: "DELETE",
  });
}
