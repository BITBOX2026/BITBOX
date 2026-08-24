import type { BusOption, BusCongestion } from "../types/bus";
import { apiFetch, parseApiResponse } from "./client";

interface DefaultBackendItem {
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

export async function getDefaultArrivals(): Promise<{ stationName: string; buses: BusOption[] }> {
  const res = await apiFetch("/api/bus/default", { signal: AbortSignal.timeout(5000) });
  const data = await parseApiResponse<DefaultApiResponse>(res, "버스 도착 정보를 불러오지 못했습니다.");
  if (!data.success) throw new Error(data.message || "기본 버스 정보를 가져오는데 실패했습니다.");

  const stationName = data.station_name || "정류장";
  const items = data.items || [];
  const result: BusOption[] = [];

  items.forEach((item) => {
    const cleanNum = cleanBusNumber(item.bus_number);

    if (item.first_arrival_min != null && item.first_arrival_min >= 0) {
      result.push({
        id: item.raw_veh_id1 || `${item.bus_number}-1`,
        busNumber: cleanNum, 
        arrivalMin: item.first_arrival_min,
        traTimeSec: item.first_arrival_min * 60, 
        arrivalMsg: item.raw_arrmsg1 || `${item.first_arrival_min}분 후 도착`,
        currentStationName: item.raw_station_nm1?.trim() || "",
        remainingStops: parseRemainingStops(item.raw_arrmsg1),
        busType: parseInt(item.raw_bus_type1 || "0", 10),
        congestion: toCongestion(item.raw_congestion1),
        isFullFlag: item.raw_is_full_flag1 === "1",
        isLastBus: item.raw_is_last1 === "1",
        plainNo: item.raw_veh_id1 || "",
        isSecond: false,
      });
    }

    if (item.second_arrival_min != null && item.second_arrival_min >= 0) {
      result.push({
        id: item.raw_veh_id2 || `${item.bus_number}-2`,
        busNumber: cleanNum, 
        arrivalMin: item.second_arrival_min,
        traTimeSec: item.second_arrival_min * 60,
        arrivalMsg: item.raw_arrmsg2 || `${item.second_arrival_min}분 후 도착`,
        currentStationName: item.raw_station_nm2?.trim() || "",
        remainingStops: parseRemainingStops(item.raw_arrmsg2),
        busType: parseInt(item.raw_bus_type2 || "0", 10),
        congestion: toCongestion(item.raw_congestion2),
        isFullFlag: item.raw_is_full_flag2 === "1",
        isLastBus: item.raw_is_last2 === "1",
        plainNo: item.raw_veh_id2 || "",
        isSecond: true,
      });
    }
  });

  const sortedBuses = result.sort((a, b) => a.arrivalMin - b.arrivalMin);
  const withLocationBuses = sortedBuses.filter((bus) => bus.currentStationName !== "");

  return {
    stationName,
    buses: withLocationBuses,
  };
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
