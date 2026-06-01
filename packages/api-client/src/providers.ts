import type { AxiosInstance } from "axios";
import type { ServiceType } from "@roadside/types";

export interface ProviderProfile {
  id: string;
  user_id: string;
  name: string | null;
  phone: string;
  service_type: ServiceType | null;
  vehicle_info: string | null;
  is_available: boolean;
  rating: number | null;
  jobs_completed: number;
  last_lat: number | null;
  last_lng: number | null;
  last_ping: string | null;
  verification_status: "pending" | "approved" | "suspended" | null;
}

export function makeProvidersApi(api: AxiosInstance) {
  return {
    async me(): Promise<ProviderProfile> {
      const { data } = await api.get("/api/providers/me");
      return data;
    },
    async updateMe(payload: {
      service_type?: ServiceType;
      vehicle_info?: string;
    }): Promise<ProviderProfile> {
      const { data } = await api.put("/api/providers/me", payload);
      return data;
    },
    async setAvailability(isAvailable: boolean): Promise<ProviderProfile> {
      const { data } = await api.put("/api/providers/availability", {
        is_available: isAvailable,
      });
      return data;
    },
    async pingLocation(
      lat: number,
      lng: number,
    ): Promise<{ provider_id: string; last_ping: string; is_available: boolean }> {
      const { data } = await api.post("/api/providers/location", { lat, lng });
      return data;
    },
  };
}
