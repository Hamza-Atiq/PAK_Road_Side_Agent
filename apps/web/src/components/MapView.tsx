import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix leaflet's default marker icon paths (Vite breaks the assumption).
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: () => string })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

interface Pin {
  id: string;
  lat: number;
  lng: number;
  color?: "blue" | "green" | "orange" | "red";
  label?: string;
}

interface Props {
  center: { lat: number; lng: number };
  pins?: Pin[];
  height?: string;
  zoom?: number;
}

const COLOR_HEX: Record<NonNullable<Pin["color"]>, string> = {
  blue: "#2473EB",
  green: "#16A34A",
  orange: "#FF6600",
  red: "#DC2626",
};

export function MapView({ center, pins = [], height = "320px", zoom = 14 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = L.map(ref.current).setView([center.lat, center.lng], zoom);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, [center.lat, center.lng, zoom]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    map.setView([center.lat, center.lng], map.getZoom() || zoom);
    layer.clearLayers();
    pins.forEach((p) => {
      const color = COLOR_HEX[p.color ?? "blue"];
      const m = L.circleMarker([p.lat, p.lng], {
        radius: 10,
        color,
        fillColor: color,
        fillOpacity: 0.85,
        weight: 3,
      }).addTo(layer);
      if (p.label) m.bindTooltip(p.label, { permanent: false });
    });
  }, [center.lat, center.lng, pins, zoom]);

  return <div ref={ref} style={{ height, width: "100%", borderRadius: "1rem" }} />;
}
