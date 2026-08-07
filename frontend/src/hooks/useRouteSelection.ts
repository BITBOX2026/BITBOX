// VoiceResult 결과 창 UI 비즈니스 로직 구현

import { useState, useEffect } from "react";
import { BusOption, RouteDetail } from "../types/bus";

export function useRouteSelection(destination: string, buses: BusOption[]) {
  const [selectedBus, setSelectedBus] = useState<BusOption | null>(null);
  const [routeDetail, setRouteDetail] = useState<RouteDetail | null>(null);
  const [loading, setLoading] = useState(false);

  // 사용자가 버스 번호를 선택했을 때 해당 버스의 상세 경로 데이터 출력
  const handleBusClick = (bus: BusOption) => {
    setSelectedBus(bus);    // 선택된 버스 업데이트
    setLoading(true);       // 로딩 시작
    
    // 백엔드 파이프라인(ODsay + 공공데이터) 실물 데이터를 직접 바인딩합니다.
    if (bus) {
      setRouteDetail({
        busNumber: bus.busNumber,
        // odsay_service.py에서 계산되어 백엔드가 넘겨준 전체 소요 시간 (데이터가 없으면 기본값 25분)
        totalMin: (bus as any).totalMin || 25, 
        // odsay_service.py 기반으로 response_builder.py가 조립한 단계별 상세 이동 경로 배열
        steps: (bus as any).steps || []
      });
    }
    setLoading(false);
  };

  // 컴포넌트가 처음 켜지거나 버스 목록이 바뀔 때 첫 번째 버스를 자동 선택
  useEffect(() => {
    if (buses.length > 0 && !selectedBus) handleBusClick(buses[0]);
  }, [buses]);

  return { selectedBus, routeDetail, loading, handleBusClick };
}