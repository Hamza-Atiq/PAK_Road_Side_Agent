// Zustand auth store — persists the access token + user in localStorage.
//
// We deliberately do NOT store the refresh token here; it lives in the
// HttpOnly cookie set by the backend, which JavaScript can't read.

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { User } from "@/types/api";

interface AuthState {
  accessToken: string | null;
  user: User | null;
  setSession: (s: { accessToken: string; user: User }) => void;
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
      name: "roadside-customer-auth",
      storage: createJSONStorage(() => localStorage),
    }
  )
);
