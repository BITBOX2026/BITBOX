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
}