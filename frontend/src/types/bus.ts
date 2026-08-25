// src/types/bus.ts

export type BusCongestion = 0 | 3 | 4 | 5;

/**
 * 도착 상태 — 백엔드 `BusArrivalStatus` 와 같은 낱말을 사용합니다.
 *
 * live     실시간 도착 예정 시간이 있음 (arrivalMin / traTimeSec 유효)
 * standby  차고지 출발대기 — 아직 출발 전이라 도착 시각을 계산할 수 없음
 * terminal 오늘 운행 종료
 * unknown  제공기관이 도착정보를 주지 않음
 *
 * `live` 가 아닌 행은 arrivalMin / traTimeSec 이 -1 이므로 시간 비교
 * (`traTimeSec < 60` 같은)에 절대 그대로 넣으면 안 됩니다. 넣으면 음수가
 * 임계값보다 작아 "곧 도착"으로 잘못 표시됩니다.
 */
export type BusArrivalStatus = "live" | "standby" | "terminal" | "unknown";

export interface BusOption {
  id: string;
  busNumber: string;
  status: BusArrivalStatus;
  arrivalMin: number;     // 도착 예정 분 (status !== "live" 이면 -1)
  traTimeSec: number;     // 원본 초 단위 (곧 도착 판단용: < 60초), status !== "live" 이면 -1
  arrivalMsg: string;
  currentStationName: string;
  remainingStops: number;
  busType: number;
  congestion: BusCongestion;
  isFullFlag: boolean;
  isLastBus: boolean;
  plainNo: string;
  isSecond: boolean;
  totalMin?: number;
  steps?: RouteStep[];
  routeDetail?: RouteDetail;
}

export interface RouteStep {
  type: "walk" | "bus";
  durationMin: number;
  description?: string;
  fromStop?: string;
  toStop?: string;
  busNumber?: string;
}

export interface RouteDetail {
  busNumber: string;
  totalMin: number;
  steps: RouteStep[];
  origin?: string;
  origin_x?: number | string | null;
  origin_y?: number | string | null;
  destination_x?: number | string | null;
  destination_y?: number | string | null;
  route_segments?: RouteSegment[];
}

export interface RouteSegment {
  vehicle_type: string;
  line: string;
  start_name: string;
  end_name: string;
  time_min?: number | null;
  start_x?: number | null;
  start_y?: number | null;
  end_x?: number | null;
  end_y?: number | null;
  path_points?: Array<{ x: number; y: number }> | null;
}
