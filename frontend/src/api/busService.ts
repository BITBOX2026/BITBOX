import type { BusOption, BusArrivalStatus, BusCongestion } from "../types/bus";
import { apiFetch, parseApiResponse } from "./client";

export interface DefaultBackendItem {
  bus_number: string;
  direction: string;
  first_arrival_min?: number | null;
  second_arrival_min?: number | null;
  message: string;
  raw_arrmsg1?: string | null;
  raw_arrmsg2?: string | null;
  raw_congestion1?: string | null;
  raw_congestion2?: string | null;
  raw_is_last1?: string | null;
  raw_is_last2?: string | null;
  raw_bus_type1?: string | null;
  raw_bus_type2?: string | null;
  raw_is_full_flag1?: string | null;
  raw_is_full_flag2?: string | null;
  raw_station_nm1?: string | null;
  raw_station_nm2?: string | null;
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
 * 서울 공공데이터는 추적 중인 차량이 없을 때 vehId 를 문자열 "0" 으로 보냅니다.
 * 자바스크립트에서 "0" 은 truthy 라 `raw_veh_id1 || fallback` 이 그대로 통과시켜,
 * 도착 예정이 없는 노선 여러 개가 전부 같은 id("0")를 갖게 됩니다. 그러면 React
 * 가 행 사이에서 상태를 섞고, 추적 대상 조회도 엉뚱한 노선을 먼저 집습니다.
 */
export function normalizeVehicleId(raw?: string | null): string {
  const value = (raw ?? "").trim();
  return value && value !== "0" ? value : "";
}

export function toCongestion(val?: string | null): BusCongestion {
  const n = Number.parseInt(val ?? "", 10);
  if (n === 3) return 3;
  if (n === 4) return 4;
  if (n === 5) return 5;
  return 0;
}

export function parseRemainingStops(arrmsg?: string | null): number {
  if (!arrmsg) return -1;
  if (arrmsg.includes("곧 도착")) return 0;
  const match = arrmsg.match(/(?:\[)?(\d+)\s*(?:번째|정거장)\s*전(?:\])?/);
  return match ? parseInt(match[1], 10) : -1;
}

export function cleanBusNumber(name: string): string {
  return name.trim().replace(/\s*번$/, "");
}

/**
 * 도착 상태를 판정합니다.
 *
 * 서울 공공데이터는 도착 시각을 계산할 수 없는 경우에도 `arrmsg` 로 이유를
 * 알려 줍니다("출발대기", "운행종료"). 백엔드는 이때 `first_arrival_min` 을
 * 비워 보내므로, 예전에는 프론트가 그 행을 통째로 버려서 이용자가 노선 자체를
 * 볼 수 없었습니다. 이제는 상태를 판정해 행을 남기고 이유를 표시합니다.
 */
export function classifyArrival(
  minutes: number | null | undefined,
  arrivalMessage?: string | null,
): BusArrivalStatus {
  const compact = (arrivalMessage || "").replace(/\s+/g, "");
  if (compact.includes("운행종료")) return "terminal";
  if (compact.includes("출발대기")) return "standby";
  if (minutes != null && minutes >= 0) return "live";
  return "unknown";
}

export function describeArrivalStatus(status: BusArrivalStatus): string {
  if (status === "standby") return "출발 대기 중";
  if (status === "terminal") return "운행 종료";
  return "도착정보 없음";
}

export async function getDefaultArrivals(): Promise<{ stationName: string; buses: BusOption[] }> {
  const res = await apiFetch("/api/bus/default", { signal: AbortSignal.timeout(5000) });
  const data = await parseApiResponse<DefaultApiResponse>(res, "버스 도착 정보를 불러오지 못했습니다.");
  if (!data.success) throw new Error(data.message || "기본 버스 정보를 가져오는데 실패했습니다.");

  return { stationName: data.station_name || "정류장", buses: toBusOptions(data.items || []) };
}

/** 백엔드 도착정보를 화면용 행 목록으로 변환합니다. 각 행의 id 는 고유해야 합니다. */
export function toBusOptions(items: DefaultBackendItem[]): BusOption[] {
  const result: BusOption[] = [];

  items.forEach((item) => {
    const cleanNum = cleanBusNumber(item.bus_number);
    const firstStatus = classifyArrival(item.first_arrival_min, item.raw_arrmsg1);

    if (firstStatus === "live") {
      result.push({
        id: normalizeVehicleId(item.raw_veh_id1) || `${item.bus_number}-1`,
        busNumber: cleanNum,
        status: "live",
        arrivalMin: item.first_arrival_min as number,
        traTimeSec: (item.first_arrival_min as number) * 60,
        arrivalMsg: item.raw_arrmsg1 || `${item.first_arrival_min}분 후 도착`,
        currentStationName: item.raw_station_nm1?.trim() || "",
        remainingStops: parseRemainingStops(item.raw_arrmsg1),
        busType: parseInt(item.raw_bus_type1 || "0", 10),
        congestion: toCongestion(item.raw_congestion1),
        isFullFlag: item.raw_is_full_flag1 === "1",
        isLastBus: item.raw_is_last1 === "1",
        plainNo: normalizeVehicleId(item.raw_veh_id1),
        isSecond: false,
      });
    } else {
      // 도착 시각이 없는 노선도 이유와 함께 남깁니다. 행을 지워 버리면 이용자가
      // "운행이 끝난 것"인지 "화면이 고장난 것"인지 구분할 수 없습니다.
      result.push({
        id: normalizeVehicleId(item.raw_veh_id1) || `${item.bus_number}-status`,
        busNumber: cleanNum,
        status: firstStatus,
        arrivalMin: -1,
        traTimeSec: -1,
        arrivalMsg: item.raw_arrmsg1?.trim() || describeArrivalStatus(firstStatus),
        currentStationName: item.raw_station_nm1?.trim() || "",
        remainingStops: -1,
        busType: parseInt(item.raw_bus_type1 || "0", 10),
        congestion: toCongestion(item.raw_congestion1),
        isFullFlag: false,
        isLastBus: item.raw_is_last1 === "1",
        plainNo: normalizeVehicleId(item.raw_veh_id1),
        isSecond: false,
      });
    }

    if (classifyArrival(item.second_arrival_min, item.raw_arrmsg2) === "live") {
      result.push({
        id: normalizeVehicleId(item.raw_veh_id2) || `${item.bus_number}-2`,
        busNumber: cleanNum,
        status: "live",
        arrivalMin: item.second_arrival_min as number,
        traTimeSec: (item.second_arrival_min as number) * 60,
        arrivalMsg: item.raw_arrmsg2 || `${item.second_arrival_min}분 후 도착`,
        currentStationName: item.raw_station_nm2?.trim() || "",
        remainingStops: parseRemainingStops(item.raw_arrmsg2),
        busType: parseInt(item.raw_bus_type2 || "0", 10),
        congestion: toCongestion(item.raw_congestion2),
        isFullFlag: item.raw_is_full_flag2 === "1",
        isLastBus: item.raw_is_last2 === "1",
        plainNo: normalizeVehicleId(item.raw_veh_id2),
        isSecond: true,
      });
    }
  });

  // 실시간 도착 차량을 빠른 순으로 먼저, 상태 행은 뒤로 보냅니다.
  const sortedBuses = result.sort((a, b) => {
    if (a.status !== b.status) {
      if (a.status === "live") return -1;
      if (b.status === "live") return 1;
    }
    return a.arrivalMin - b.arrivalMin;
  });

  // 현재 위치를 모른다고 해서 오는 버스를 감추지는 않습니다. 서울 공공데이터는
  // 노선에 따라 stationNm 을 비워 보내기도 하는데, 그때 행을 지워 버리면 실제로
  // 도착하는 버스가 전광판에서 조용히 사라져 이용자가 놓칩니다. 위치는 화면에서
  // "위치 확인 중"으로 표시하고, 도착 시간은 그대로 안내합니다.
  return sortedBuses;
}

export function getCongestionLabel(c: BusCongestion): string {
  return ({ 0: "정보 없음", 3: "여유", 4: "보통", 5: "혼잡" } as Record<BusCongestion, string>)[c];
}

export function getCongestionColor(c: BusCongestion): string {
  return ({
    0: "text-slate-700 bg-slate-100 border-slate-300",
    3: "text-[#065F46] bg-[#D1FAE5] border-[#34D399]",
    4: "text-[#92400E] bg-[#FEF3C7] border-[#F59E0B]",
    5: "text-[#991B1B] bg-[#FEE2E2] border-[#F87171]",
  } as Record<BusCongestion, string>)[c];
}
