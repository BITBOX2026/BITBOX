import { describe, expect, it } from "vitest";
import {
  classifyArrival,
  cleanBusNumber,
  describeArrivalStatus,
  getCongestionLabel,
  normalizeVehicleId,
  parseRemainingStops,
  toBusOptions,
  toCongestion,
} from "./busService";

describe("parseRemainingStops", () => {
  it("parses common Seoul arrival message formats", () => {
    expect(parseRemainingStops("[3번째 전] 잠시후 도착")).toBe(3);
    expect(parseRemainingStops("2번째전")).toBe(2);
    expect(parseRemainingStops("1정거장 전")).toBe(1);
    expect(parseRemainingStops("곧 도착")).toBe(0);
  });

  it("returns -1 when no stop count is available", () => {
    expect(parseRemainingStops("운행 종료")).toBe(-1);
  });
});

describe("bus display values", () => {
  it("preserves Korean village-bus route names", () => {
    expect(cleanBusNumber("강동01")).toBe("강동01");
    expect(cleanBusNumber("송파02번")).toBe("송파02");
  });

  it("keeps unavailable congestion distinct from free seating", () => {
    expect(toCongestion(undefined)).toBe(0);
    expect(toCongestion("0")).toBe(0);
    expect(toCongestion("3")).toBe(3);
    expect(getCongestionLabel(0)).toBe("정보 없음");
  });
});

describe("classifyArrival", () => {
  it("keeps standby and terminal distinct from a real ETA", () => {
    expect(classifyArrival(null, "출발대기")).toBe("standby");
    expect(classifyArrival(null, "운행 종료")).toBe("terminal");
    expect(classifyArrival(null, "")).toBe("unknown");
    expect(classifyArrival(undefined, undefined)).toBe("unknown");
    expect(classifyArrival(0, "곧 도착")).toBe("live");
    expect(classifyArrival(4, "4분후[2번째 전]")).toBe("live");
  });

  it("prefers the provider reason over a present minute value", () => {
    // 제공기관이 이유를 명시하면 분 값이 있어도 그 이유가 우선입니다.
    expect(classifyArrival(0, "운행종료")).toBe("terminal");
  });

  it("describes each status in Korean for the display", () => {
    expect(describeArrivalStatus("standby")).toBe("출발 대기 중");
    expect(describeArrivalStatus("terminal")).toBe("운행 종료");
    expect(describeArrivalStatus("unknown")).toBe("도착정보 없음");
  });
});

describe("normalizeVehicleId", () => {
  it('treats the Seoul "no tracked vehicle" sentinel as absent', () => {
    // 서울 공공데이터는 추적 차량이 없으면 vehId 를 "0" 으로 보냅니다.
    // "0" 은 자바스크립트에서 truthy 라 그대로 통과하면 여러 노선이 같은 id 를 갖습니다.
    expect(normalizeVehicleId("0")).toBe("");
    expect(normalizeVehicleId("")).toBe("");
    expect(normalizeVehicleId(" ")).toBe("");
    expect(normalizeVehicleId(undefined)).toBe("");
    expect(normalizeVehicleId(null)).toBe("");
    expect(normalizeVehicleId("124031021")).toBe("124031021");
    expect(normalizeVehicleId(" 124031021 ")).toBe("124031021");
    // "0" 으로 시작하는 실제 차량번호는 유효합니다.
    expect(normalizeVehicleId("012345")).toBe("012345");
  });
});

describe("toBusOptions", () => {
  // 운영 정류장(올림픽공원역) 실데이터 형태: 9개 노선 중 8개가 vehId "0" 입니다.
  const items = [
    {
      bus_number: "3412", direction: "강동차고지 방향", first_arrival_min: 2, second_arrival_min: 9,
      message: "", raw_arrmsg1: "2분후[2번째 전]", raw_arrmsg2: "9분후[7번째 전]",
      raw_veh_id1: "124031021", raw_veh_id2: "124031131",
    },
    ...["1311B광주", "30-5하남", "3214", "3220", "3319", "3323", "3413"].map((bus_number) => ({
      bus_number, direction: "방향", first_arrival_min: null, second_arrival_min: null,
      message: "", raw_arrmsg1: "운행종료", raw_arrmsg2: "",
      raw_veh_id1: "0", raw_veh_id2: "0",
    })),
  ];

  it("gives every row a unique id so React never mixes rows up", () => {
    const buses = toBusOptions(items);
    const ids = buses.map((bus) => bus.id);
    expect(ids.length).toBeGreaterThan(1);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('never lets the "0" sentinel become a tracking id', () => {
    const buses = toBusOptions(items);
    // 추적 id 는 toggleTracking 과 같은 방식으로 계산합니다.
    const trackingIds = buses.map((bus) => bus.plainNo || bus.id);
    expect(trackingIds).not.toContain("0");
    expect(new Set(trackingIds).size).toBe(trackingIds.length);
    expect(buses.filter((bus) => bus.plainNo === "0")).toHaveLength(0);
  });

  it("keeps a real vehicle number as the tracking id", () => {
    const live = toBusOptions(items).find((bus) => bus.status === "live" && !bus.isSecond);
    expect(live?.plainNo).toBe("124031021");
  });
});
