import type { BusOption, BusCongetion } from "../types/bus";
import { apiFetch } from "./client";

// ─── 기본 전광판(/api/bus/default) 전용 인터페이스 ───
interface DefaultBackendItem {
  bus_number: string;
  direction: string;
  first_arrival_min: number;
  second_arrival_min: number;
  message: string;
  raw_arrmsg1: string;
  raw_arrmsg2: string;
  raw_congestion1: string;
  raw_congestion2: string;
  raw_is_last1: string;
  raw_is_last2: string;
  raw_bus_type1: string;
  raw_bus_type2: string;
  raw_is_full_flag1: string;
  raw_is_full_flag2: string;
  raw_station_nm1: string;
  raw_station_nm2: string;
  raw_veh_id1?: string;
  raw_veh_id2?: string;
}

interface DefaultApiResponse {
  success: boolean;
  station_name: string;
  station_id: string;
  items: DefaultBackendItem[];
  message: string;
}

/**
 * 혼잡도 수치 변환 헬퍼 함수
 */
function toCongestion(val: string): BusCongetion {
  const n = parseInt(val, 10);
  if (n === 4) return 4;
  if (n === 5) return 5;
  return 3;
}

/**
 * 문자열에서 남은 정류장 수 파싱
 */
export function parseRemainingStops(arrmsg: string): number {
  if (!arrmsg) return -1;
  if (arrmsg.includes("곧 도착")) return 0;
  const match = arrmsg.match(/(?:\[)?(\d+)\s*(?:번째|정거장)\s*전(?:\])?/);
  return match ? parseInt(match[1], 10) : -1;
}

/**
 * 경기 버스 노선 번호 뒤의 한글 지역명 제거 정규식
 */
function cleanBusNumber(name: string): string {
  if (!name) return "";
  return name.replace(/[가-힣]/g, "").trim();
}

/**
 * 📺 메인 화면 상시 표시 기본 버스 정보 조회 (Default 전용)
 */
export async function getDefaultArrivals(): Promise<{ stationName: string; buses: BusOption[] }> {
  const res = await apiFetch("/api/bus/default", { signal: AbortSignal.timeout(5000) });
  if (!res.ok) throw new Error(`HTTP 오류: ${res.status}`);

  const data: DefaultApiResponse = await res.json();
  if (!data.success) throw new Error(data.message || "기본 버스 정보를 가져오는데 실패했습니다.");

  const stationName = data.station_name || "정류장";
  const items = data.items || [];
  const result: BusOption[] = [];

  items.forEach((item) => {
    const cleanNum = cleanBusNumber(item.bus_number);

    // 1번째 도착 예정 버스 객체화
    if (item.first_arrival_min >= 0) {
      result.push({
        id: item.raw_veh_id1 || `${item.bus_number}-1`,
        busNumber: cleanNum, 
        arrivalMin: item.first_arrival_min,
        traTimeSec: item.first_arrival_min * 60, 
        arrivalMsg: item.raw_arrmsg1 || `${item.first_arrival_min}분 후 도착`,
        currentStationName: item.raw_station_nm1?.trim() || "",
        remainingStops: parseRemainingStops(item.raw_arrmsg1),
        busType: parseInt(item.raw_bus_type1 || "0", 10),
        congetion: toCongestion(item.raw_congestion1),
        isFullFlag: item.raw_is_full_flag1 === "1",
        isLastBus: item.raw_is_last1 === "1",
        plainNo: item.raw_veh_id1 || "",
        isSecond: false,
      });
    }

    // 2번째 도착 예정 버스 객체화
    if (item.second_arrival_min >= 0) {
      result.push({
        id: item.raw_veh_id2 || `${item.bus_number}-2`,
        busNumber: cleanNum, 
        arrivalMin: item.second_arrival_min,
        traTimeSec: item.second_arrival_min * 60,
        arrivalMsg: item.raw_arrmsg2 || `${item.second_arrival_min}분 후 도착`,
        currentStationName: item.raw_station_nm2?.trim() || "",
        remainingStops: parseRemainingStops(item.raw_arrmsg2),
        busType: parseInt(item.raw_bus_type2 || "0", 10),
        congetion: toCongestion(item.raw_congestion2),
        isFullFlag: item.raw_is_full_flag2 === "1",
        isLastBus: item.raw_is_last2 === "1",
        plainNo: item.raw_veh_id2 || "",
        isSecond: true,
      });
    }
  });

  // 1. 남은 시간순 오름차순 정렬
  const sortedBuses = result.sort((a, b) => a.arrivalMin - b.arrivalMin);

  // 2. [필터링] 현재 위치 명칭(currentStationName)이 유실된 불완전 버스 데이터 전격 제거
  const withLocationBuses = sortedBuses.filter((bus) => bus.currentStationName !== "");

  return {
    stationName,
    buses: withLocationBuses,
  };
}

/**
 * UI 뱃지용 혼잡도 라벨/컬러 매핑 헬퍼 함수들
 */
export function getCongestionLabel(c: BusCongetion): string {
  return ({ 3: "여유", 4: "보통", 5: "혼잡" } as Record<number, string>)[c] ?? "여유";
}

export function getCongestionColor(c: BusCongetion): string {
  return ({
    3: "text-[#065F46] bg-[#D1FAE5] border-[#34D399]",
    4: "text-[#92400E] bg-[#FEF3C7] border-[#F59E0B]",
    5: "text-[#991B1B] bg-[#FEE2E2] border-[#F87171]",
  } as Record<number, string>)[c] ?? "text-[#065F46] bg-[#D1FAE5] border-[#34D399]";
}
