import { apiGet, apiPost } from "./client";

export interface AgencyLevel {
  id: string;
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

export async function setAgency(levelId: string): Promise<AgencyState> {
  return apiPost<AgencyState>("/api/agency", { level_id: levelId });
}
