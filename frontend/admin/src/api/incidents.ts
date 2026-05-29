import { api } from "./client";
import type {
  Incident,
  IncidentListResponse,
  IncidentStatus,
} from "@/types/api";

export const incidentsApi = {
  async list(params: {
    status?: IncidentStatus | null;
    limit?: number;
    offset?: number;
  } = {}): Promise<IncidentListResponse> {
    const { data } = await api.get("/api/incidents", {
      params: {
        status: params.status || undefined,
        limit: params.limit ?? 25,
        offset: params.offset ?? 0,
      },
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
      new_status, reason,
    });
    return data;
  },

  async close(incidentId: string, reason?: string): Promise<Incident> {
    const { data } = await api.put(`/api/incidents/${incidentId}/close`, { reason });
    return data;
  },
};
