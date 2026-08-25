import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { BusOption as BusInfo } from "../../types/bus";
import { getDefaultArrivals, getCongestionLabel, getCongestionColor } from "../../api/busService";
import { Accessibility, BusFront, MapPin, Radio, RefreshCw, Volume2, Wifi, ZoomIn } from "lucide-react";
import { useAccessibilityDisplay } from "../../hooks/useAccessibilityDisplay";

const STATION_NAME = import.meta.env.VITE_STATION_NAME ?? "정류장";

const SOON_SEC    = 3 * 60; // 잠시 후 도착 기준: 180초 미만
const SOON_ARRIVE = 60;     // 곧 도착 기준: 60초 미만
const SOON_PER_PAGE = 5;
const MAIN_PER_PAGE = 5;
const REFRESH_MS    = 15_000;
const MAX_MIN       = 30;
const DAY_KR = ["일", "월", "화", "수", "목", "금", "토"];

export function accessibilityScore(bus: BusInfo): number {
  const fullPenalty = bus.isFullFlag ? 100 : 0;
  const lowFloorBonus = bus.busType === 1 ? -20 : 0;
  const congestionPenalty = bus.congestion === 5 ? 15 : bus.congestion === 4 ? 5 : bus.congestion === 0 ? 10 : 0;
  return fullPenalty + lowFloorBonus + congestionPenalty + bus.arrivalMin;
}

// 카드/행 전체를 스크린리더가 하나의 문장으로 읽도록 요약합니다.
// (개별 텍스트 조각을 순서대로 읽으면 맥락 없이 끊겨 들리는 문제를 방지)
export function describeBus(bus: BusInfo): string {
  const arrival = bus.traTimeSec < SOON_ARRIVE ? "곧 도착" : `약 ${bus.arrivalMin}분 후 도착`;
  const congestion = getCongestionLabel(bus.congestion);
  const parts = [`${bus.busNumber}번 버스`, arrival, `혼잡도 ${congestion}`];
  if (bus.currentStationName) parts.push(`${bus.currentStationName} 통과`);
  if (bus.busType === 1) parts.push("저상버스");
  if (bus.isFullFlag) parts.push("만차");
  if (bus.isLastBus) parts.push("막차");
  return parts.join(", ");
}

export function getApproachThreshold(previous: number | null, current: number): number | null {
  return [0, 1, 3].find(
    (threshold) => current <= threshold && (previous === null || previous > threshold),
  ) ?? null;
}

// ─── 원형 프로그레스 ─────────────────────────────────────────
function CircleTimer({ arrivalMin }: { arrivalMin: number }) {
  const r = 30;
  const circumference = 2 * Math.PI * r;
  const ratio = Math.min(arrivalMin / MAX_MIN, 1);
  const dash  = ratio * circumference;
  const color = arrivalMin <= 5 ? "#F59E0B" : "#FACC15";

  return (
    <svg viewBox="0 0 76 76" className="size-12 sm:size-14 md:size-16" aria-label={`${arrivalMin}분 후 도착`}>
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
    <>
      <span className="mt-1 text-[11px] font-bold text-[#475569] sm:hidden">{remaining}정거장 전</span>
      <div className="mt-1.5 hidden items-center gap-0 sm:flex">
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
    </>
  );
}

// ─── 잠시 후 도착 카드 (시간 없음, 번호+혼잡도만) ────────────
function SoonCard({ bus, isTracked, onTrack }: { bus: BusInfo; isTracked: boolean; onTrack: () => void }) {
  const congLabel = getCongestionLabel(bus.congestion);
  const congColor = getCongestionColor(bus.congestion);
  return (
    <button type="button" onClick={onTrack} aria-pressed={isTracked} aria-label={describeBus(bus)} className={`flex min-w-0 flex-col items-center justify-center gap-2 rounded-xl border bg-[#171D23] px-2 py-3 shadow-[0_8px_18px_rgba(23,29,35,0.22)] transition-transform hover:-translate-y-0.5 ${isTracked ? "border-white ring-2 ring-white" : "border-[#303842]"}`}>
      <div className={`rounded-full px-3 py-0.5 text-[12px] font-black border ${congColor}`}>
        {congLabel}
      </div>
      <div className="max-w-full truncate text-[28px] font-black text-[#FACC15] font-mono leading-none sm:text-[36px] md:text-[42px]">
        {bus.busNumber}
      </div>
      <div className="flex flex-wrap justify-center gap-1">
        {bus.busType === 1 && <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-black text-sky-800">저상</span>}
        {bus.isFullFlag && <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-black text-white">만차</span>}
        {bus.isLastBus && <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-black text-white">막차</span>}
      </div>
    </button>
  );
}

// ─── 로딩 스켈레톤 ───────────────────────────────────────────
function SkeletonRow({ idx }: { idx: number }) {
  return (
    <div className={`grid min-h-[56px] min-w-0 w-full flex-1 shrink-0 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] items-center border-b border-[#E2E8F0] sm:min-h-[68px] md:grid-cols-[150px_110px_1fr] ${idx % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`}>
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
  const [accessibleMode, setAccessibleMode] = useState(false);
  const [largeTextMode, toggleLargeTextMode] = useAccessibilityDisplay();
  const [trackedBusId, setTrackedBusId] = useState<string | null>(null);
  const lastRemainingStopsRef = useRef<number | null>(null);
  const approachUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const now = useLiveClock();
  const { buses, liveStationName, loading, error, lastUpdated, refetch } = useBusArrivals();

  const cancelApproachSpeech = useCallback(() => {
    if (approachUtteranceRef.current && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      approachUtteranceRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!trackedBusId) {
      lastRemainingStopsRef.current = null;
      return;
    }
    const tracked = buses.find((bus) => bus.id === trackedBusId || bus.plainNo === trackedBusId);
    if (!tracked || tracked.remainingStops < 0) return;

    const previous = lastRemainingStopsRef.current;
    const crossed = getApproachThreshold(previous, tracked.remainingStops);
    if (crossed === null) {
      lastRemainingStopsRef.current = tracked.remainingStops;
      return;
    }
    if (!("speechSynthesis" in window)) {
      lastRemainingStopsRef.current = tracked.remainingStops;
      return;
    }
    if (window.speechSynthesis.speaking) {
      lastRemainingStopsRef.current = tracked.remainingStops;
      return;
    }
    lastRemainingStopsRef.current = tracked.remainingStops;

    const message = crossed === 0
      ? `${tracked.busNumber}번 버스가 곧 도착합니다. 승차를 준비해 주세요.`
      : crossed === 1
        ? `${tracked.busNumber}번 버스가 한 정거장 전입니다.`
        : `${tracked.busNumber}번 버스가 세 정거장 이내로 접근했습니다.`;
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.lang = "ko-KR";
    utterance.rate = 0.9;
    approachUtteranceRef.current = utterance;
    const releaseUtterance = () => {
      if (approachUtteranceRef.current === utterance) {
        approachUtteranceRef.current = null;
      }
    };
    utterance.onend = releaseUtterance;
    utterance.onerror = releaseUtterance;
    window.speechSynthesis.speak(utterance);
    return () => {
      if (approachUtteranceRef.current === utterance) {
        cancelApproachSpeech();
      }
    };
  }, [buses, cancelApproachSpeech, trackedBusId]);

  const toggleTracking = (bus: BusInfo) => {
    cancelApproachSpeech();
    const trackingId = bus.plainNo || bus.id;
    setTrackedBusId((current) => current === trackingId ? null : trackingId);
    lastRemainingStopsRef.current = null;
  };

  const rankedBuses = useMemo(
    () => accessibleMode
      ? [...buses].sort((a, b) => accessibilityScore(a) - accessibilityScore(b))
      : buses,
    [accessibleMode, buses],
  );
  const arrivingSoon = useMemo(
    () => rankedBuses.filter((bus) => bus.traTimeSec < SOON_SEC),
    [rankedBuses],
  );
  const soonTotalPages = Math.max(1, Math.ceil(arrivingSoon.length / SOON_PER_PAGE));
  const mainTotalPages = Math.max(1, Math.ceil(rankedBuses.length / MAIN_PER_PAGE));

  useEffect(() => {
    if (soonTotalPages <= 1 || trackedBusId) return;
    const id = setInterval(() => setSoonPage((p) => (p + 1) % soonTotalPages), 5000);
    return () => clearInterval(id);
  }, [soonTotalPages, trackedBusId]);

  useEffect(() => {
    if (mainTotalPages <= 1 || trackedBusId) return;
    const id = setInterval(() => setMainPage((p) => (p + 1) % mainTotalPages), 5000);
    return () => clearInterval(id);
  }, [mainTotalPages, trackedBusId]);

  const curSoonPage = Math.min(soonPage, soonTotalPages - 1);
  const curMainPage = Math.min(mainPage, mainTotalPages - 1);
  const currentSoon = arrivingSoon.slice(curSoonPage * SOON_PER_PAGE, (curSoonPage + 1) * SOON_PER_PAGE);
  const currentMain = rankedBuses.slice(curMainPage * MAIN_PER_PAGE, (curMainPage + 1) * MAIN_PER_PAGE);

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
  const isStale = !loading && (!lastUpdated || now.getTime() - lastUpdated.getTime() > 45_000);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-[#EDF1F3] font-['Noto_Sans_KR']">

      {/* ── 헤더 ─────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between border-b-4 border-[#F0C929] bg-[#171D23] px-3 py-2 sm:px-6 sm:py-3">
        <div className="flex min-w-0 items-center gap-2 text-left sm:gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-md bg-[#F0C929] text-[#171D23] sm:size-12">
            <MapPin className="size-5 sm:size-6" />
          </div>
          <div className="min-w-0">
            <span className="mb-0.5 hidden text-[13px] font-bold text-white/50 sm:block">서울특별시 · 실시간 버스정보</span>
            <span className="block max-w-[36vw] truncate text-[18px] font-black leading-tight text-white sm:max-w-[44vw] sm:text-[28px] md:text-[32px]">{liveStationName || STATION_NAME}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={toggleLargeTextMode}
            aria-pressed={largeTextMode}
            className={`inline-flex items-center gap-2 rounded-md border p-2 text-xs font-black sm:px-3 ${largeTextMode ? "border-[#F0C929] bg-[#F0C929] text-[#171D23]" : "border-white/20 bg-white/10 text-white"}`}
            title="큰 글씨·고대비 화면으로 전환"
          >
            <ZoomIn className="size-4" /><span className="hidden sm:inline">큰 글씨</span>
          </button>
          <button
            type="button"
            onClick={() => { setAccessibleMode((enabled) => !enabled); setMainPage(0); setSoonPage(0); }}
            aria-pressed={accessibleMode}
            className={`inline-flex items-center gap-2 rounded-md border p-2 text-xs font-black sm:px-3 ${accessibleMode ? "border-[#F0C929] bg-[#F0C929] text-[#171D23]" : "border-white/20 bg-white/10 text-white"}`}
            title="저상·비혼잡 도착 차량 우선 표시"
          >
            <Accessibility className="size-4" /><span className="hidden sm:inline">저상·여유 우선</span>
          </button>
          <div className="text-right text-white">
          <div className="mb-1 hidden text-[13px] text-white/65 sm:block">{yy}년 {mm}월 {dd}일 ({day})</div>
          <div className="flex items-baseline gap-1 font-mono text-[22px] font-black leading-none text-white sm:text-[36px] md:gap-2 md:text-[44px]">
            <span className="text-[12px] text-yellow-400 sm:text-[20px] md:text-[24px]">{ampm}</span>
            {displayH}:{displayM}:{displayS}
          </div>
          </div>
        </div>
      </div>

      {/* ── 오류 배너 ────────────────────────────── */}
      {error && (
        <div className="bg-red-600 text-white text-[13px] font-bold px-5 py-2 flex items-center justify-between shrink-0">
          <span>{error}</span>
          <button onClick={refetch} className="ml-4 inline-flex items-center gap-1 text-white hover:text-white/90"><RefreshCw className="size-3.5" />다시 시도</button>
        </div>
      )}

      {/* ── 잠시 후 도착 (3분 미만, 시간 없음) ───── */}
      <div className="shrink-0 border-b border-[#C99F11] bg-[#F0C929] px-3 pb-3 pt-2 sm:px-5 sm:pb-4 sm:pt-3">
        <div className="flex justify-between items-end mb-3">
          <div className="flex flex-col text-left">
            <span className="text-[20px] font-black leading-tight text-[#2C2A1A] sm:text-[24px]">잠시 후 도착</span>
            <span className="text-[12px] font-bold text-[#4E3F0C] sm:text-[13px]">3분 이내 도착 차량</span>
          </div>
          {lastUpdatedStr && <span className={`text-[12px] font-bold ${isStale ? "text-red-700" : "text-[#78350F]"}`}>{isStale ? `정보 지연 · ${lastUpdatedStr}` : lastUpdatedStr}</span>}
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
          <div className="grid grid-cols-2 items-stretch gap-2 sm:grid-cols-5">
            {currentSoon.map((bus) => <SoonCard key={bus.id} bus={bus} isTracked={trackedBusId === (bus.plainNo || bus.id)} onTrack={() => toggleTracking(bus)} />)}
            {currentSoon.length < SOON_PER_PAGE && (
              <div
                className="hidden min-h-[92px] items-center justify-center gap-3 rounded-xl border border-[#6F611E]/25 bg-[#E5BE24]/55 px-5 text-[#4E4214] sm:flex"
                style={{ gridColumn: `span ${SOON_PER_PAGE - currentSoon.length}` }}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-black/10"><Radio className="size-5" /></span>
                <span className="text-left"><strong className="block text-sm font-black">실시간 도착정보 수신 중</strong><span className="text-xs font-bold text-[#4E4214]">새로운 차량이 확인되면 바로 표시됩니다.</span></span>
              </div>
            )}
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
        <div data-testid="main-bus-scroll" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto bg-[#F1F5F9]">
          <div className="flex min-h-full min-w-0 flex-col">
            {loading
              ? Array.from({ length: MAIN_PER_PAGE }).map((_, i) => <SkeletonRow key={i} idx={i} />)
              : currentMain.map((bus, idx) => {
                  const congLabel = getCongestionLabel(bus.congestion);
                  const congColor = getCongestionColor(bus.congestion);
                  const isArriving = bus.traTimeSec < SOON_ARRIVE;

                  return (
                    <button data-testid="main-bus-row" type="button" onClick={() => toggleTracking(bus)} aria-pressed={trackedBusId === (bus.plainNo || bus.id)} aria-label={describeBus(bus)} key={bus.id} className={`grid min-h-[56px] min-w-0 w-full flex-1 shrink-0 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] items-center border-b border-[#E2E8F0] text-left sm:min-h-[68px] md:grid-cols-[150px_110px_1fr]
                      ${trackedBusId === (bus.plainNo || bus.id) ? "bg-amber-50 ring-2 ring-inset ring-[#F0C929]" : idx % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`}>

                      {/* 노선번호 */}
                      <div className="flex items-center justify-center px-4 border-r border-[#E2E8F0] h-full">
                        <span className="max-w-full truncate text-[22px] font-black leading-none text-[#1E293B] sm:text-[27px] md:text-[32px]">
                          {bus.busNumber}
                        </span>
                      </div>

                      {/* 예정시간 */}
                      <div className="flex h-full items-center justify-center border-r border-[#E2E8F0]">
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
                          <div className="mt-1 flex gap-1">
                            {bus.busType === 1 && <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-black text-sky-800">저상버스</span>}
                            {bus.isFullFlag && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-black text-red-700">만차</span>}
                          </div>
                          {bus.isLastBus && (
                            <span className="text-[12px] text-red-500 font-black mt-0.5">막차</span>
                          )}
                        </div>
                      </div>

                    </button>
                  );
                })}

            {!loading && currentMain.length < MAIN_PER_PAGE && (
              <div className="grid min-h-[68px] flex-1 place-items-center bg-[linear-gradient(135deg,#f8fafc_25%,#f1f5f9_25%,#f1f5f9_50%,#f8fafc_50%,#f8fafc_75%,#f1f5f9_75%)] bg-[length:24px_24px] px-4 text-center">
                <div className="rounded-full border border-slate-200 bg-white/95 px-4 py-2 text-xs font-bold text-slate-500 shadow-sm">
                  현재 확인된 도착 차량은 {currentMain.length}대입니다
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex shrink-0 items-center justify-between border-t border-[#CBD5E1] bg-[#EDF1F3] px-3 py-2 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" onClick={refetch} className={`inline-flex items-center gap-1.5 text-[12px] font-bold hover:text-[#1B2930] ${isStale ? "text-red-700" : "text-[#52616B]"}`} title="도착 정보 새로고침">
              <Wifi className={`size-3.5 ${isStale ? "text-red-600" : "text-emerald-600"}`} /> {isStale ? "정보 갱신 지연 · 다시 시도" : "실시간 · 15초마다 갱신"}
            </button>
            {trackedBusId && <span className="hidden items-center gap-1 truncate text-[12px] font-black text-[#145466] sm:inline-flex"><Volume2 className="size-3.5" /> 선택 차량 도착 알림 중</span>}
          </div>
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
