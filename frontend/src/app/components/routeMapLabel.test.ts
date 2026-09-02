import { describe, expect, it } from "vitest";
import { pathMidpoint } from "./VoiceResult/RouteDetail";

describe("지도 노선 라벨 위치", () => {
  it("경유 정류장이 없는 두 점 구간은 실제 중점에 붙인다", () => {
    // 회귀: path[Math.floor(2 / 2)] 는 도착점이라 라벨이 구간 끝에 붙었습니다.
    // ODsay 가 passStopList 를 주지 않은 버스 구간은 좌표가 정확히 두 개입니다.
    expect(pathMidpoint([
      { lat: 37.500, lng: 127.000 },
      { lat: 37.600, lng: 127.200 },
    ])).toEqual({ lat: 37.550, lng: 127.100 });
  });

  it("점이 홀수 개면 가운데 점을 그대로 쓴다", () => {
    expect(pathMidpoint([
      { lat: 37.5, lng: 127.0 },
      { lat: 37.7, lng: 127.4 },
      { lat: 37.9, lng: 127.8 },
    ])).toEqual({ lat: 37.7, lng: 127.4 });
  });

  it("점이 짝수 개면 가운데 두 점의 평균을 쓴다", () => {
    expect(pathMidpoint([
      { lat: 0, lng: 0 },
      { lat: 2, lng: 4 },
      { lat: 4, lng: 8 },
      { lat: 6, lng: 12 },
    ])).toEqual({ lat: 3, lng: 6 });
  });

  it("라벨이 구간의 끝 좌표에 놓이지 않는다", () => {
    const path = [
      { lat: 37.514, lng: 127.119 },
      { lat: 37.499, lng: 127.029 },
    ];
    const midpoint = pathMidpoint(path);
    expect(midpoint).not.toEqual(path[0]);
    expect(midpoint).not.toEqual(path[path.length - 1]);
  });
});
