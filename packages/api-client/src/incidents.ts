import type { AxiosInstance } from "axios";
import type { IncidentStatus, ServiceType } from "@roadside/types";

export interface Incident {
  id: string;
  customer_id: string;
  provider_id: string | null;
  status: IncidentStatus;
  lat: number;
  lng: number;
  address: string | null;
  description: string | null;
  diagnosis: string | null;
  service_type: ServiceType | null;
  image_url: string | null;
  voice_url: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  reason: string | null;
  provider?: {
    id: string;
    name: string | null;
    phone: string;
    rating: number | null;
    vehicle_info: string | null;
    last_lat: number | null;
    last_lng: number | null;
  } | null;
}

export interface IncidentListResponse {
  items: Incident[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateIncidentPayload {
  lat: number;
  lng: number;
  description?: string;
  address?: string;
  service_type?: ServiceType;
  image?: File | null;
  voice?: Blob | null;
}

export function makeIncidentsApi(api: AxiosInstance) {
  return {
    async create(payload: CreateIncidentPayload): Promise<{
      id: string;
      status: IncidentStatus;
      queued: boolean;
      message: string;
    }> {
      const form = new FormData();
      form.append("lat", String(payload.lat));
      form.append("lng", String(payload.lng));
      if (payload.description) form.append("description", payload.description);
      if (payload.address) form.append("address", payload.address);
      if (payload.service_type) form.append("service_type", payload.service_type);
      if (payload.image) form.append("image", payload.image);
      if (payload.voice) {
        const file = new File([payload.voice], "voice.webm", {
          type: payload.voice.type || "audio/webm",
        });
        form.append("voice", file);
      }
      const { data } = await api.post("/api/incidents", form);
      return data;
    },

    async listMine(limit = 20, offset = 0): Promise<IncidentListResponse> {
      const { data } = await api.get("/api/incidents/my", { params: { limit, offset } });
      return data;
    },

    async listAssigned(includeHistory = false): Promise<IncidentListResponse> {
      const { data } = await api.get("/api/incidents/assigned", {
        params: { include_history: includeHistory },
      });
      return data;
    },

    async getOne(incidentId: string): Promise<Incident> {
      const { data } = await api.get(`/api/incidents/${incidentId}`);
      return data;
    },

    async updateStatus(
      incidentId: string,
      newStatus: IncidentStatus,
      reason?: string,
    ): Promise<Incident> {
      const { data } = await api.put(`/api/incidents/${incidentId}/status`, {
        new_status: newStatus,
        reason,
      });
      return data;
    },

    async close(incidentId: string, reason?: string): Promise<Incident> {
      const { data } = await api.put(`/api/incidents/${incidentId}/close`, { reason });
      return data;
    },
  };
}
