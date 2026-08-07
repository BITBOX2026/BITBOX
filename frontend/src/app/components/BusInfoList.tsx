import { useState, useEffect, useCallback } from "react";
import { BusOption as BusInfo } from "../../types/bus";
import { getDefaultArrivals, getCongestionLabel, getCongestionColor } from "../../api/busService";
import { BusFront, MapPin, RefreshCw, Wifi } from "lucide-react";

const STATION_NAME = import.meta.env.VITE_STATION_NAME ?? "정류장";

const SOON_SEC    = 3 * 60; // 잠시 후 도착 기준: 180초 미만
const SOON_ARRIVE = 60;     // 곧 도착 기준: 60초 미만
const SOON_PER_PAGE = 5;
const MAIN_PER_PAGE = 5;
const REFRESH_MS    = 15_000;
const MAX_MIN       = 30;
const DAY_KR = ["일", "월", "화", "수", "목", "금", "토"];

// ─── 원형 프로그레스 ─────────────────────────────────────────
function CircleTimer({ arrivalMin }: { arrivalMin: number }) {
  const r = 30;
  const circumference = 2 * Math.PI * r;
  const ratio = Math.min(arrivalMin / MAX_MIN, 1);
  const dash  = ratio * circumference;
  const color = arrivalMin <= 5 ? "#F59E0B" : "#FACC15";

  return (
    <svg width="76" height="76" viewBox="0 0 76 76">
      <circle cx="38" cy="38" r={r} fill="none" stroke="#E2E8F0" strokeWidth="6" />
      <circle
        cx="38" cy="38" r={r}
        fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${dash} ${circumference}`}
        transform="rotate(-90 38 38)"
        style={{ transition: "stroke-dasharray 0.5s ease" }}
      />
      <text x="38" y="35" textAnchor="middle" dominantBaseline="middle"
        fontSize="22" fontWeight="900" fill="#1E293B" fontFamily="monospace">
        {arrivalMin}
      </text>
      <text x="38" y="54" textAnchor="middle"
        fontSize="12" fontWeight="700" fill="#64748B">
        분
      </text>
    </svg>
  );
}

// ─── 정거장 도트 시각화 ──────────────────────────────────────
function StopsDot({ remaining }: { remaining: number }) {
  if (remaining < 0) return null;
  if (remaining === 0) return (
    <span className="text-[12px] font-black text-red-500 bg-red-50 border border-red-200 rounded px-2 py-0.5 mt-1 inline-block">
      정류소 곧 도착
    </span>
  );

  const MAX_DOTS = 6;
  const showStops = Math.min(remaining, MAX_DOTS);
  const dots = Array.from({ length: showStops }, (_, i) => showStops - i);

  return (
    <div className="flex items-center gap-0 mt-1.5">
      <BusFront className="mr-1 size-4 shrink-0 text-[#2563EB]" aria-hidden="true" />
      <div className="h-[2px] w-2 bg-[#CBD5E1]" />
      {dots.map((n, i) => (
        <div key={n} className="flex items-center">
          <div className={`w-[18px] h-[18px] rounded-full border-2 flex items-center justify-center
            ${i === 0 ? "bg-[#3B82F6] border-[#2563EB]" : "bg-white border-[#CBD5E1]"}`}>
            <span className={`text-[9px] font-black leading-none ${i === 0 ? "text-white" : "text-[#64748B]"}`}>
              {n}
            </span>
          </div>
          {i < dots.length - 1 && <div className="h-[2px] w-2 bg-[#CBD5E1]" />}
        </div>
      ))}
      <div className="h-[2px] w-2 bg-[#CBD5E1]" />
      <div className="w-[18px] h-[18px] rounded-full bg-red-500 border-2 border-red-400 flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-white" />
      </div>
    </div>
  );
}

// ─── 잠시 후 도착 카드 (시간 없음, 번호+혼잡도만) ────────────
function SoonCard({ bus }: { bus: BusInfo }) {
  const congLabel = getCongestionLabel(bus.congetion);
  const congColor = getCongestionColor(bus.congetion);
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-2 rounded-md border border-[#303842] bg-[#1C2229] px-2 py-3 shadow-md">
      <div className={`rounded-full px-3 py-0.5 text-[12px] font-black border ${congColor}`}>
        {congLabel}
      </div>
      <div className="max-w-full truncate text-[28px] font-black text-[#FACC15] font-mono leading-none sm:text-[36px] md:text-[44px]">
        {bus.busNumber}
      </div>
      {bus.isLastBus && (
        <span className="bg-red-600 text-white text-[11px] font-black px-2 py-0.5 rounded-full">막차</span>
      )}
    </div>
  );
}

// ─── 로딩 스켈레톤 ───────────────────────────────────────────
function SkeletonRow({ idx }: { idx: number }) {
  return (
    <div className={`grid min-h-0 flex-1 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] items-center border-b border-[#E2E8F0] md:grid-cols-[150px_110px_1fr] ${idx % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`}>
      <div className="flex justify-center px-4 border-r border-[#E2E8F0] h-full items-center">
        <div className="h-9 w-20 bg-gray-200 rounded animate-pulse" />
      </div>
      <div className="flex justify-center px-2 border-r border-[#E2E8F0] h-full items-center">
        <div className="h-16 w-16 bg-gray-200 rounded-full animate-pulse" />
      </div>
      <div className="flex flex-col px-4 h-full justify-center gap-2">
        <div className="h-5 w-40 bg-gray-200 rounded animate-pulse" />
        <div className="h-4 w-28 bg-gray-200 rounded animate-pulse" />
      </div>
    </div>
  );
}

// ─── 실시간 시계 훅 ──────────────────────────────────────────
function useLiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

// ─── 실시간 도착 정보 훅 ─────────────────────────────────────
function useBusArrivals() {
  const [buses, setBuses]             = useState<BusInfo[]>([]);
  const [liveStationName, setLiveStationName] = useState<string>("");
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const { stationName, buses: data } = await getDefaultArrivals();
      setBuses(data);
      setLiveStationName(stationName); // 가져온 실시간 서버 정류소 이름을 저장
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "도착 정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    const id = setInterval(fetchData, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  return { buses, liveStationName, loading, error, lastUpdated, refetch: fetchData };
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────
export function BusInfoList() {
  const [mainPage, setMainPage] = useState(0);
  const [soonPage, setSoonPage] = useState(0);
  const now = useLiveClock();
  const { buses, liveStationName, loading, error, lastUpdated, refetch } = useBusArrivals();

  const arrivingSoon   = buses.filter((b) => b.traTimeSec < SOON_SEC);
  const soonTotalPages = Math.max(1, Math.ceil(arrivingSoon.length / SOON_PER_PAGE));
  const mainTotalPages = Math.max(1, Math.ceil(buses.length / MAIN_PER_PAGE));

  useEffect(() => {
    if (soonTotalPages <= 1) return;
    const id = setInterval(() => setSoonPage((p) => (p + 1) % soonTotalPages), 5000);
    return () => clearInterval(id);
  }, [soonTotalPages]);

  useEffect(() => {
    if (mainTotalPages <= 1) return;
    const id = setInterval(() => setMainPage((p) => (p + 1) % mainTotalPages), 5000);
    return () => clearInterval(id);
  }, [mainTotalPages]);

  const curSoonPage = Math.min(soonPage, soonTotalPages - 1);
  const curMainPage = Math.min(mainPage, mainTotalPages - 1);
  const currentSoon = arrivingSoon.slice(curSoonPage * SOON_PER_PAGE, (curSoonPage + 1) * SOON_PER_PAGE);
  const currentMain = buses.slice(curMainPage * MAIN_PER_PAGE, (curMainPage + 1) * MAIN_PER_PAGE);

  const yy = now.getFullYear(), mm = now.getMonth() + 1, dd = now.getDate();
  const day    = DAY_KR[now.getDay()];
  const hh24   = now.getHours();
  const ampm   = hh24 >= 12 ? "오후" : "오전";
  const displayH = hh24 > 12 ? hh24 - 12 : hh24 === 0 ? 12 : hh24;
  const displayM = String(now.getMinutes()).padStart(2, "0");
  const displayS = String(now.getSeconds()).padStart(2, "0");
  const lastUpdatedStr = lastUpdated
    ? `${String(lastUpdated.getHours()).padStart(2,"0")}:${String(lastUpdated.getMinutes()).padStart(2,"0")}:${String(lastUpdated.getSeconds()).padStart(2,"0")} 갱신`
    : "";

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-[#EDF1F3] font-['Noto_Sans_KR']">

      {/* ── 헤더 ─────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between border-b-4 border-[#F0C929] bg-[#171D23] px-3 py-2 sm:px-6 sm:py-3">
        <div className="flex min-w-0 items-center gap-3 text-left">
          <div className="grid size-10 shrink-0 place-items-center rounded-md bg-[#F0C929] text-[#171D23] sm:size-12">
            <MapPin className="size-5 sm:size-6" />
          </div>
          <div className="min-w-0">
            <span className="mb-0.5 block text-[11px] font-bold text-white/50 sm:text-[13px]">서울특별시 · 실시간 버스정보</span>
            <span className="block max-w-[44vw] truncate text-[21px] font-black leading-tight text-white sm:text-[28px] md:text-[32px]">{liveStationName || STATION_NAME}</span>
          </div>
        </div>
        <div className="text-right text-white">
          <div className="mb-1 text-[11px] text-white/45 sm:text-[13px]">{yy}년 {mm}월 {dd}일 ({day})</div>
          <div className="flex items-baseline gap-1 font-mono text-[26px] font-black leading-none text-white sm:text-[36px] md:gap-2 md:text-[44px]">
            <span className="text-[14px] text-yellow-400 sm:text-[20px] md:text-[24px]">{ampm}</span>
            {displayH}:{displayM}:{displayS}
          </div>
        </div>
      </div>

      {/* ── 오류 배너 ────────────────────────────── */}
      {error && (
        <div className="bg-red-600 text-white text-[13px] font-bold px-5 py-2 flex items-center justify-between shrink-0">
          <span>{error}</span>
          <button onClick={refetch} className="ml-4 inline-flex items-center gap-1 text-white/90 hover:text-white"><RefreshCw className="size-3.5" />다시 시도</button>
        </div>
      )}

      {/* ── 잠시 후 도착 (3분 미만, 시간 없음) ───── */}
      <div className="shrink-0 border-b border-[#C99F11] bg-[#F0C929] px-3 pb-3 pt-2 sm:px-5 sm:pb-4 sm:pt-3">
        <div className="flex justify-between items-end mb-3">
          <div className="flex flex-col text-left">
            <span className="text-[20px] font-black leading-tight text-[#2C2A1A] sm:text-[24px]">잠시 후 도착</span>
            <span className="text-[12px] font-bold text-[#645716] sm:text-[13px]">3분 이내 도착 차량</span>
          </div>
          {lastUpdatedStr && <span className="text-[12px] text-[#92400E]">{lastUpdatedStr}</span>}
        </div>

        {loading ? (
          <div className="flex gap-1 sm:gap-2">
            {Array.from({ length: SOON_PER_PAGE }).map((_, i) => (
              <div key={i} className="min-h-[92px] flex-1 animate-pulse rounded-md border border-[#6F611E]/30 bg-[#1C2229]/35" />
            ))}
          </div>
        ) : arrivingSoon.length === 0 ? (
          <div className="rounded-md bg-black/8 py-5 text-center text-[16px] font-bold text-[#504710]">
            3분 이내 도착 예정 버스가 없습니다
          </div>
        ) : (
          <div className="flex items-stretch gap-1 sm:gap-2">
            {currentSoon.map((bus) => <SoonCard key={bus.id} bus={bus} />)}
            {Array.from({ length: SOON_PER_PAGE - currentSoon.length }).map((_, i) => (
              <div key={`es-${i}`} className="min-h-[92px] flex-1 rounded-md border border-[#6F611E]/20 bg-[#1C2229]/12" />
            ))}
          </div>
        )}
      </div>

      {/* ── 메인 버스 목록 ───────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0 bg-white">
        {/* 테이블 헤더 */}
        <div className="grid shrink-0 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] border-b border-[#374151] bg-[#1C1F26] md:grid-cols-[150px_110px_1fr]">
          {["노선번호", "예정시간", "버스 현재 위치"].map((label, i) => (
            <div key={i} className={`py-3 px-4 text-[14px] font-black text-white tracking-wider ${i === 2 ? "text-left" : "text-center"} ${i < 2 ? "border-r border-[#374151]" : ""}`}>
              {label}
            </div>
          ))}
        </div>

        {/* 목록 본문 */}
        <div className="flex-1 flex flex-col min-h-0 bg-[#F1F5F9]">
          <div className="flex flex-col h-full">
            {loading
              ? Array.from({ length: MAIN_PER_PAGE }).map((_, i) => <SkeletonRow key={i} idx={i} />)
              : currentMain.map((bus, idx) => {
                  const congLabel = getCongestionLabel(bus.congetion);
                  const congColor = getCongestionColor(bus.congetion);
                  const isArriving = bus.traTimeSec < SOON_ARRIVE;

                  return (
                    <div key={bus.id} className={`grid min-h-0 flex-1 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] items-center border-b border-[#E2E8F0] md:grid-cols-[150px_110px_1fr]
                      ${idx % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`}>

                      {/* 노선번호 */}
                      <div className="flex items-center justify-center px-4 border-r border-[#E2E8F0] h-full">
                        <span className="max-w-full truncate text-[22px] font-black leading-none text-[#1E293B] sm:text-[27px] md:text-[32px]">
                          {bus.busNumber}
                        </span>
                      </div>

                      {/* 예정시간 */}
                      <div className="flex items-center justify-center border-r border-[#E2E8F0] h-full py-2">
                        {isArriving ? (
                          <div className="flex flex-col items-center">
                            <span className="text-[20px] font-black text-red-500 leading-tight">곧</span>
                            <span className="text-[20px] font-black text-red-500 leading-tight">도착</span>
                          </div>
                        ) : (
                          <CircleTimer arrivalMin={bus.arrivalMin} />
                        )}
                      </div>

                      {/* 버스 현재 위치 */}
                      <div className="flex items-center px-4 h-full gap-3">
                        <div className={`border rounded-lg px-2 py-1 shrink-0 ${congColor}`}>
                          <span className="text-[12px] font-black">{congLabel}</span>
                        </div>
                        <div className="flex flex-col min-w-0">
                          <span className="truncate text-[14px] font-black leading-tight text-[#1E293B] sm:text-[17px] md:text-[20px]">
                            {bus.currentStationName}
                          </span>
                          <StopsDot remaining={bus.remainingStops} />
                          {bus.isLastBus && (
                            <span className="text-[12px] text-red-500 font-black mt-0.5">막차</span>
                          )}
                        </div>
                      </div>

                    </div>
                  );
                })}

            {!loading && Array.from({ length: Math.max(0, MAIN_PER_PAGE - currentMain.length) }).map((_, i) => (
              <div key={`em-${i}`} className={`grid min-h-0 flex-1 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] border-b border-[#E2E8F0] md:grid-cols-[150px_110px_1fr] ${(currentMain.length + i) % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`} />
            ))}
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex shrink-0 items-center justify-between border-t border-[#CBD5E1] bg-[#EDF1F3] px-3 py-2 sm:px-5">
          <button type="button" onClick={refetch} className="inline-flex items-center gap-1.5 text-[12px] font-bold text-[#52616B] hover:text-[#1B2930]" title="도착 정보 새로고침">
            <Wifi className="size-3.5 text-emerald-600" /> 실시간 · 15초마다 갱신
          </button>
          <div className="flex gap-1.5 items-center">
            {Array.from({ length: mainTotalPages }).map((_, i) => (
              <div key={i} className={`h-2 rounded-full transition-all duration-300 ${i === curMainPage ? "w-6 bg-[#475569]" : "w-2 bg-[#CBD5E1]"}`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
