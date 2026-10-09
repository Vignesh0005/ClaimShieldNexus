"use client";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap, LayerGroup } from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GeoEvent } from "@/lib/types";
import { RISK_HEX } from "@/lib/utils";

export function GeoMap({ events, selectedId, onSelect }: { events: GeoEvent[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<LayerGroup | null>(null);
  const tiles = useRef<import("leaflet").TileLayer | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("leaflet").then((L) => {
      if (cancelled || !el.current || map.current) return;
      map.current = L.map(el.current, { center: [38.5, -96], zoom: 4, scrollWheelZoom: false, worldCopyJump: true });
      layer.current = L.layerGroup().addTo(map.current);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      layer.current = null;
      tiles.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    import("leaflet").then((L) => {
      if (cancelled || !map.current || !layer.current) return;
      if (!tiles.current) {
        // Dark mode is handled in CSS by inverting the tile pane (see globals.css).
        tiles.current = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          maxZoom: 12,
        }).addTo(map.current);
      }

      layer.current.clearLayers();
      for (const e of events) {
        const selected = e.id === selectedId;
        const color = RISK_HEX[e.level];
        const line = L.polyline(
          [
            [e.a.lat, e.a.lng],
            [e.b.lat, e.b.lng],
          ],
          { color, weight: selected ? 4 : 1.5, opacity: selected ? 1 : 0.55, dashArray: selected ? undefined : "5 6" },
        );
        line.on("click", () => onSelect(e.id));
        line.bindTooltip(`${e.subject}: ${e.a.city} to ${e.b.city}`);
        layer.current.addLayer(line);
        for (const p of [e.a, e.b]) {
          const m = L.circleMarker([p.lat, p.lng], { radius: selected ? 7 : 4, color: "#0F172A", weight: 1, fillColor: color, fillOpacity: 0.95 });
          m.on("click", () => onSelect(e.id));
          layer.current.addLayer(m);
        }
        if (selected) map.current.fitBounds(line.getBounds(), { padding: [60, 60], maxZoom: 6 });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [events, selectedId, onSelect]);

  return (
    <div
      ref={el}
      className="h-[26rem] w-full rounded-lg lg:h-[34rem]"
      role="application"
      aria-label={`Map of ${events.length} location conflicts. Each line joins two places where the same provider or member was billed too close together in time. The list beside the map contains the same information.`}
    />
  );
}
