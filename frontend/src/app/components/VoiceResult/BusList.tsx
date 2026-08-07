import { Clock } from "lucide-react";
import { BusOption } from "../../../types/bus";

export function BusList({ buses, selectedId, onBusClick }: {
    buses: BusOption[];
    selectedId?: string;
    onBusClick: (bus: BusOption) => void;
}) {
    const formatArrival = (arrivalMin: any) => {
        if (arrivalMin === undefined || arrivalMin === null) return "정보 없음";

        // 혹시 'NaN' 데이터가 넘어왔다면 안전하게 "곧 도착"으로 표시
        if (Number.isNaN(arrivalMin) || arrivalMin === "NaN") {
            return "곧 도착";
        }

        // 이미 숫자이거나 숫자로 변환 가능한 경우
        const num = typeof arrivalMin === "number" ? arrivalMin : parseInt(String(arrivalMin), 10);

        // "출발대기" 같이 숫자로 변환되지 않는 문자열인 경우 원본 그대로 반환
        if (isNaN(num)) {
            return String(arrivalMin);
        }

        return num <= 1 ? "곧 도착" : `${num}분`;
    };
    return (
        
        // 전체 너비의 30%를 차지하며, 초과 시 스크롤 구현
        <div className="w-[30%] h-full border-r border-black overflow-y-auto custom-scrollbar bg-blue shrink-0">
            {buses.map((bus) => {
                // 현재 이 버스가 선택된 상태인지 확인
                const isSelected = selectedId === bus.id;
                return (
                    <button
                        key={bus.id}
                        onClick={() => onBusClick(bus)}
                        // 선택된 버스는 노란색 배경에 검은 글자, 미선택된 버스는 흰색 배경에 검은 글자
                        className={`w-full flex flex-col items-center justify-center py-8 px-4 border-b border-black transition-all ${
                            isSelected ? "bg-[#F0E442] text-[#000000]" : "bg-white text-[#000000]"
                        }`} >
                        {/* 버스 번호 */}
                        <span className="text-5xl font-black font-mono mb-2">{bus.busNumber}</span>
                        <div className="flex items-center gap-1">
                            <Clock className="w-5 h-5" />
                            <span className="text-2xl font-black font-mono whitespace-nowrap">
                                {formatArrival(bus.arrivalMin)}
                            </span>
                        </div>
                    </button>
                );
            })}
        </div>
    );
}