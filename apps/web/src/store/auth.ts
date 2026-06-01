import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { AuthUser } from "@roadside/api-client";

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  setSession: (s: { accessToken: string; user: AuthUser }) => void;
  clear: () => void;
  isAuthed: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,
      setSession: ({ accessToken, user }) => set({ accessToken, user }),
      clear: () => set({ accessToken: null, user: null }),
      isAuthed: () => !!get().accessToken && !!get().user,
    }),
    {
      name: "roadside-web-auth",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
