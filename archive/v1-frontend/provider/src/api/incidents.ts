import { api } from "./client";
import type { Incident, IncidentListResponse, IncidentStatus } from "@/types/api";

export const incidentsApi = {
  async listAssigned(): Promise<IncidentListResponse> {
    const { data } = await api.get("/api/incidents/assigned");
    return data;
  },

  async listHistory(limit = 50, offset = 0): Promise<IncidentListResponse> {
    const { data } = await api.get("/api/incidents/assigned", {
      params: { include_history: true, limit, offset },
    });
    return data;
  },

  async getOne(incidentId: string): Promise<Incident> {
    const { data } = await api.get(`/api/incidents/${incidentId}`);
    return data;
  },

  async updateStatus(
    incidentId: string,
    new_status: IncidentStatus,
    reason?: string
  ): Promise<Incident> {
    const { data } = await api.put(`/api/incidents/${incidentId}/status`, {
      new_status,
      reason,
    });
    return data;
  },
};
