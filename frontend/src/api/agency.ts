import { apiGet, apiPost } from "./client";

export interface AgencyLevel {
  level_id: string;
  name: string;
  description: string;
  order: number;
  temperature: number;
}

export interface AgencyState {
  current: AgencyLevel;
  levels: AgencyLevel[];
}

export async function getAgency(): Promise<AgencyState> {
  return apiGet<AgencyState>("/api/agency");
}

export async function setAgency(levelId: string): Promise<AgencyLevel> {
  return apiPost<AgencyLevel>("/api/agency", { level_id: levelId });
}
