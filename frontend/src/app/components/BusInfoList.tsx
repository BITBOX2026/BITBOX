import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { BusOption as BusInfo } from "../../types/bus";
import { getDefaultArrivals, getCongestionLabel, getCongestionColor, describeArrivalStatus } from "../../api/busService";
import { Accessibility, BusFront, ChevronLeft, ChevronRight, MapPin, Pause, Play, Radio, RefreshCw, Volume2, Wifi, ZoomIn } from "lucide-react";
import { useAccessibilityDisplay } from "../../hooks/useAccessibilityDisplay";
import { cancelSpeech, speakKorean } from "../../utils/speech";
import { busNumberFontSize } from "../../utils/busNumberFit";
import { useElementHeight, useVisibleRowCount } from "../../hooks/useVisibleRowCount";

const STATION_NAME = import.meta.env.VITE_STATION_NAME ?? "정류장";

const SOON_SEC    = 3 * 60; // 잠시 후 도착 기준: 180초 미만
const SOON_ARRIVE = 60;     // 곧 도착 기준: 60초 미만
const SOON_PER_PAGE = 5;
const MAIN_PER_PAGE = 5;
const REFRESH_MS    = 15_000;
// 한 화면을 읽고 의미를 파악할 시간을 충분히 줍니다. 5초는 표의 다섯 행을
// 읽는 고령 이용자에게 너무 짧았고, 수동 조작 시에는 기존처럼 자동 전환을 멈춥니다.
const PAGE_ROTATION_MS = 10_000;
// 서버 TTS 상한(15초) 직후 실제 오디오가 재생되는 경우까지 포함합니다. 이 값이
// 폴링 주기와 같으면 다음 폴링이 새 안내를 시작해 막 재생된 음성을 다시 끊습니다.
const APPROACH_SPEECH_RELEASE_MS = 30_000;
// 추적 차량이 도착정보에서 사라졌다고 판정하기까지 필요한 연속 폴링 횟수.
// 한 번의 일시적 누락으로 추적을 풀면 이용자가 고른 버스를 놓칩니다.
const TRACKED_BUS_MISSING_POLLS = 2;
// "잠시 후 도착" 패널은 172px 를 씁니다. 전광판이 이보다 낮으면 이 패널 때문에
// 정작 도착 목록이 한두 줄로 줄어듭니다. 여기 실린 차량은 아래 목록에도 그대로
// 나오므로, 공간이 부족하면 중복 요약을 접고 목록을 살리는 쪽이 맞습니다.
// 값의 근거: 전광판 640px = 머리글 98 + 패널 172 + 표 머리글·바닥 106 + 3행(240).
const SOON_PANEL_MIN_BOARD_HEIGHT = 640;
const MAX_MIN       = 30;
const DAY_KR = ["일", "월", "화", "수", "목", "금", "토"];

export function accessibilityScore(bus: BusInfo): number {
  // 도착 시각이 없는 행은 arrivalMin 이 -1 이라 정렬에서 맨 앞으로 튀어나옵니다.
  // 탑승할 수 없는 노선이므로 항상 뒤로 보냅니다.
  if (bus.status !== "live") return Number.MAX_SAFE_INTEGER;
  const fullPenalty = bus.isFullFlag ? 100 : 0;
  const lowFloorBonus = bus.busType === 1 ? -20 : 0;
  const congestionPenalty = bus.congestion === 5 ? 15 : bus.congestion === 4 ? 5 : bus.congestion === 0 ? 10 : 0;
  return fullPenalty + lowFloorBonus + congestionPenalty + bus.arrivalMin;
}

// 카드/행 전체를 스크린리더가 하나의 문장으로 읽도록 요약합니다.
// (개별 텍스트 조각을 순서대로 읽으면 맥락 없이 끊겨 들리는 문제를 방지)
export function describeBus(bus: BusInfo): string {
  if (bus.status !== "live") {
    // 음수 sentinel 을 시간 비교에 넣으면 "곧 도착"으로 잘못 읽힙니다.
    const parts = [`${bus.busNumber}번 버스`, describeArrivalStatus(bus.status)];
    if (bus.isLastBus) parts.push("막차");
    return parts.join(", ");
  }
  const arrival = bus.traTimeSec < SOON_ARRIVE ? "곧 도착" : `약 ${bus.arrivalMin}분 후 도착`;
  const congestion = getCongestionLabel(bus.congestion);
  const parts = [`${bus.busNumber}번 버스`, arrival, `혼잡도 ${congestion}`];
  if (bus.currentStationName) parts.push(`${bus.currentStationName} 통과`);
  if (bus.busType === 1) parts.push("저상버스");
  if (bus.isFullFlag) parts.push("만차");
  if (bus.isLastBus) parts.push("막차");
  return parts.join(", ");
}

/**
 * 전광판 오류 배너에 쓸 한국어 문구를 고릅니다.
 *
 * `AbortSignal.timeout()` 이 만드는 DOMException 의 message 는 "signal timed out"
 * 같은 영어 기술 문구입니다. 그대로 배너에 넣으면 교통약자 이용자에게 아무 의미가
 * 없으므로, 서버가 내려 준 한국어 안내만 통과시키고 나머지는 정해진 문구로 바꿉니다.
 */
export function toKoreanBoardError(error: unknown): string {
  if (error instanceof DOMException) {
    return error.name === "TimeoutError" || error.name === "AbortError"
      ? "도착 정보를 불러오는 데 시간이 오래 걸립니다. 잠시 후 다시 시도해 주세요."
      : "도착 정보를 불러오지 못했습니다.";
  }
  const message = error instanceof Error ? error.message.trim() : "";
  // 한글이 포함된 메시지만 서버가 준 사용자 안내로 간주합니다.
  return /[가-힣]/.test(message) ? message : "도착 정보를 불러오지 못했습니다.";
}

export function getApproachThreshold(previous: number | null, current: number): number | null {
  return [0, 1, 3].find(
    (threshold) => current <= threshold && (previous === null || previous > threshold),
  ) ?? null;
}

export function approachMessage(busNumber: string, crossed: number): string {
  if (crossed === 0) return `${busNumber}번 버스가 곧 도착합니다. 승차를 준비해 주세요.`;
  if (crossed === 1) return `${busNumber}번 버스가 한 정거장 전입니다.`;
  return `${busNumber}번 버스가 세 정거장 이내로 접근했습니다.`;
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
        fontSize="1.375rem" fontWeight="900" fill="#1E293B" fontFamily="monospace">
        {arrivalMin}
      </text>
      <text x="38" y="54" textAnchor="middle"
        fontSize="0.75rem" fontWeight="700" fill="#64748B">
        분
      </text>
    </svg>
  );
}

// ─── 정거장 도트 시각화 ──────────────────────────────────────
function StopsDot({ remaining }: { remaining: number }) {
  if (remaining < 0) return null;
  if (remaining === 0) return (
    <span className="mt-1 inline-block rounded border border-red-200 bg-red-50 px-2 py-0.5 text-[0.75rem] font-black text-red-700">
      정류소 곧 도착
    </span>
  );

  const MAX_DOTS = 6;
  const showStops = Math.min(remaining, MAX_DOTS);
  const dots = Array.from({ length: showStops }, (_, i) => showStops - i);

  return (
    <>
      <span className="mt-1 text-[0.6875rem] font-bold text-[#475569] sm:hidden">{remaining}정거장 전</span>
      <div className="mt-1.5 hidden items-center gap-0 sm:flex">
        <BusFront className="mr-1 size-4 shrink-0 text-[#2563EB]" aria-hidden="true" />
        <div className="h-[2px] w-2 bg-[#CBD5E1]" />
        {dots.map((n, i) => (
          <div key={n} className="flex items-center">
            <div className={`w-[18px] h-[18px] rounded-full border-2 flex items-center justify-center
              ${i === 0 ? "bg-[#3B82F6] border-[#2563EB]" : "bg-white border-[#CBD5E1]"}`}>
              <span className={`text-[0.5625rem] font-black leading-none ${i === 0 ? "text-white" : "text-[#64748B]"}`}>
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
    <button type="button" onClick={onTrack} aria-pressed={isTracked} aria-label={describeBus(bus)} className={`flex min-w-0 flex-col items-center justify-center gap-2 rounded-xl border bg-[#171D23] px-2 py-2 [container-type:inline-size] shadow-[0_8px_18px_rgba(23,29,35,0.22)] transition-transform hover:-translate-y-0.5 ${isTracked ? "border-white ring-2 ring-white" : "border-[#303842]"}`}>
      <div className={`rounded-full border px-3 py-0.5 text-[0.75rem] font-black ${congColor}`}>
        {congLabel}
      </div>
      <div
        className="max-w-full whitespace-nowrap text-center font-mono font-black leading-tight text-[#FACC15]"
        style={{ fontSize: busNumberFontSize(bus.busNumber, 2) }}
        title={`${bus.busNumber}번 버스`}
      >
        {bus.busNumber}
      </div>
      <div className="flex flex-wrap justify-center gap-1">
        {bus.busType === 1 && <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[0.625rem] font-black text-sky-800">저상</span>}
        {bus.isFullFlag && <span className="rounded bg-red-600 px-1.5 py-0.5 text-[0.625rem] font-black text-white">만차</span>}
        {bus.isLastBus && <span className="rounded bg-red-600 px-1.5 py-0.5 text-[0.625rem] font-black text-white">막차</span>}
      </div>
    </button>
  );
}

// ─── 로딩 스켈레톤 ───────────────────────────────────────────
function SkeletonRow({ idx }: { idx: number }) {
  return (
    <div className={`grid min-h-[56px] w-full min-w-0 shrink-0 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] items-center border-b border-[#E2E8F0] sm:min-h-[68px] md:grid-cols-[150px_110px_1fr] ${idx % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`}>
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
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const { stationName, buses: data } = await getDefaultArrivals();
      if (!mountedRef.current) return;
      setBuses(data);
      setLiveStationName(stationName); // 가져온 실시간 서버 정류소 이름을 저장
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      if (!mountedRef.current) return;
      // DOMException 의 원문("signal timed out")은 영어 기술 문구라 그대로
      // 보여 주면 안 됩니다. 서버가 준 한국어 안내만 통과시킵니다.
      setError(toKoreanBoardError(err));
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    const id = setInterval(fetchData, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  return { buses, liveStationName, loading, error, lastUpdated, refetch: fetchData };
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────
export function BusInfoList({ compact = false }: { compact?: boolean }) {
  const [mainPage, setMainPage] = useState(0);
  const [soonPage, setSoonPage] = useState(0);
  const [accessibleMode, setAccessibleMode] = useState(false);
  const [largeTextMode, toggleLargeTextMode] = useAccessibilityDisplay();
  const [autoRotate, setAutoRotate] = useState(true);
  const [trackedBusId, setTrackedBusId] = useState<string | null>(null);
  const mainScrollRef = useRef<HTMLDivElement>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const lastRemainingStopsRef = useRef<number | null>(null);
  // 진행 중인 도착 알림의 세대 번호. 브라우저 음성과 서버 음성 어느 쪽으로 나가든
  // 같은 방식으로 소유권을 판단하기 위해 객체 대신 숫자를 씁니다.
  const approachSpeechIdRef = useRef(0);
  const approachSpeakingRef = useRef(false);
  const approachReleaseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const now = useLiveClock();
  const { buses, liveStationName, loading, error, lastUpdated, refetch } = useBusArrivals();
  const trackedBus = useMemo(
    () => buses.find((bus) => bus.id === trackedBusId || bus.plainNo === trackedBusId),
    [buses, trackedBusId],
  );
  const trackedBusNumber = trackedBus?.busNumber;
  const trackedBusStatus = trackedBus?.status;
  const trackedRemainingStops = trackedBus?.remainingStops;

  // 재생이 끝난 뒤 보관해 둔 임계값을 다시 평가할 때, 그 사이 차량 상태가 바뀌지
  // 않았는지 확인하기 위한 최신 스냅샷입니다.
  const trackedSnapshotRef = useRef<{
    busNumber?: string; status?: string; remainingStops?: number;
  }>({});
  // 안내가 재생 중이라 아직 말하지 못한 임계값. 그냥 버리면 "곧 도착" 처럼 가장
  // 중요한 안내가 영영 사라집니다.
  const pendingApproachRef = useRef<{ crossed: number; busNumber: string } | null>(null);
  const flushPendingApproachRef = useRef<() => void>(() => {});
  // 추적 차량이 도착정보에서 연속으로 보이지 않은 폴링 횟수입니다.
  const trackedMissRef = useRef(0);

  const cancelApproachSpeech = useCallback(() => {
    approachSpeechIdRef.current += 1;
    approachSpeakingRef.current = false;
    pendingApproachRef.current = null;
    if (approachReleaseTimerRef.current) {
      clearTimeout(approachReleaseTimerRef.current);
      approachReleaseTimerRef.current = null;
    }
    cancelSpeech();
  }, []);

  const startApproachSpeech = useCallback((busNumber: string, crossed: number) => {
    const speechId = ++approachSpeechIdRef.current;
    approachSpeakingRef.current = true;
    if (approachReleaseTimerRef.current) {
      clearTimeout(approachReleaseTimerRef.current);
      approachReleaseTimerRef.current = null;
    }
    const release = () => {
      if (approachSpeechIdRef.current !== speechId) return;
      approachSpeakingRef.current = false;
      if (approachReleaseTimerRef.current) {
        clearTimeout(approachReleaseTimerRef.current);
        approachReleaseTimerRef.current = null;
      }
      // 보관해 둔 임계값은 재생이 끝나야 말할 수 있습니다. ref 만 바꾸면 아래
      // effect 는 의존값이 그대로여서 다시 실행되지 않으므로 여기서 직접 평가합니다.
      flushPendingApproachRef.current();
    };
    // 재생 종료 신호가 오지 않는 경우에도 다음 알림이 영영 막히지 않도록 상한을 둡니다.
    approachReleaseTimerRef.current = setTimeout(release, APPROACH_SPEECH_RELEASE_MS);

    // 기기에 한국어 음성이 없으면 서버 음성으로 대체됩니다. 둘 다 안 되면
    // 화면의 도착 표시로만 안내되며, 알림 자체는 조용히 실패합니다.
    void speakKorean(approachMessage(busNumber, crossed), {
      onEnd: release,
      activitySource: "background",
    }).then((outcome) => {
      if (outcome === "unavailable") release();
    });
  }, []);

  const flushPendingApproach = useCallback(() => {
    const pending = pendingApproachRef.current;
    if (!pending) return;
    pendingApproachRef.current = null;
    const snapshot = trackedSnapshotRef.current;
    // 같은 차량이 아직 운행 중이고, 보관한 임계값이 여전히 사실일 때만 말합니다.
    // 이미 더 가까워졌다면 다음 폴링이 더 급한 안내를 만들어 냅니다.
    if (snapshot.busNumber !== pending.busNumber) return;
    if (snapshot.status !== "live") return;
    if (snapshot.remainingStops == null || snapshot.remainingStops > pending.crossed) return;
    startApproachSpeech(pending.busNumber, pending.crossed);
  }, [startApproachSpeech]);

  useEffect(() => {
    flushPendingApproachRef.current = flushPendingApproach;
  }, [flushPendingApproach]);

  useEffect(() => {
    trackedSnapshotRef.current = {
      busNumber: trackedBusNumber,
      status: trackedBusStatus,
      remainingStops: trackedRemainingStops,
    };
    if (!trackedBusId) {
      lastRemainingStopsRef.current = null;
      return;
    }
    if (
      !trackedBusNumber
      || trackedBusStatus !== "live"
      || trackedRemainingStops == null
      || trackedRemainingStops < 0
    ) return;

    const previous = lastRemainingStopsRef.current;
    const crossed = getApproachThreshold(previous, trackedRemainingStops);
    if (crossed === null) {
      lastRemainingStopsRef.current = trackedRemainingStops;
      return;
    }
    lastRemainingStopsRef.current = trackedRemainingStops;

    if (approachSpeakingRef.current) {
      // 곧 도착(0정거장)은 승차 준비 신호라 가장 급합니다. 재생 중인 안내를
      // 대체하지 않으면 이 안내는 영영 나가지 못합니다.
      if (crossed === 0) {
        pendingApproachRef.current = null;
        startApproachSpeech(trackedBusNumber, 0);
        return;
      }
      // 나머지는 잘라내지도, 버리지도 않고 보관했다가 재생이 끝난 뒤 평가합니다.
      const pending = pendingApproachRef.current;
      if (!pending || pending.busNumber !== trackedBusNumber || crossed < pending.crossed) {
        pendingApproachRef.current = { crossed, busNumber: trackedBusNumber };
      }
      return;
    }

    // 폴링으로 remainingStops가 바뀌어도 진행 중 안내를 cleanup에서 취소하지
    // 않습니다. 추적 해제·다른 버스 선택은 toggleTracking이 명시적으로 취소하고,
    // 컴포넌트 제거는 아래 전용 cleanup이 담당합니다.
    startApproachSpeech(trackedBusNumber, crossed);
  }, [trackedBusId, trackedBusNumber, trackedBusStatus, trackedRemainingStops, startApproachSpeech]);

  // 추적하던 차량은 언젠가 반드시 도착해 목록에서 사라집니다. 그때 추적 상태가
  // 남아 있으면 "선택 차량 도착 알림 중" 표시가 켜진 채로 자동 페이지 전환이
  // 영구히 멈춰, 뒤에 온 이용자는 2페이지의 노선을 볼 수 없습니다. 무인 키오스크
  // 에서는 아무도 되돌릴 수 없으므로 스스로 해제합니다.
  useEffect(() => {
    if (!trackedBusId || trackedBus) {
      trackedMissRef.current = 0;
      return;
    }
    trackedMissRef.current += 1;
    if (trackedMissRef.current < TRACKED_BUS_MISSING_POLLS) return;
    trackedMissRef.current = 0;
    cancelApproachSpeech();
    lastRemainingStopsRef.current = null;
    setTrackedBusId(null);
  }, [buses, trackedBus, trackedBusId, cancelApproachSpeech]);

  useEffect(() => () => cancelApproachSpeech(), [cancelApproachSpeech]);

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
    () => rankedBuses.filter((bus) => bus.status === "live" && bus.traTimeSec < SOON_SEC),
    [rankedBuses],
  );
  const soonTotalPages = Math.max(1, Math.ceil(arrivingSoon.length / SOON_PER_PAGE));
  // 큰 글씨 모드에서는 행이 높아져 5행이 들어가지 않습니다. 잘린 행을 보여 주는
  // 대신 페이지에 담는 행 수를 줄입니다. 나머지는 자동 페이지 전환이 보여 줍니다.
  const mainPerPage = useVisibleRowCount(mainScrollRef, "[data-testid=main-bus-row]", {
    max: MAIN_PER_PAGE,
    resetKey: `${largeTextMode}:${accessibleMode}:${rankedBuses.length}`,
  });
  const mainTotalPages = Math.max(1, Math.ceil(rankedBuses.length / mainPerPage));

  useEffect(() => {
    if (!autoRotate || soonTotalPages <= 1 || trackedBusId) return;
    const id = setInterval(() => setSoonPage((p) => (p + 1) % soonTotalPages), PAGE_ROTATION_MS);
    return () => clearInterval(id);
  }, [autoRotate, soonTotalPages, trackedBusId]);

  useEffect(() => {
    if (!autoRotate || mainTotalPages <= 1 || trackedBusId) return;
    const id = setInterval(() => setMainPage((p) => (p + 1) % mainTotalPages), PAGE_ROTATION_MS);
    return () => clearInterval(id);
  }, [autoRotate, mainTotalPages, trackedBusId]);

  const curSoonPage = Math.min(soonPage, soonTotalPages - 1);
  const curMainPage = Math.min(mainPage, mainTotalPages - 1);
  const currentSoon = arrivingSoon.slice(curSoonPage * SOON_PER_PAGE, (curSoonPage + 1) * SOON_PER_PAGE);
  const currentMain = rankedBuses.slice(curMainPage * mainPerPage, (curMainPage + 1) * mainPerPage);

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
  const boardHeight = useElementHeight(boardRef);
  const showSoonPanel = !compact && boardHeight >= SOON_PANEL_MIN_BOARD_HEIGHT;

  return (
    <div ref={boardRef} className="flex h-full w-full flex-col overflow-hidden bg-[#EDF1F3] font-kiosk">

      {/* ── 헤더 ─────────────────────────────────── */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b-4 border-[#F0C929] bg-[#171D23] px-3 py-2 sm:flex-nowrap sm:px-6 sm:py-3">
        <div className="flex min-w-0 w-full items-center gap-2 text-left sm:w-auto sm:gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-md bg-[#F0C929] text-[#171D23] sm:size-12">
            <MapPin className="size-5 sm:size-6" />
          </div>
          <div className="min-w-0">
            <span className="mb-0.5 hidden text-[0.8125rem] font-bold text-white/50 sm:block">서울특별시 · 실시간 버스정보</span>
            {/* 정류장 이름은 이 화면의 현재 위치입니다. 잘라내면 이용자가 자기가
                어느 정류장에 서 있는지 확인할 수 없으므로 두 줄까지 펼칩니다. */}
            {/* leading-normal 을 줄이면 line-clamp 의 overflow:hidden 이 한글 아래쪽
                획을 잘라냅니다(글꼴의 자연 라인박스가 더 큽니다). */}
            <span data-testid="station-name" className="line-clamp-2 block max-w-full break-words text-[1.125rem] font-black leading-normal text-white sm:max-w-[44vw] sm:text-[1.75rem] md:text-[2rem]">{liveStationName || STATION_NAME}</span>
          </div>
        </div>
        <div className="flex w-full shrink-0 items-center justify-between gap-2 sm:w-auto sm:justify-start sm:gap-3">
          <button
            type="button"
            onClick={toggleLargeTextMode}
            aria-pressed={largeTextMode}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border p-2 text-xs font-black sm:px-3 ${largeTextMode ? "border-[#F0C929] bg-[#F0C929] text-[#171D23]" : "border-white/20 bg-white/10 text-white"}`}
            title="큰 글씨·고대비 화면으로 전환"
          >
            <ZoomIn className="size-4" /><span className="hidden sm:inline">큰 글씨</span>
          </button>
          <button
            type="button"
            onClick={() => { setAccessibleMode((enabled) => !enabled); setMainPage(0); setSoonPage(0); }}
            aria-pressed={accessibleMode}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border p-2 text-xs font-black sm:px-3 ${accessibleMode ? "border-[#F0C929] bg-[#F0C929] text-[#171D23]" : "border-white/20 bg-white/10 text-white"}`}
            title="저상·비혼잡 도착 차량 우선 표시"
          >
            <Accessibility className="size-4" /><span className="hidden sm:inline">저상·여유 우선</span>
          </button>
          <div className="text-right text-white">
          <div className="mb-1 hidden text-[0.8125rem] text-white/65 sm:block">{yy}년 {mm}월 {dd}일 ({day})</div>
          <div className="flex items-baseline gap-1 font-mono text-[1.375rem] font-black leading-none text-white sm:text-[2.25rem] md:gap-2 md:text-[2.75rem]">
            <span className="text-[0.75rem] text-yellow-400 sm:text-[1.25rem] md:text-[1.5rem]">{ampm}</span>
            {displayH}:{displayM}<span className="hidden sm:inline">:{displayS}</span>
          </div>
          </div>
        </div>
      </div>

      {/* ── 오류 배너 ────────────────────────────── */}
      {error && (
        <div className="flex shrink-0 items-center justify-between bg-red-700 px-5 py-2 text-[0.8125rem] font-bold text-white">
          <span>{error}</span>
          <button onClick={refetch} className="ml-4 inline-flex items-center gap-1 text-white hover:text-white/90"><RefreshCw className="size-3.5" />다시 시도</button>
        </div>
      )}

      {/* ── 잠시 후 도착 (3분 미만, 시간 없음) ───── */}
      {/*
        화면이 낮을 때 이 영역이 줄어들 수 있어야 합니다. 여기 있는 차량은 아래
        목록에도 다시 나오므로, 공간이 부족하면 목록을 살리는 쪽이 맞습니다.
      */}
      {showSoonPanel && <div data-testid="soon-arrivals-panel" className="hidden shrink-0 border-b border-[#C99F11] bg-[#F0C929] px-5 pb-2.5 pt-2 sm:block">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex items-baseline gap-2 text-left">
            <span className="text-[1.25rem] font-black leading-tight text-[#2C2A1A] sm:text-[1.375rem]">잠시 후 도착</span>
            <span className="text-[0.75rem] font-bold text-[#4E3F0C] sm:text-[0.8125rem]">3분 이내</span>
          </div>
          <div className="flex items-center gap-1.5">
            {lastUpdatedStr && <span className={`hidden text-[0.75rem] font-bold sm:inline ${isStale ? "text-red-700" : "text-[#78350F]"}`}>{isStale ? `정보 지연 · ${lastUpdatedStr}` : lastUpdatedStr}</span>}
            {soonTotalPages > 1 && (
              <div className="flex items-center gap-1" aria-label="곧 도착 차량 페이지 제어">
                <button type="button" onClick={() => { setAutoRotate(false); setSoonPage((page) => (page - 1 + soonTotalPages) % soonTotalPages); }} className="grid size-11 place-items-center rounded border border-[#6F611E]/40 bg-white/70 text-[#2C2A1A]" aria-label="이전 곧 도착 차량 목록"><ChevronLeft className="size-4" /></button>
                <span className="min-w-10 text-center text-sm font-black text-[#2C2A1A]" aria-live="polite">{curSoonPage + 1}/{soonTotalPages}</span>
                <button type="button" onClick={() => { setAutoRotate(false); setSoonPage((page) => (page + 1) % soonTotalPages); }} className="grid size-11 place-items-center rounded border border-[#6F611E]/40 bg-white/70 text-[#2C2A1A]" aria-label="다음 곧 도착 차량 목록"><ChevronRight className="size-4" /></button>
              </div>
            )}
          </div>
        </div>

        {loading ? (
          <div className="flex gap-1 sm:gap-2">
            {Array.from({ length: SOON_PER_PAGE }).map((_, i) => (
              <div key={i} className="min-h-[76px] flex-1 animate-pulse rounded-md border border-[#6F611E]/30 bg-[#1C2229]/35" />
            ))}
          </div>
        ) : arrivingSoon.length === 0 ? (
          <div className="rounded-md bg-black/8 py-5 text-center text-base font-bold text-[#504710]">
            3분 이내 도착 예정 버스가 없습니다
          </div>
        ) : (
          <div className="grid grid-cols-2 items-stretch gap-2 sm:grid-cols-5">
            {currentSoon.map((bus) => <SoonCard key={bus.id} bus={bus} isTracked={trackedBusId === (bus.plainNo || bus.id)} onTrack={() => toggleTracking(bus)} />)}
            {currentSoon.length < SOON_PER_PAGE && (
              <div
                className="hidden min-h-[76px] items-center justify-center gap-3 rounded-xl border border-[#6F611E]/25 bg-[#E5BE24]/55 px-5 text-[#4E4214] sm:flex"
                style={{ gridColumn: `span ${SOON_PER_PAGE - currentSoon.length}` }}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-black/10"><Radio className="size-5" /></span>
                <span className="text-left"><strong className="block text-sm font-black">실시간 도착정보 수신 중</strong><span className="text-xs font-bold text-[#4E4214]">새로운 차량이 확인되면 바로 표시됩니다.</span></span>
              </div>
            )}
          </div>
        )}
      </div>}

      {/* ── 메인 버스 목록 ───────────────────────── */}
      <div className="flex min-h-0 flex-1 flex-col bg-white">
        {/* 테이블 헤더 */}
        <div className="grid shrink-0 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] border-b border-[#374151] bg-[#1C1F26] md:grid-cols-[150px_110px_1fr]">
          {/* 큰 글씨 모드에서 "노선번호"가 "노선번 / 호"로 쪼개지면 표가 망가져
              보입니다. 열 제목은 줄바꿈하지 않고 칸에 맞춰 줄어들게 합니다. */}
          {["노선번호", "예정시간", "버스 현재 위치"].map((label, i) => (
            <div key={i} className={`overflow-hidden px-2 py-3 [container-type:inline-size] sm:px-4 ${i < 2 ? "border-r border-[#374151]" : ""}`}>
              {/* cqi 는 조상 컨테이너를 기준으로 하므로 크기는 안쪽 span 에 줍니다. */}
              <span className={`block whitespace-nowrap text-[min(0.875rem,13cqi)] font-black tracking-wider text-white ${i === 2 ? "text-left" : "text-center"}`}>{label}</span>
            </div>
          ))}
        </div>

        {/* 목록 본문 */}
        {/*
          스크롤 영역에는 키보드로 도달할 수 있어야 합니다(WCAG 2.1.1). 평소에는 안에
          있는 버스 행 버튼이 그 역할을 하지만, 도착 정보가 하나도 없을 때(외부 API 장애
          등)는 초점을 받을 요소가 없어 키보드·스크린리더 이용자가 이 영역을 스크롤할
          수 없게 됩니다. 그래서 영역 자체를 초점 대상으로 만들고 이름을 붙입니다.
        */}
        <div
          ref={mainScrollRef}
          data-testid="main-bus-scroll"
          tabIndex={0}
          role="region"
          aria-label="버스 도착 목록"
          className="flex min-h-[112px] min-w-0 flex-1 flex-col overflow-y-auto bg-[#F1F5F9] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#123E49]"
        >
          <div className="flex min-h-full min-w-0 flex-col">
            {loading
              ? Array.from({ length: mainPerPage }).map((_, i) => <SkeletonRow key={i} idx={i} />)
              : currentMain.map((bus, idx) => {
                  const congLabel = getCongestionLabel(bus.congestion);
                  const congColor = getCongestionColor(bus.congestion);
                  const isArriving = bus.status === "live" && bus.traTimeSec < SOON_ARRIVE;

                  return (
                    <button data-testid="main-bus-row" type="button" disabled={bus.status !== "live"} onClick={() => toggleTracking(bus)} aria-pressed={bus.status === "live" ? trackedBusId === (bus.plainNo || bus.id) : undefined} aria-label={describeBus(bus)} key={bus.id} className={`grid min-h-[56px] w-full min-w-0 shrink-0 grid-cols-[minmax(78px,1fr)_82px_minmax(120px,2fr)] items-center border-b border-[#E2E8F0] text-left disabled:cursor-default sm:min-h-[68px] md:grid-cols-[150px_110px_1fr]
                      ${trackedBusId === (bus.plainNo || bus.id) ? "bg-amber-50 ring-2 ring-inset ring-[#F0C929]" : idx % 2 === 0 ? "bg-white" : "bg-[#F8FAFC]"}`}>

                      {/* 노선번호 */}
                      <div className="flex h-full items-center justify-center border-r border-[#E2E8F0] px-4 [container-type:inline-size]">
                        <span
                          className="max-w-full whitespace-nowrap text-center font-black leading-tight text-[#1E293B]"
                          style={{ fontSize: busNumberFontSize(bus.busNumber, 2) }}
                          title={`${bus.busNumber}번 버스`}
                        >
                          {bus.busNumber}
                        </span>
                      </div>

                      {/* 예정시간 */}
                      <div className="flex h-full items-center justify-center border-r border-[#E2E8F0]">
                        {bus.status !== "live" ? (
                          <span className="px-1 text-center text-[0.8125rem] font-black leading-tight text-slate-500">
                            {describeArrivalStatus(bus.status)}
                          </span>
                        ) : isArriving ? (
                          <div className="flex flex-col items-center">
                            <span className="text-[1.25rem] font-black leading-tight text-red-600">곧</span>
                            <span className="text-[1.25rem] font-black leading-tight text-red-600">도착</span>
                          </div>
                        ) : (
                          <CircleTimer arrivalMin={bus.arrivalMin} />
                        )}
                      </div>

                      {/* 버스 현재 위치 */}
                      <div className="flex items-center px-4 h-full gap-3">
                        {bus.status === "live" && (
                          <div className={`border rounded-lg px-2 py-1 shrink-0 ${congColor}`}>
                            <span className="text-[0.75rem] font-black">{congLabel}</span>
                          </div>
                        )}
                        <div className="flex flex-col min-w-0">
                          {/*
                            정류장 이름은 잘라내지 않고 줄을 바꿉니다. 터치 화면에서는
                            title 툴팁을 띄울 방법이 없어, ellipsis 로 자르면 이용자가
                            "몽촌토성역대형쇼핑센터앞…" 이 어디인지 확인할 방법이
                            없어집니다. 목록 자체가 세로 스크롤되므로 행이 늘어나도
                            다른 정보가 사라지지 않습니다.
                          */}
                          <span className="break-words text-[0.875rem] font-black leading-snug text-[#1E293B] sm:text-[1.0625rem] md:text-[1.25rem]">
                            {bus.status === "live"
                              ? bus.currentStationName || "위치 확인 중"
                              : bus.arrivalMsg}
                          </span>
                          <StopsDot remaining={bus.remainingStops} />
                          <div className="mt-1 flex gap-1">
                            {bus.busType === 1 && <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[0.625rem] font-black text-sky-800">저상버스</span>}
                            {bus.isFullFlag && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[0.625rem] font-black text-red-700">만차</span>}
                          </div>
                          {bus.isLastBus && (
                            <span className="mt-0.5 text-[0.75rem] font-black text-red-600">막차</span>
                          )}
                        </div>
                      </div>

                    </button>
                  );
                })}

            {/*
              행을 그리고 남은 자리를 채웁니다. `min-h` 없이 flex-1 만 쓰므로 남는
              자리가 없으면 높이 0 이 되어 목록을 넘치게 하지 않습니다. 고정값 5와
              비교하던 예전 조건은 화면이 낮아 4행이 정원인 경우에도 안내를 덧붙여
              마지막 행을 가렸습니다.

              문구는 "이 페이지가 마지막이고 자리가 남았을 때"만 보여 줍니다. 페이지가
              꽉 찼는데 이 문구를 띄우면 뒤 페이지의 차량이 없다는 뜻이 됩니다.
            */}
            {!loading && (
              <div className="grid min-h-0 flex-1 place-items-center overflow-hidden bg-[linear-gradient(135deg,#f8fafc_25%,#f1f5f9_25%,#f1f5f9_50%,#f8fafc_50%,#f8fafc_75%,#f1f5f9_75%)] bg-[length:24px_24px] px-4 text-center">
                {currentMain.length < mainPerPage && (
                  <div className="rounded-full border border-slate-200 bg-white/95 px-4 py-2 text-xs font-bold text-slate-500 shadow-sm">
                    현재 확인된 도착 차량은 {currentMain.length}대입니다
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* 푸터 */}
        <div className="flex shrink-0 items-center justify-between border-t border-[#CBD5E1] bg-[#EDF1F3] px-3 py-2 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            {/* min-w-11: 라벨이 잘려도 아이콘이 44px 아래로 눌리지 않게 합니다. */}
            <button type="button" onClick={refetch} className={`inline-flex min-h-11 min-w-11 items-center gap-1.5 text-left text-[0.75rem] font-bold hover:text-[#1B2930] ${isStale ? "text-red-700" : "text-[#52616B]"}`} title="도착 정보 새로고침">
              <Wifi className={`size-4 shrink-0 ${isStale ? "text-red-600" : "text-emerald-600"}`} /> <span className="truncate">{isStale ? "정보 갱신 지연 · 다시 시도" : "실시간 · 15초마다 갱신"}</span>
            </button>
            {trackedBusId && <span aria-live="polite" className="inline-flex items-center gap-1 truncate text-[0.75rem] font-black text-[#145466]"><Volume2 className="size-3.5" /> {trackedBusNumber ? `${trackedBusNumber}번 ` : ""}도착 알림 중</span>}
          </div>
          <div className="flex items-center gap-1.5" aria-label="버스 목록 페이지 제어">
            {mainTotalPages > 1 && (
              <button type="button" onClick={() => { setAutoRotate(false); setMainPage((page) => (page - 1 + mainTotalPages) % mainTotalPages); }} className="grid size-11 place-items-center rounded border border-slate-300 bg-white text-slate-700" aria-label="이전 버스 목록"><ChevronLeft className="size-4" /></button>
            )}
            {(mainTotalPages > 1 || soonTotalPages > 1) && (
              <button type="button" onClick={() => setAutoRotate((enabled) => !enabled)} aria-pressed={!autoRotate} className="grid size-11 place-items-center rounded border border-slate-300 bg-white text-slate-700" aria-label={autoRotate ? "자동 페이지 넘김 중지" : "자동 페이지 넘김 시작"}>{autoRotate ? <Pause className="size-4" /> : <Play className="size-4" />}</button>
            )}
            {mainTotalPages > 1 && <span className="min-w-10 text-center text-sm font-black text-slate-700" aria-live="polite">{curMainPage + 1}/{mainTotalPages}</span>}
            {Array.from({ length: mainTotalPages }).map((_, i) => (
              <button key={i} type="button" onClick={() => { setAutoRotate(false); setMainPage(i); }} aria-label={`버스 목록 ${i + 1}페이지`} aria-current={i === curMainPage ? "page" : undefined} className="grid size-11 shrink-0 place-items-center rounded">
                <span className={`block h-2 rounded-full transition-all duration-300 ${i === curMainPage ? "w-6 bg-[#475569]" : "w-2 bg-[#CBD5E1]"}`} />
              </button>
            ))}
            {mainTotalPages > 1 && (
              <button type="button" onClick={() => { setAutoRotate(false); setMainPage((page) => (page + 1) % mainTotalPages); }} className="grid size-11 place-items-center rounded border border-slate-300 bg-white text-slate-700" aria-label="다음 버스 목록"><ChevronRight className="size-4" /></button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
