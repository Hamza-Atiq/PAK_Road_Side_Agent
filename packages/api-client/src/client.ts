// HTTP client factory with single-flight JWT refresh.
// Apps provide an AuthBridge so this package stays independent of any one store.
//
// Usage:
//   import { createApi, registerAuthBridge } from "@roadside/api-client";
//   registerAuthBridge({ getAccessToken, setSession, clear });
//   export const api = createApi(import.meta.env.VITE_API_BASE_URL ?? "");

import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

export interface AuthBridge {
  getAccessToken: () => string | null;
  setSession: (data: { accessToken: string; user: unknown }) => void;
  clear: () => void;
}

let bridge: AuthBridge | null = null;

export function registerAuthBridge(b: AuthBridge): void {
  bridge = b;
}

export function createApi(baseURL: string): AxiosInstance {
  const instance = axios.create({ baseURL, withCredentials: true });

  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = bridge?.getAccessToken();
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
          { withCredentials: true },
        );
        const newToken: string | undefined = resp.data?.access_token;
        if (!newToken) return null;
        bridge?.setSession({ accessToken: newToken, user: resp.data.user });
        return newToken;
      } catch {
        bridge?.clear();
        return null;
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  instance.interceptors.response.use(
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
          return instance(original);
        }
      }
      return Promise.reject(error);
    },
  );

  return instance;
}
