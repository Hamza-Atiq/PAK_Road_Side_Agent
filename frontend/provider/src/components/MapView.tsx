// Leaflet view with one or two pins (customer + provider) and an optional
// straight-line route between them. We render a straight line instead of a
// real driving polyline because the provider panel doesn't have ORS credentials —
// the actual route ETA comes from the backend DispatchAgent.

import { MapContainer, Marker, Polyline, TileLayer, useMap } from "react-leaflet";
import { useEffect } from "react";
import L from "leaflet";

// Two icons so customer and provider are visually distinct
const CUSTOMER_ICON = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

// Tint provider icon green via a CSS filter wrapper (avoids extra asset hosting)
const PROVIDER_ICON = L.divIcon({
  className: "",
  html: '<div style="width:18px;height:18px;border-radius:50%;background:#059669;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.4)"></div>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 14);
      return;
    }
    const bounds = L.latLngBounds(points.map((p) => L.latLng(p[0], p[1])));
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [map, points]);
  return null;
}

interface Props {
  customerLat: number;
  customerLng: number;
  providerLat?: number | null;
  providerLng?: number | null;
  height?: string;
}

export function MapView({
  customerLat,
  customerLng,
  providerLat,
  providerLng,
  height = "320px",
}: Props) {
  const hasProvider = providerLat != null && providerLng != null;
  const points: [number, number][] = hasProvider
    ? [[customerLat, customerLng], [providerLat!, providerLng!]]
    : [[customerLat, customerLng]];

  return (
    <div
      style={{ height }}
      className="overflow-hidden rounded-lg ring-1 ring-slate-200"
    >
      <MapContainer center={[customerLat, customerLng]} zoom={13} scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={[customerLat, customerLng]} icon={CUSTOMER_ICON} />
        {hasProvider && (
          <>
            <Marker position={[providerLat!, providerLng!]} icon={PROVIDER_ICON} />
            <Polyline
              positions={[
                [customerLat, customerLng],
                [providerLat!, providerLng!],
              ]}
              pathOptions={{ color: "#059669", weight: 4, opacity: 0.7, dashArray: "6 8" }}
            />
          </>
        )}
        <FitBounds points={points} />
      </MapContainer>
    </div>
  );
}
