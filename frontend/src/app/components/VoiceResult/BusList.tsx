import { BusFront, Clock } from "lucide-react";
import type { BusOption } from "../../../types/bus";

interface BusListProps {
  buses: BusOption[];
  selectedId?: string;
  onBusClick: (bus: BusOption) => void;
}

function formatArrival(value: number): string {
  if (!Number.isFinite(value)) return "정보 없음";
  return value <= 1 ? "곧 도착" : `${value}분`;
}

export function BusList({ buses, selectedId, onBusClick }: BusListProps) {
  return (
    <aside className="custom-scrollbar h-full w-[31%] min-w-24 max-w-[210px] shrink-0 overflow-y-auto border-r border-slate-300 bg-[#EDF1F3]">
      <div className="flex items-center gap-2 border-b border-slate-300 bg-[#171D23] px-3 py-2 text-xs font-bold text-white/70">
        <BusFront className="size-4 text-[#F0C929]" /> 추천 노선
      </div>
      {buses.map((bus) => {
        const isSelected = selectedId === bus.id;
        return (
          <button
            type="button"
            key={bus.id}
            onClick={() => onBusClick(bus)}
            aria-pressed={isSelected}
            className={`flex min-h-[92px] w-full flex-col items-center justify-center border-b border-slate-300 px-2 py-3 text-[#171D23] transition-colors sm:min-h-[112px] ${isSelected ? "bg-[#F0C929]" : "bg-white hover:bg-slate-50"}`}
          >
            <span className="max-w-full truncate font-mono text-2xl font-black sm:text-3xl">{bus.busNumber}</span>
            <span className="mt-1 flex items-center gap-1 whitespace-nowrap text-sm font-black sm:text-base">
              <Clock className="size-4" /> {formatArrival(bus.arrivalMin)}
            </span>
          </button>
        );
      })}
    </aside>
  );
}
