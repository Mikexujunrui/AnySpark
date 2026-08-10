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

export function listPlots(): Promise<PlotPoint[]> {
  return apiFetch<PlotPoint[]>("/api/plot");
}

export function generatePlot(settings?: string): Promise<PlotPoint[]> {
  return apiFetch<PlotPoint[]>("/api/plot", {
    method: "POST",
    body: JSON.stringify({ settings: settings ?? "" }),
  });
}

export function updatePlot(plotId: string, req: PlotPatch): Promise<PlotPoint> {
  return apiFetch<PlotPoint>(`/api/plot/${plotId}`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

export function addPlotItem(req: PlotItemCreate): Promise<PlotPoint> {
  return apiFetch<PlotPoint>("/api/plot/item", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function deletePlot(plotId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/plot/${plotId}`, {
    method: "DELETE",
  });
}
