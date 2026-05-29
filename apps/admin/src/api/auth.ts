import { api } from "./client";
import type { TokenResponse, User } from "@/types/api";

export const authApi = {
  async login(phone: string, password: string): Promise<TokenResponse> {
    const { data } = await api.post("/api/auth/login", { phone, password });
    return data;
  },
  async me(): Promise<User> {
    const { data } = await api.get("/api/auth/me");
    return data;
  },
  async logout(): Promise<void> {
    await api.post("/api/auth/logout");
  },
};
