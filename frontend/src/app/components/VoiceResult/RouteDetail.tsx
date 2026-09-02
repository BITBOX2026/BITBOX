import { AlertTriangle, BusFront, Clock3, FileText, Footprints, LoaderCircle, Map as MapIcon, MapPin } from "lucide-react";
import { CustomOverlayMap, Map, MapMarker, Polyline, useKakaoLoader } from "react-kakao-maps-sdk";
import type { ReactNode } from "react";
import { busNumberFontSize } from "../../../utils/busNumberFit";
import type { RouteDetail, RouteSegment } from "../../../types/bus";

interface RouteDetailOverlayProps {
  route: RouteDetail;
  destination: string;
  viewMode: "text" | "map";
  onToggleView: () => void;
}

// 색맹 안전 팔레트(Okabe-Ito). 선 색은 그대로 두고 라벨 글자색만 대비로 고릅니다.
const ROUTE_COLORS = ["#0072B2", "#009E73", "#D55E00", "#CC79A7"];

/**
 * 배경색 위에서 WCAG AA(4.5:1)를 만족하는 글자색을 고릅니다.
 *
 * 팔레트를 어둡게 바꾸면 색맹 구분성이 떨어지므로, 배경은 유지하고
 * 흰색/검은색 중 대비가 큰 쪽을 선택합니다.
 */
export function readableTextColor(background: string): "#FFFFFF" | "#000000" {
  const hex = background.replace("#", "");
  if (hex.length !== 6) return "#000000";
  const channel = (offset: number): number => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
  const againstWhite = 1.05 / (luminance + 0.05);
  const againstBlack = (luminance + 0.05) / 0.05;
  return againstWhite >= againstBlack ? "#FFFFFF" : "#000000";
}

interface MapPoint {
  lat: number;
  lng: number;
}

interface MapLine {
  path: MapPoint[];
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

function LazyKakaoMap({ children }: {
  children: (loading: boolean, error: ErrorEvent | undefined) => ReactNode;
}) {
  // 텍스트 안내만 보는 이용자에게 지도 SDK를 미리 요청하지 않습니다. 지도 탭을
  // 실제로 열었을 때만 로드해 초기 결과 표시를 빠르게 하고 불필요한 외부 요청을 줄입니다.
  const [loading, error] = useKakaoLoader({
    appkey: import.meta.env.VITE_KAKAO_MAP_APPKEY || "",
  });
  return children(loading, error);
}

/**
 * 총 소요시간·환승 횟수·예상 요금 요약. 화면 폭에 따라 헤더 안이나 그 아래
 * 한 줄짜리 막대에 놓입니다. 값이 없는 항목은 지어내지 않고 아예 그리지 않습니다.
 */
function RouteSummaryChips({ route }: { route: RouteDetail }) {
  return (
    <>
      <span className="flex min-h-9 shrink-0 items-center gap-1 whitespace-nowrap rounded-md bg-slate-100 px-2 text-sm font-black text-slate-700"><Clock3 className="size-4 text-[#9A7400]" /> {formatDuration(route.totalMin)}</span>
      {route.transferCount != null && (
        <span className="flex min-h-9 shrink-0 items-center whitespace-nowrap rounded-md bg-sky-50 px-2 text-sm font-black text-sky-900">
          {route.transferCount === 0 ? "환승 없음" : `환승 ${route.transferCount}회`}
        </span>
      )}
      {route.payment != null && (
        <span className="flex min-h-9 shrink-0 items-center whitespace-nowrap rounded-md bg-emerald-50 px-2 text-sm font-black text-emerald-900">예상 {route.payment.toLocaleString("ko-KR")}원</span>
      )}
    </>
  );
}

/**
 * 노선 라벨을 붙일 구간의 중간 좌표를 고릅니다.
 *
 * 경유 정류장이 없는 구간은 좌표가 출발·도착 두 개뿐입니다. 이때 인덱스를
 * `length / 2` 로 고르면 1번(도착점)이 잡혀 라벨이 구간 끝에 붙습니다. 점 개수가
 * 짝수면 가운데 두 점의 평균을, 홀수면 가운데 점을 씁니다.
 */
export function pathMidpoint(path: MapPoint[]): MapPoint {
  const middle = Math.floor(path.length / 2);
  if (path.length % 2 === 1) return path[middle];
  const before = path[middle - 1];
  const after = path[middle];
  return { lat: (before.lat + after.lat) / 2, lng: (before.lng + after.lng) / 2 };
}

export function RouteDetailOverlay({ route, destination, viewMode, onToggleView }: RouteDetailOverlayProps) {
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
  const mapPoints = [...mapMarkers, ...mapLines.flatMap((line) => line.path)];

  const fitMapToRoute = (map: kakao.maps.Map) => {
    if (mapPoints.length < 2) return;
    const bounds = new kakao.maps.LatLngBounds();
    mapPoints.forEach((point) => bounds.extend(new kakao.maps.LatLng(point.lat, point.lng)));
    map.setBounds(bounds, 48, 48, 48, 48);
  };

  return (
    <div className="absolute inset-0 flex min-h-0 min-w-0 flex-col overflow-hidden bg-white text-[#171D23]">
      {/*
        헤더는 shrink-0 입니다. 여기에 요약 칩까지 넣으면 좁은 화면에서 줄바꿈으로
        헤더가 부모(overflow-hidden)보다 커지고, 아래 스크롤 영역이 통째로 잘린
        영역 밖으로 밀려나 경로 본문이 한 줄도 보이지 않습니다. 그래서 헤더에는
        높이가 고정된 "노선번호 + 보기 전환"만 두고, 요약은 아래 전용 한 줄로
        내립니다. 폭이 모자라면 줄을 바꾸는 대신 가로로 흐르게 해 높이를 묶습니다.
      */}
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-1.5 shadow-sm sm:px-5 sm:py-2.5">
        {/* 폭이 정해진 래퍼를 컨테이너로 두어야 노선번호가 칸에 맞춰 줄어듭니다.
            칩 자체를 컨테이너로 삼으면 내용으로 폭이 정해지지 않아 찌그러집니다. */}
        <div className="min-w-0 flex-1 [container-type:inline-size]">
          <span
            title={`${route.busNumber}번 버스`}
            className="inline-block max-w-full whitespace-nowrap rounded-lg bg-[#123E49] px-3 py-2 text-center font-mono font-black leading-tight text-white shadow-sm"
            style={{ fontSize: busNumberFontSize(`${route.busNumber}번`, 1.25) }}
          >
            {route.busNumber}번
          </span>
        </div>
        <div className="flex shrink-0 rounded-md border border-slate-200 bg-slate-100 p-1" aria-label="경로 보기 방식">
          <button type="button" onClick={() => viewMode === "map" && onToggleView()} aria-pressed={viewMode === "text"} className={`route-tab ${viewMode === "text" ? "route-tab-active" : ""}`} title="경로 안내"><FileText className="size-4" /><span className="hidden sm:inline">안내</span></button>
          <button type="button" onClick={() => viewMode === "text" && onToggleView()} aria-pressed={viewMode === "map"} className={`route-tab ${viewMode === "map" ? "route-tab-active" : ""}`} title="지도"><MapIcon className="size-4" /><span className="hidden sm:inline">지도</span></button>
        </div>
      </header>

      <div className="no-scrollbar flex shrink-0 items-center gap-2 overflow-x-auto border-b border-slate-200 bg-white px-3 py-1.5 sm:px-5 sm:py-2">
        <RouteSummaryChips route={route} />
      </div>

      <div
        tabIndex={0}
        role="region"
        aria-label="경로 상세 내용"
        className="custom-scrollbar-light min-h-0 flex-1 overflow-y-auto bg-[#F3F6F7] p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#123E49] sm:p-5"
      >
        {viewMode === "map" ? (
          <LazyKakaoMap>{(mapLoading, mapError) => mapMarkers.length > 0 ? (
            <div className="fade-enter relative h-full min-h-[300px] overflow-hidden rounded-xl border border-slate-300 bg-white shadow-[0_10px_28px_rgba(15,23,42,0.10)]">
              <span className="absolute left-3 top-3 z-10 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs font-black text-slate-700 shadow-lg backdrop-blur">정류장 기준 예상 경로</span>
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
                <Map center={mapMarkers[0]} onCreate={fitMapToRoute} style={{ width: "100%", height: "100%", minHeight: "300px" }} level={5}>
                  {mapMarkers.map((marker, index) => <MapMarker key={`${marker.name}-${index}`} position={marker} title={marker.name} />)}
                  {mapLines.map((line, index) => <Polyline key={index} path={line.path} strokeWeight={line.isWalk ? 4 : 6} strokeColor={line.color} strokeOpacity={0.85} strokeStyle={line.isWalk ? "shortdash" : "solid"} />)}
                  {mapLines.map((line, index) => {
                    if (!line.busNumber) return null;
                    const midpoint = pathMidpoint(line.path);
                    return (
                      <CustomOverlayMap key={`label-${index}`} position={midpoint} yAnchor={1.2}>
                        <span className="rounded-md border-2 border-white px-2 py-1 text-xs font-black shadow-lg" style={{ backgroundColor: line.color, color: readableTextColor(line.color) }}>{line.busNumber}</span>
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
          )}</LazyKakaoMap>
        ) : (
          <div className="fade-enter mx-auto max-w-[640px] space-y-3">
            {route.steps.map((step, index) => {
              const isWalk = step.type === "walk";
              const color = isWalk ? "#64748B" : ROUTE_COLORS[index % ROUTE_COLORS.length];
              return (
                <article key={`${step.type}-${index}`} className="flex gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-[0_5px_16px_rgba(15,23,42,0.06)] sm:p-4">
                  <div className="grid size-10 shrink-0 place-items-center rounded-lg text-white shadow-sm" style={{ backgroundColor: color }}>{isWalk ? <Footprints className="size-5" /> : <BusFront className="size-5" />}</div>
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
                    {!isWalk && step.alternativeBuses && step.alternativeBuses.length > 0 && (
                      <p className="mt-2 text-sm font-bold leading-relaxed text-[#145466]">
                        {step.alternativeBuses.slice(0, 3).map((bus) => `${bus}번`).join(", ")}
                        {step.alternativeBuses.length > 3 ? " 등" : ""} 버스를 타셔도 됩니다.
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
