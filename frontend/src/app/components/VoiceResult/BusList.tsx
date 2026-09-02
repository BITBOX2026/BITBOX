import { BusFront, Clock } from "lucide-react";
import { describeArrivalStatus } from "../../../api/busService";
import { busNumberFontSize } from "../../../utils/busNumberFit";
import type { BusOption } from "../../../types/bus";

interface BusListProps {
  buses: BusOption[];
  selectedId?: string;
  onBusClick: (bus: BusOption) => void;
}

function formatArrival(bus: BusOption): string {
  // 출발대기·운행종료를 뭉뚱그려 "정보 없음"으로 보여 주면 백엔드가 안내하는
  // 이유와 화면이 어긋납니다. 상태별 문구를 그대로 씁니다.
  if (bus.status !== "live") return describeArrivalStatus(bus.status);
  if (!Number.isFinite(bus.arrivalMin) || bus.arrivalMin < 0) return "정보 없음";
  return bus.arrivalMin <= 1 ? "곧 도착" : `${bus.arrivalMin}분`;
}

export function BusList({ buses, selectedId, onBusClick }: BusListProps) {
  return (
    <aside className="custom-scrollbar h-auto w-full shrink-0 overflow-x-auto border-b border-slate-300 bg-[#EDF1F3] sm:h-full sm:w-[31%] sm:min-w-28 sm:max-w-[220px] sm:overflow-x-hidden sm:overflow-y-auto sm:border-b-0 sm:border-r">
      <div className="hidden items-center gap-2 border-b border-slate-300 bg-[#171D23] px-3 py-2 text-xs font-bold text-white/70 sm:flex">
        <BusFront className="size-4 text-[#F0C929]" /> 추천 노선
      </div>
      <div className={`flex sm:block sm:min-w-0 ${buses.length === 1 ? "w-full" : "min-w-max"}`}>
        {buses.map((bus) => {
          const isSelected = selectedId === bus.id;
          return (
            <button
              type="button"
              key={bus.id}
              onClick={() => onBusClick(bus)}
              aria-pressed={isSelected}
              className={`flex min-h-[64px] flex-col items-center justify-center border-r border-slate-300 [container-type:inline-size] px-4 py-2 text-[#171D23] transition-colors sm:min-h-[112px] sm:w-full sm:min-w-0 sm:border-b sm:border-r-0 sm:px-2 sm:py-3 ${buses.length === 1 ? "w-full" : "min-w-[112px]"} ${isSelected ? "bg-[#F0C929] shadow-[inset_0_-4px_0_#171D23] sm:shadow-[inset_4px_0_0_#171D23]" : "bg-white hover:bg-slate-50"}`}
            >
              <span
                title={`${bus.busNumber}번 버스`}
                className="max-w-full whitespace-nowrap text-center font-mono font-black leading-tight"
                style={{ fontSize: busNumberFontSize(bus.busNumber, 1.875) }}
              >
                {bus.busNumber}
              </span>
              <span className="mt-0.5 flex items-center gap-1 whitespace-nowrap text-xs font-black sm:mt-1 sm:text-base">
                <Clock className="size-3.5 sm:size-4" /> {formatArrival(bus)}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
