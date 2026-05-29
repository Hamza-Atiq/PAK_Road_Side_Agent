// Thin Leaflet wrapper. Two use cases:
//
// 1. Read-only display with a single pin (incident location).
// 2. Editable pin: drag to correct the auto-detected GPS position.

import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import { useEffect } from "react";
import L from "leaflet";

// Leaflet's default marker icons assume webpack-style asset paths. With Vite
// we need to point at the CDN copies or imported assets. Use CDN URLs since
// we already load the CSS from unpkg in index.html.
const ICON = new L.Icon({
  iconUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = ICON;

interface Props {
  lat: number;
  lng: number;
  /** If set, clicks on the map move the marker and fire onMove. */
  editable?: boolean;
  onMove?: (lat: number, lng: number) => void;
  zoom?: number;
  height?: string;
}

function ClickCatcher({
  onMove,
}: {
  onMove: (lat: number, lng: number) => void;
}) {
  useMapEvents({
    click(e) {
      onMove(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

// Keep the map centered on the marker when props change
function CenterUpdater({ lat, lng }: { lat: number; lng: number }) {
  const map = (window as any).__leafletMap_lastInstance as L.Map | undefined;
  useEffect(() => {
    if (map) map.setView([lat, lng]);
  }, [lat, lng, map]);
  return null;
}

export function MapView({
  lat,
  lng,
  editable = false,
  onMove,
  zoom = 14,
  height = "320px",
}: Props) {
  return (
    <div
      style={{ height }}
      className="overflow-hidden rounded-lg ring-1 ring-slate-200"
    >
      <MapContainer
        center={[lat, lng]}
        zoom={zoom}
        scrollWheelZoom
        whenReady={() => {
          // expose for CenterUpdater (best-effort, not load-bearing)
        }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker
          position={[lat, lng]}
          draggable={editable}
          eventHandlers={
            editable && onMove
              ? {
                  dragend(e) {
                    const m = e.target as L.Marker;
                    const { lat: nlat, lng: nlng } = m.getLatLng();
                    onMove(nlat, nlng);
                  },
                }
              : undefined
          }
        />
        {editable && onMove && <ClickCatcher onMove={onMove} />}
        <CenterUpdater lat={lat} lng={lng} />
      </MapContainer>
    </div>
  );
}
