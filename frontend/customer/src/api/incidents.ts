import { api } from "./client";
import type { Incident, IncidentListResponse } from "@/types/api";

export const incidentsApi = {
  /**
   * Submit an incident with optional image/voice. Returns the created incident id.
   */
  async create(payload: {
    lat: number;
    lng: number;
    description?: string;
    address?: string;
    image?: File | null;
    voice?: Blob | null;
  }): Promise<{ id: string; status: string; queued: boolean; message: string }> {
    const form = new FormData();
    form.append("lat", String(payload.lat));
    form.append("lng", String(payload.lng));
    if (payload.description) form.append("description", payload.description);
    if (payload.address) form.append("address", payload.address);
    if (payload.image) form.append("image", payload.image);
    if (payload.voice) {
      // voice may be a Blob from MediaRecorder; ensure filename for FastAPI
      const file = new File([payload.voice], "voice.webm", {
        type: payload.voice.type || "audio/webm",
      });
      form.append("voice", file);
    }
    const { data } = await api.post("/api/incidents", form);
    return data;
  },

  async listMine(limit = 20, offset = 0): Promise<IncidentListResponse> {
    const { data } = await api.get("/api/incidents/my", {
      params: { limit, offset },
    });
    return data;
  },

  async getOne(incidentId: string): Promise<Incident> {
    const { data } = await api.get(`/api/incidents/${incidentId}`);
    return data;
  },

  async close(incidentId: string, reason?: string): Promise<Incident> {
    const { data } = await api.put(`/api/incidents/${incidentId}/close`, { reason });
    return data;
  },
};
