// useGeolocation — wraps the browser Geolocation API with explicit states.

import { useState } from "react";

export interface Position {
  lat: number;
  lng: number;
  accuracy: number;
}

interface State {
  position: Position | null;
  loading: boolean;
  error: string | null;
}

export function useGeolocation() {
  const [state, setState] = useState<State>({
    position: null,
    loading: false,
    error: null,
  });

  const request = () => {
    if (!("geolocation" in navigator)) {
      setState({
        position: null,
        loading: false,
        error: "Geolocation not supported by this browser",
      });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setState({
          position: {
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
          },
          loading: false,
          error: null,
        }),
      (err) =>
        setState({
          position: null,
          loading: false,
          error: err.message || "Unable to get location",
        }),
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 }
    );
  };

  return { ...state, request };
}
