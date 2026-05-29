import { api } from "./client";
import type {
  AdminQueryRequest,
  AdminQueryResponse,
  DashboardResponse,
  NotifyRequest,
  NotifyResponse,
  ReassignRequest,
  ReassignResponse,
} from "@/types/api";

export const adminApi = {
  async dashboard(): Promise<DashboardResponse> {
    const { data } = await api.get("/api/admin/dashboard");
    return data;
  },

  async notify(payload: NotifyRequest): Promise<NotifyResponse> {
    const { data } = await api.post("/api/admin/notify", payload);
    return data;
  },

  async query(payload: AdminQueryRequest): Promise<AdminQueryResponse> {
    const { data } = await api.post("/api/admin/query", payload);
    return data;
  },

  async reassign(
    incidentId: string,
    payload: ReassignRequest
  ): Promise<ReassignResponse> {
    const { data } = await api.put(
      `/api/admin/incidents/${incidentId}/reassign`,
      payload
    );
    return data;
  },

  async approveProvider(providerId: string): Promise<{ provider_id: string; approved: boolean }> {
    const { data } = await api.put(`/api/admin/providers/${providerId}/approve`);
    return data;
  },

  async suspendProvider(
    providerId: string,
    reason?: string
  ): Promise<{ provider_id: string; suspended: boolean; reason: string }> {
    const { data } = await api.put(
      `/api/admin/providers/${providerId}/suspend`,
      { reason }
    );
    return data;
  },
};
