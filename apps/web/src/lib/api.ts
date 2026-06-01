// Single api instance for this app — wires the @roadside/api-client to the Zustand auth store.
import {
  createApi,
  makeAuthApi,
  makeIncidentsApi,
  makeProvidersApi,
  registerAuthBridge,
  type AuthUser,
} from "@roadside/api-client";
import { useAuthStore } from "@/store/auth";

const baseURL = import.meta.env.VITE_API_BASE_URL || "";

registerAuthBridge({
  getAccessToken: () => useAuthStore.getState().accessToken,
  setSession: ({ accessToken, user }) =>
    useAuthStore.getState().setSession({ accessToken, user: user as AuthUser }),
  clear: () => useAuthStore.getState().clear(),
});

export const api = createApi(baseURL);
export const authApi = makeAuthApi(api);
export const incidentsApi = makeIncidentsApi(api);
export const providersApi = makeProvidersApi(api);
