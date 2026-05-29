import { api } from "./client";
import type { ProviderProfile } from "@/types/api";

export const providersApi = {
  async me(): Promise<ProviderProfile> {
    const { data } = await api.get("/api/providers/me");
    return data;
  },

  async updateMe(payload: {
    service_type?: string;
    vehicle_info?: string;
  }): Promise<ProviderProfile> {
    const { data } = await api.put("/api/providers/me", payload);
    return data;
  },

  async setAvailability(is_available: boolean): Promise<ProviderProfile> {
    const { data } = await api.put("/api/providers/availability", { is_available });
    return data;
  },

  async pingLocation(lat: number, lng: number): Promise<{
    provider_id: string;
    last_ping: string;
    is_available: boolean;
  }> {
    const { data } = await api.post("/api/providers/location", { lat, lng });
    return data;
  },
};
