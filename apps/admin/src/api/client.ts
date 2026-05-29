// Same single-flight JWT refresh pattern as customer/provider — works with the
// admin auth store because it depends only on the same interface.

import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/auth";

const baseURL = import.meta.env.VITE_API_BASE_URL || "";

export const api = axios.create({ baseURL, withCredentials: true });

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.set("Authorization", `Bearer ${token}`);
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshOnce(): Promise<string | null> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    try {
      const resp = await axios.post(
        `${baseURL}/api/auth/refresh`,
        {},
        { withCredentials: true }
      );
      const newToken: string = resp.data?.access_token;
      if (!newToken) return null;
      useAuthStore.getState().setSession({
        accessToken: newToken,
        user: resp.data.user,
      });
      return newToken;
    } catch {
      useAuthStore.getState().clear();
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined;
    if (
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !original.url?.endsWith("/api/auth/refresh") &&
      !original.url?.endsWith("/api/auth/login")
    ) {
      original._retried = true;
      const newToken = await refreshOnce();
      if (newToken) {
        original.headers.set("Authorization", `Bearer ${newToken}`);
        return api(original);
      }
    }
    return Promise.reject(error);
  }
);
