// src/types/bus.ts

export type BusCongetion = 0 | 3 | 4 | 5;

export interface BusOption {
  id: string;
  busNumber: string;
  arrivalMin: number;     // 도착 예정 분
  traTimeSec: number;     // 원본 초 단위 (곧 도착 판단용: < 60초)
  arrivalMsg: string;
  currentStationName: string;
  remainingStops: number;
  busType: number;
  congetion: BusCongetion;
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
