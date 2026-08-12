import { apiFetch } from "./client";

/* ── 后端实际返回结构 ── */

export interface GraphEntity {
  id: string;
  book_id: string;
  name: string;
  entity_type: string;
  aliases: string[];
  description: string;
  state: string;
  first_chapter: string;
  last_chapter: string;
  first_order: number;
  last_order: number;
  weight: number;
  lines: string[];
}

export interface GraphRelation {
  id: string;
  book_id: string;
  from_id: string;
  from_name: string;
  to_id: string;
  to_name: string;
  rel_type: string;
  description: string;
  chapter_ref: string;
}

export interface GraphEvent {
  id: string;
  book_id: string;
  chapter_ref: string;
  chapter_order: number;
  time_point: string;
  label: string;
  description: string;
  involved: string[];
}

export interface GraphType {
  id: string;
  name: string;
  enabled: boolean;
  order_index: number;
  created_at: string;
}

/* ── 请求体 ── */

export interface CreateEntityRequest {
  name: string;
  entity_type: string;
  aliases?: string[];
  description?: string;
}

export interface UpdateEntityRequest {
  name?: string;
  entity_type?: string;
  aliases?: string[];
  description?: string;
  state?: string;
}

export interface CreateRelationRequest {
  from_name: string;
  to_name: string;
  rel_type: string;
  description?: string;
  chapter_ref?: string;
}

export interface UpdateRelationRequest {
  rel_type?: string;
  description?: string;
}

export interface CreateEventRequest {
  label: string;
  time_point?: string;
  chapter_ref?: string;
  chapter_order?: number;
  description?: string;
  involved?: string[];
}

export interface UpdateEventRequest {
  label?: string;
  time_point?: string;
  chapter_ref?: string;
  chapter_order?: number;
  description?: string;
  involved?: string[];
}

/* ── Entity CRUD ── */

export function createEntity(req: CreateEntityRequest): Promise<GraphEntity> {
  return apiFetch<GraphEntity>("/api/graph/entities", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function updateEntity(entityId: string, req: UpdateEntityRequest): Promise<GraphEntity> {
  return apiFetch<GraphEntity>(`/api/graph/entities/${entityId}`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

export function deleteEntity(entityId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/graph/entities/${entityId}`, {
    method: "DELETE",
  });
}

/* ── Relation CRUD ── */

export function createRelation(req: CreateRelationRequest): Promise<GraphRelation> {
  return apiFetch<GraphRelation>("/api/graph/relations", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function updateRelation(relationId: string, req: UpdateRelationRequest): Promise<GraphRelation> {
  return apiFetch<GraphRelation>(`/api/graph/relations/${relationId}`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

export function deleteRelation(relationId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/graph/relations/${relationId}`, {
    method: "DELETE",
  });
}

/* ── Event CRUD ── */

export function createEvent(req: CreateEventRequest): Promise<GraphEvent> {
  return apiFetch<GraphEvent>("/api/graph/events", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function updateEvent(eventId: string, req: UpdateEventRequest): Promise<GraphEvent> {
  return apiFetch<GraphEvent>(`/api/graph/events/${eventId}`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

export function deleteEvent(eventId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/graph/events/${eventId}`, {
    method: "DELETE",
  });
}
