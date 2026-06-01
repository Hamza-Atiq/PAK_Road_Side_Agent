import type { AxiosInstance } from "axios";
import type { UserRole } from "@roadside/types";

export interface AuthUser {
  id: string;
  phone: string;
  name: string | null;
  role: UserRole;
  is_active: boolean;
  is_phone_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: AuthUser;
}

export function makeAuthApi(api: AxiosInstance) {
  return {
    async login(phone: string, password: string): Promise<TokenResponse> {
      const { data } = await api.post("/api/auth/login", { phone, password });
      return data;
    },
    async register(payload: {
      phone: string;
      name: string;
      password: string;
      role: UserRole;
    }): Promise<{ user_id: string }> {
      const { data } = await api.post("/api/auth/register", payload);
      return data;
    },
    async verifyOtp(phone: string, code: string): Promise<TokenResponse> {
      const { data } = await api.post("/api/auth/verify-otp", { phone, code });
      return data;
    },
    async me(): Promise<AuthUser> {
      const { data } = await api.get("/api/auth/me");
      return data;
    },
    async logout(): Promise<void> {
      await api.post("/api/auth/logout");
    },
  };
}
