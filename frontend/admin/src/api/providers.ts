import { api } from "./client";
import type { ProviderListResponse } from "@/types/api";

export const providersApi = {
  async list(params: {
    is_available?: boolean;
    is_approved?: boolean;
    service_type?: string;
  } = {}): Promise<ProviderListResponse> {
    const { data } = await api.get("/api/providers", { params });
    return data;
  },
};
