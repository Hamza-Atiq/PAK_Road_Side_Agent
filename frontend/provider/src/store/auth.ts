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
      name: "roadside-provider-auth",
      storage: createJSONStorage(() => localStorage),
    }
  )
);
