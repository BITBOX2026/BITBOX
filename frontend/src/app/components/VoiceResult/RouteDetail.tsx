import { AlertTriangle, BusFront, Clock3, FileText, Footprints, LoaderCircle, Map as MapIcon, MapPin } from "lucide-react";
import { CustomOverlayMap, Map, MapMarker, Polyline, useKakaoLoader } from "react-kakao-maps-sdk";
import type { RouteDetail, RouteSegment } from "../../../types/bus";

interface RouteDetailOverlayProps {
  route: RouteDetail;
  destination: string;
  viewMode: "text" | "map";
  onToggleView: () => void;
}

const ROUTE_COLORS = ["#0072B2", "#009E73", "#D55E00", "#CC79A7"];

interface MapLine {
  path: Array<{ lat: number; lng: number }>;
  color: string;
  busNumber?: string;
  isWalk?: boolean;
}

function hasCoordinates(segment: RouteSegment): boolean {
  return [segment.start_x, segment.start_y, segment.end_x, segment.end_y].every(
    (value) => value !== null && value !== undefined && Number.isFinite(Number(value)),
  );
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}분`;
  const remainder = minutes % 60;
  return `${Math.floor(minutes / 60)}시간${remainder ? ` ${remainder}분` : ""}`;
}

export function RouteDetailOverlay({ route, destination, viewMode, onToggleView }: RouteDetailOverlayProps) {
  const [mapLoading, mapError] = useKakaoLoader({
    appkey: import.meta.env.VITE_KAKAO_MAP_APPKEY || "",
    libraries: ["services", "clusterer"],
  });
  const segments = route.route_segments ?? [];
  const mapLines: MapLine[] = [];
  const mapMarkers: Array<{ lat: number; lng: number; name: string }> = [];

  segments.forEach((segment, index) => {
    if (!hasCoordinates(segment)) return;
    const start = { lat: Number(segment.start_y), lng: Number(segment.start_x) };
    const end = { lat: Number(segment.end_y), lng: Number(segment.end_x) };
    const stationPath = (segment.path_points ?? [])
      .filter((point) => Number.isFinite(Number(point.x)) && Number.isFinite(Number(point.y)))
      .map((point) => ({ lat: Number(point.y), lng: Number(point.x) }));
    const isWalk = segment.vehicle_type === "도보";
    mapLines.push({
      path: stationPath.length >= 2 ? stationPath : [start, end],
      color: isWalk ? "#64748B" : ROUTE_COLORS[index % ROUTE_COLORS.length],
      busNumber: isWalk ? undefined : segment.line || route.busNumber,
      isWalk,
    });
    mapMarkers.push({ ...start, name: segment.start_name || "탑승 정류장" });
    if (index === segments.length - 1) mapMarkers.push({ ...end, name: segment.end_name || destination });

    const next = segments[index + 1];
    if (next && next.start_x != null && next.start_y != null) {
      mapLines.push({ path: [end, { lat: Number(next.start_y), lng: Number(next.start_x) }], color: "#94A3B8" });
    }
  });

  if (route.origin_x != null && route.origin_y != null) {
    const originLat = Number(route.origin_y);
    const originLng = Number(route.origin_x);
    if (Number.isFinite(originLat) && Number.isFinite(originLng)) mapMarkers.unshift({ lat: originLat, lng: originLng, name: route.origin || "출발지" });
  }
  if (route.destination_x != null && route.destination_y != null) {
    const destinationLat = Number(route.destination_y);
    const destinationLng = Number(route.destination_x);
    if (Number.isFinite(destinationLat) && Number.isFinite(destinationLng)) mapMarkers.push({ lat: destinationLat, lng: destinationLng, name: destination || "목적지" });
  }

  return (
    <div className="absolute inset-0 flex h-full w-full flex-col overflow-hidden bg-white text-[#171D23]">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2 sm:px-5">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-[#123E49] px-3 py-2 font-mono text-lg font-black text-white sm:text-xl">{route.busNumber}번</span>
          <span className="hidden items-center gap-1 text-sm font-bold text-slate-600 sm:flex"><Clock3 className="size-4" /> {formatDuration(route.totalMin)}</span>
        </div>
        <div className="flex rounded-md border border-slate-200 bg-slate-100 p-1" aria-label="경로 보기 방식">
          <button type="button" onClick={() => viewMode === "map" && onToggleView()} aria-pressed={viewMode === "text"} className={`route-tab ${viewMode === "text" ? "route-tab-active" : ""}`} title="경로 안내"><FileText className="size-4" /><span className="hidden sm:inline">안내</span></button>
          <button type="button" onClick={() => viewMode === "text" && onToggleView()} aria-pressed={viewMode === "map"} className={`route-tab ${viewMode === "map" ? "route-tab-active" : ""}`} title="지도"><MapIcon className="size-4" /><span className="hidden sm:inline">지도</span></button>
        </div>
      </header>

      <div className="custom-scrollbar-light min-h-0 flex-1 overflow-y-auto bg-[#F5F7F8] p-3 sm:p-5">
        {viewMode === "map" ? (
          mapMarkers.length > 0 ? (
            <div className="fade-enter relative h-full min-h-[260px] overflow-hidden rounded-md border border-slate-300 bg-white">
              <span className="absolute left-2 top-2 z-10 rounded bg-white/95 px-2 py-1 text-[11px] font-bold text-slate-600 shadow">정류장 기준 예상 경로</span>
              {mapError ? (
                <div className="flex h-full min-h-[260px] flex-col overflow-y-auto bg-slate-50 px-4 pb-4 pt-11">
                  <p className="mb-4 flex items-center gap-2 rounded bg-amber-100 px-3 py-2 text-xs font-bold text-amber-900"><AlertTriangle className="size-4 shrink-0" />지도 연결이 지연되어 정류장 순서로 표시합니다.</p>
                  <div className="mx-auto w-full max-w-[440px]">
                    {route.steps.map((step, index) => (
                      <div key={`${step.type}-${index}`} className="grid grid-cols-[32px_minmax(0,1fr)] gap-3">
                        <div className="flex flex-col items-center">
                          <span className={`grid size-8 place-items-center rounded-full text-white ${step.type === "walk" ? "bg-slate-500" : "bg-[#145466]"}`}>{step.type === "walk" ? <Footprints className="size-4" /> : <BusFront className="size-4" />}</span>
                          {index < route.steps.length - 1 && <span className="min-h-8 w-1 flex-1 bg-slate-300" />}
                        </div>
                        <div className="pb-4 text-sm">
                          <strong>{step.type === "walk" ? step.description || "도보 이동" : `${step.busNumber || route.busNumber}번 버스`}</strong>
                          <p className="mt-1 text-xs text-slate-600">{step.fromStop || "출발"} → {step.toStop || "도착"} · {formatDuration(step.durationMin)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : mapLoading ? (
                <div className="grid h-full min-h-[260px] place-items-center text-sm font-bold text-slate-500"><span className="flex items-center gap-2"><LoaderCircle className="size-5 animate-spin" />지도를 불러오는 중입니다.</span></div>
              ) : (
                <Map center={mapMarkers[0]} style={{ width: "100%", height: "100%", minHeight: "260px" }} level={5}>
                  {mapMarkers.map((marker, index) => <MapMarker key={`${marker.name}-${index}`} position={marker} title={marker.name} />)}
                  {mapLines.map((line, index) => <Polyline key={index} path={line.path} strokeWeight={line.isWalk ? 4 : 6} strokeColor={line.color} strokeOpacity={0.85} strokeStyle={line.isWalk ? "shortdash" : "solid"} />)}
                  {mapLines.map((line, index) => {
                    if (!line.busNumber) return null;
                    const [start, end] = line.path;
                    return (
                      <CustomOverlayMap key={`label-${index}`} position={{ lat: (start.lat + end.lat) / 2, lng: (start.lng + end.lng) / 2 }} yAnchor={1.2}>
                        <span className="rounded-md border-2 border-white px-2 py-1 text-xs font-black text-white shadow-lg" style={{ backgroundColor: line.color }}>{line.busNumber}</span>
                      </CustomOverlayMap>
                    );
                  })}
                </Map>
              )}
            </div>
          ) : (
            <div className="grid h-full min-h-[260px] place-items-center rounded-md border border-dashed border-slate-300 bg-white px-4 text-center">
              <div><MapPin className="mx-auto mb-2 size-7 text-slate-400" /><p className="text-sm font-bold text-slate-500">지도 좌표를 불러올 수 없습니다.</p></div>
            </div>
          )
        ) : (
          <div className="fade-enter mx-auto max-w-[640px] space-y-3">
            {route.steps.map((step, index) => {
              const isWalk = step.type === "walk";
              const color = isWalk ? "#64748B" : ROUTE_COLORS[index % ROUTE_COLORS.length];
              return (
                <article key={`${step.type}-${index}`} className="flex gap-3 rounded-md border border-slate-200 bg-white p-3 shadow-sm sm:p-4">
                  <div className="grid size-10 shrink-0 place-items-center rounded-md text-white" style={{ backgroundColor: color }}>{isWalk ? <Footprints className="size-5" /> : <BusFront className="size-5" />}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <strong className="text-base">{isWalk ? step.description || "도보 이동" : `${step.busNumber || route.busNumber}번 탑승`}</strong>
                      <span className="shrink-0 font-mono text-sm font-black">{formatDuration(step.durationMin)}</span>
                    </div>
                    {step.fromStop && (
                      <p className="mt-2 text-sm font-medium leading-relaxed text-slate-600">
                        {step.fromStop} {isWalk ? "출발" : "승차"}<br />
                        {step.toStop} {isWalk ? "도착" : "하차"}
                      </p>
                    )}
                  </div>
                </article>
              );
            })}
            <div className="flex items-center gap-3 rounded-md border border-emerald-200 bg-emerald-50 p-4 text-emerald-800"><MapPin className="size-6 shrink-0" /><strong>{destination} 도착</strong></div>
          </div>
        )}
      </div>
    </div>
  );
}
