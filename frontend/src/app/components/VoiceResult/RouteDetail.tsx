import { RouteDetail } from "../../../types/bus";
import { Map, MapMarker, Polyline, CustomOverlayMap } from "react-kakao-maps-sdk";
import { Map as MapIcon, FileText } from "lucide-react";

// 경로 위경도 좌표 배열
interface RouteDetailOverlayProps {
  route: RouteDetail & {
    origin_x?: number | string;
    origin_y?: number | string;
    destination_x?: number | string;
    destination_y?: number | string;
    origin?: string;
    route_segments?: any[];
  };
  destination: string;
  viewMode: 'text' | 'map';
  onToggleView: () => void;
  onClose: () => void;
}

// 색약자를 위한 오카베-이토 8색 팔레트 (CUD) 적용
const TRANSIT_THEMES = [
  // 파랑 Blue
  { bg: "bg-[#0072B2]", border: "border-[#0072B2]", text: "text-[#0072B2]", hex: "#0072B2" },
  
  // 주황 Orange
  { bg: "bg-[#E69F00]", border: "border-[#E69F00]", text: "text-[#E69F00]", hex: "#E69F00" },
  
  // 청록 Bluish Green
  { bg: "bg-[#009E73]", border: "border-[#009E73]", text: "text-[#009E73]", hex: "#009E73" },
  
  // 주홍 Vermilion
  { bg: "bg-[#D55E00]", border: "border-[#D55E00]", text: "text-[#D55E00]", hex: "#D55E00" },
  
  // 분홍보라 Reddish Purple
  { bg: "bg-[#CC79A7]", border: "border-[#CC79A7]", text: "text-[#CC79A7]", hex: "#CC79A7" },
  
  // 하늘색 Sky Blue (주의: 배경은 하늘색이지만, 흰색 바탕에서 글씨가 안 보일 수 있어 텍스트는 짙은 파랑으로 묶어줌)
  { bg: "bg-[#56B4E9]", border: "border-[#56B4E9]", text: "text-[#0072B2]", hex: "#56B4E9" },

  // 노랑 Yellow (주의: 표에 "얇은 선에는 사용 금지"라고 명시되어 있어 후순위로 뺌. 텍스트는 검정색으로 묶어줌)
  { bg: "bg-[#F0E442]", border: "border-[#F0E442]", text: "text-[#000000]", hex: "#F0E442" },
  
  // 검정 Black
  { bg: "bg-[#000000]", border: "border-[#000000]", text: "text-[#000000]", hex: "#000000" },
];

export function RouteDetailOverlay({ route, destination, viewMode, onToggleView }: RouteDetailOverlayProps) {
  let transitColorIndex = 0;

  const mapLines: { path: { lat: number; lng: number }[]; color: string; busNumber?: string }[] = [];
  const mapMarkers: { lat: number; lng: number; name: string }[] = [];

  // [중간 좌표 계산기]: 버스 번호 텍스트를 띄우기 위한 픽셀 연산용 함수
  const getMidpoint = (path: { lat: number; lng: number }[]) => {
    if (path.length < 2) return path[0];
    return { lat: (path[0].lat + path[1].lat) / 2, lng: (path[0].lng + path[1].lng) / 2 };
  };

  // 1. 첫 번째 도보 구간
  if (route.origin_y && route.origin_x && route.route_segments?.[0]?.start_y) {
    mapLines.push({
      path: [
        { lat: Number(route.origin_y), lng: Number(route.origin_x) },
        { lat: Number(route.route_segments[0].start_y), lng: Number(route.route_segments[0].start_x) }
      ],
      color: "#9CA3AF"
    });
    mapMarkers.push({ lat: Number(route.origin_y), lng: Number(route.origin_x), name: route.origin || "출발 정류장" });
  }

  // 2. 환승 구간별 정류장 좌표 추적 및 실시간 테마 컬러 매핑
  if (route.route_segments && route.route_segments.length > 0) {
    route.route_segments.forEach((seg: any, idx: number) => {
      if (seg.start_y && seg.start_x && seg.end_y && seg.end_x) {
        // 기존 텍스트 모드와 일치하는 색상 인덱스 추출
        const currentTheme = TRANSIT_THEMES[idx % TRANSIT_THEMES.length];

        // 버스 탑승 구역 노선 선 데이터 추가
        mapLines.push({
          path: [
            { lat: Number(seg.start_y), lng: Number(seg.start_x) },
            { lat: Number(seg.end_y), lng: Number(seg.end_x) }
          ],
          color: currentTheme.hex,
          busNumber: seg.line || route.busNumber
        });

        // 탑승 및 하차 정류장 마커 추가
        mapMarkers.push({ lat: Number(seg.start_y), lng: Number(seg.start_x), name: seg.start_name || "탑승 정류장" });
        mapMarkers.push({ lat: Number(seg.end_y), lng: Number(seg.end_x), name: seg.end_name || "하차 정류장" });

        // 환승 도보 구간 연결 연산
        const nextSeg = route.route_segments?.[idx + 1];
        if (nextSeg && nextSeg.start_y) {
          mapLines.push({
            path: [
              { lat: Number(seg.end_y), lng: Number(seg.end_x) },
              { lat: Number(nextSeg.start_y), lng: Number(nextSeg.start_x) }
            ],
            color: "#9CA3AF"
          });
        }
      }
    });
  }

  // 3. 마지막 도보 구간
  const lastSegment = route.route_segments?.[route.route_segments.length - 1];
  if (lastSegment && lastSegment.end_y && route.destination_y) {
    mapLines.push({
      path: [
        { lat: Number(lastSegment.end_y), lng: Number(lastSegment.end_x) },
        { lat: Number(route.destination_y), lng: Number(route.destination_x) }
      ],
      color: "#9CA3AF"
    });
    mapMarkers.push({ lat: Number(route.destination_y), lng: Number(route.destination_x), name: destination || "목적지" });
  }

  return (
    <div className="absolute inset-0 z-[100] bg-white text-gray-900 overflow-hidden font-['Noto_Sans_KR'] flex flex-col w-full h-full">
      {/* ── [우측 뷰어 전용 헤더 영역 (줄바꿈 및 가시성 개선)] ── */}
      <div className="flex items-center justify-between w-full py-3 px-6 bg-white shrink-0 border-b border-gray-100 shadow-sm">
        
        {/* 버스 번호 배지 */}
        <div className="flex items-center gap-3 shrink-0">
          <span className="bg-blue-600 text-white px-4 py-2 rounded-xl font-mono text-2xl font-black whitespace-nowrap shrink-0 shadow-sm flex items-center justify-center">
            {route.busNumber}번
          </span>
        </div>

        {/* 우측 컨트롤 그룹 (토글 + 소요 시간) */}
        <div className="flex items-center gap-3 shrink-0">
          
          {/* 뷰 모드 탭 (Segmented Control) */}
          <div className="flex bg-gray-100/80 p-1 rounded-xl border border-gray-200/80 shrink-0">
            <button 
              type="button"
              onClick={() => viewMode !== 'text' && onToggleView()}
              className={`flex flex-row items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap shrink-0 ${
                viewMode === 'text' 
                  ? 'bg-white text-blue-600 shadow-sm border border-gray-200/60' 
                  : 'text-gray-400 hover:text-gray-600'
              }`}
            >
              <FileText className="w-4 h-4 shrink-0" />
              <span className="whitespace-nowrap">텍스트로 보기</span>
            </button>

            <button 
              type="button"
              onClick={() => viewMode !== 'map' && onToggleView()}
              className={`flex flex-row items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap shrink-0 ${
                viewMode === 'map' 
                  ? 'bg-white text-blue-600 shadow-sm border border-gray-200/60' 
                  : 'text-gray-400 hover:text-gray-600'
              }`}
            >
              <MapIcon className="w-4 h-4 shrink-0" />
              <span className="whitespace-nowrap">지도로 보기</span>
            </button>
          </div>

          {/* 소요 시간 박스 */}
          <div className="bg-amber-50 border border-amber-200/80 px-4 py-2 rounded-xl flex items-center gap-2 shadow-sm whitespace-nowrap shrink-0">
            <span className="text-amber-800 text-xs font-extrabold whitespace-nowrap shrink-0">총</span>
            {route.totalMin >= 60 ? (
              <div className="flex items-baseline gap-0.5 whitespace-nowrap shrink-0">
                <span className="text-2xl font-black text-gray-900 font-mono leading-none">{Math.floor(route.totalMin / 60)}</span>
                <span className="text-amber-800 font-bold text-xs mr-1">시간</span>
                {route.totalMin % 60 > 0 && (
                  <>
                    <span className="text-2xl font-black text-gray-900 font-mono leading-none">{route.totalMin % 60}</span>
                    <span className="text-amber-800 font-bold text-xs">분</span>
                  </>
                )}
              </div>
            ) : (
              <div className="flex items-baseline gap-0.5 whitespace-nowrap shrink-0">
                <span className="text-2xl font-black text-gray-900 font-mono leading-none">{route.totalMin}</span>
                <span className="text-amber-800 font-bold text-xs">분</span>
              </div>
            )}
          </div>

        </div>
      </div>

      {/* ── 하단 가변 콘텐츠 구역 ── */}
      <div className="flex-1 overflow-y-auto px-8 pt-5 pb-6 custom-scrollbar-light bg-white flex flex-col">
        {viewMode === 'map' ? (
          // [지도 모드]
          mapMarkers && mapMarkers.length > 0 && mapMarkers[0]?.lat ? (
            <div className="w-full h-[520px] rounded-2xl overflow-hidden border border-gray-200 relative shadow-sm animate-in fade-in duration-300">
              <Map center={{ lat: mapMarkers[0].lat, lng: mapMarkers[0].lng }} style={{ width: "100%", height: "520px" }} level={5}>
                {mapMarkers.map((pos, index) => 
                  pos?.lat && pos?.lng ? <MapMarker key={`marker-${index}`} position={{ lat: pos.lat, lng: pos.lng }}/> : null
                )}

                {mapLines.map((line, index) => (
                  <Polyline key={`line-${index}`} path={line.path} strokeWeight={6} strokeColor={line.color} strokeOpacity={0.85} />
                ))}

                {mapLines.map((line, index) => {
                  if (!line.busNumber) return null;
                  const midpoint = getMidpoint(line.path);
                  return (
                    <CustomOverlayMap key={`overlay-${index}`} position={midpoint} yAnchor={1.5}>
                      <div className="text-white font-black px-3 py-1 rounded-xl text-sm shadow-xl border-2 border-white whitespace-nowrap flex items-center gap-1 animate-bounce" style={{ backgroundColor: line.color }}>
                        <span>🚌</span><span>{line.busNumber}</span>
                      </div>
                    </CustomOverlayMap>
                  );
                })}
              </Map>
            </div>
          ) : (
            <div className="flex-1 w-full h-full rounded-2xl border-2 border-dashed border-gray-200 flex flex-col items-center justify-center p-6 bg-gray-50/50 min-h-[350px]">
              <div className="text-4xl mb-2">📍</div>
              <p className="text-gray-500 font-black text-lg">실시간 지도 경로 데이터를 불러올 수 없습니다.</p>
            </div>
          )
        ) : (
          // [텍스트 모드]
          <div className="w-full h-full animate-in fade-in duration-300">
            {route.steps.map((step: any, idx: number) => {
              const isWalk = step.type === "walk";
              const isLast = idx === route.steps.length - 1;

              let currentTheme = TRANSIT_THEMES[0];
              if (!isWalk) {
                currentTheme = TRANSIT_THEMES[transitColorIndex % TRANSIT_THEMES.length];
                transitColorIndex++;
              }
              
              return (
                <div key={idx} className="flex gap-6 mb-8 relative text-black">
                  {!isLast && <div className="absolute left-[27px] top-[60px] w-0.5 h-full bg-gray-200" />}
                  <div className={`w-14 h-14 rounded-full shrink-0 flex items-center justify-center z-10 border-2 shadow-sm ${isWalk ? "bg-gray-100 border-gray-300" : `${currentTheme.bg} ${currentTheme.border}`}`}>
                    <span className="text-3xl">{isWalk ? "🚶" : "🚌"}</span>
                  </div>
                  <div className="flex-1 bg-gray-50 rounded-2xl p-5 border border-gray-200 shadow-sm">
                    <div className="flex justify-between items-center mb-2">
                      <span className={`text-lg font-bold ${isWalk ? "text-black" : currentTheme.text}`}>{isWalk ? step.description : `${step.busNumber} 탑승`}</span>
                      <span className="text-black font-black font-mono text-xl">
                        {step.durationMin >= 60 ? `${Math.floor(step.durationMin / 60)}시간 ${step.durationMin % 60 > 0 ? `${step.durationMin % 60}분` : ''}` : `${step.durationMin}분`}
                      </span>
                    </div>
                    {step.fromStop && (
                      <div className="mt-3 bg-white border border-gray-100 rounded-xl p-3 space-y-1.5 shadow-inner text-base text-black font-medium">
                        <div className="flex items-center gap-2"><span className={`w-2 h-2 rounded-full ${isWalk ? 'bg-gray-400' : currentTheme.bg}`} /> {step.fromStop} 승차</div>
                        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-500" /> {step.toStop} 하차</div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {/* 최종 도착지 표시 */}
            <div className="flex gap-6 items-center pb-4">
              <div className="w-14 h-14 rounded-full bg-green-50 border-2 border-green-500 flex items-center justify-center text-2xl shadow-sm">🎯</div>
              <div className="flex-1 bg-green-50 border border-green-200 rounded-2xl p-4">
                <p className="text-xl font-black text-green-700">{destination} 도착</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}