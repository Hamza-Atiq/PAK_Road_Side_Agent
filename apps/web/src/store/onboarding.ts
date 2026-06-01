import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export interface Vehicle {
  make: string;
  model: string;
  year: string;
  color: string;
  plate: string;
}

interface OnboardingState {
  hasCompletedOnboarding: boolean;
  locationPermissionRequested: boolean;
  vehicle: Vehicle | null;
  setVehicle: (v: Vehicle) => void;
  markLocationRequested: () => void;
  completeOnboarding: () => void;
  reset: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      hasCompletedOnboarding: false,
      locationPermissionRequested: false,
      vehicle: null,
      setVehicle: (v) => set({ vehicle: v }),
      markLocationRequested: () => set({ locationPermissionRequested: true }),
      completeOnboarding: () => set({ hasCompletedOnboarding: true }),
      reset: () =>
        set({ hasCompletedOnboarding: false, locationPermissionRequested: false, vehicle: null }),
    }),
    {
      name: "roadside-web-onboarding",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
