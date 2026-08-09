import { apiFetch } from "./client";

export interface GraphEntity {
  id: string;
  name: string;
  entity_type: string;
  description?: string;
  aliases?: string[];
  properties?: Record<string, unknown>;
  created_at: string;
}

export interface GraphRelation {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  description?: string;
  created_at: string;
}

export interface GraphEvent {
  id: string;
  name: string;
  event_type?: string;
  description?: string;
  created_at: string;
}

export interface GraphType {
  id: string;
  name: string;
  enabled?: boolean;
}

export function listEntities(q?: string, entityType?: string): Promise<GraphEntity[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (entityType) params.set("entity_type", entityType);
  const qs = params.toString();
  return apiFetch<GraphEntity[]>(`/api/graph/entities${qs ? `?${qs}` : ""}`);
}

export function listRelations(): Promise<GraphRelation[]> {
  return apiFetch<GraphRelation[]>("/api/graph/relations");
}

export function listEvents(): Promise<GraphEvent[]> {
  return apiFetch<GraphEvent[]>("/api/graph/events");
}

export function listGraphTypes(): Promise<GraphType[]> {
  return apiFetch<GraphType[]>("/api/graph/types");
}
