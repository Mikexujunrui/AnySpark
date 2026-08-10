import { apiGet, apiPost, apiDelete } from "./client";

export interface Material {
  id: string;
  title: string;
  topic: string;
  key_points: string[];
  key_settings: string[];
  characters: string[];
  terms: string[];
  purpose: string;
  source_text: string;
  created_at: string;
}

export interface MaterialCreate {
  text: string;
  title?: string;
  purpose?: "style" | "fact" | "both";
}

export async function listMaterials(): Promise<Material[]> {
  return apiGet<Material[]>("/api/materials");
}

export async function getMaterial(id: string): Promise<Material> {
  return apiGet<Material>(`/api/materials/${id}`);
}

export async function createMaterial(data: MaterialCreate): Promise<Material> {
  return apiPost<Material>("/api/materials", data);
}

export async function deleteMaterial(id: string): Promise<{ ok: boolean; id: string }> {
  return apiDelete<{ ok: boolean; id: string }>(`/api/materials/${id}`);
}
