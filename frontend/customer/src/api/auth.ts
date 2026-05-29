import { api } from "./client";
import type { TokenResponse, User } from "@/types/api";

export const authApi = {
  async register(payload: {
    phone: string;
    name: string;
    password: string;
    role: "customer" | "provider";
    email?: string;
  }): Promise<{ message: string }> {
    const { data } = await api.post("/api/auth/register", payload);
    return data;
  },

  async verifyOtp(phone: string, code: string): Promise<TokenResponse> {
    const { data } = await api.post("/api/auth/verify-otp", { phone, code });
    return data;
  },

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
