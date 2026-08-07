import { useMemo, useState } from "react";
import { Bus, Clock3, Search, TrainFront } from "lucide-react";
import type { TransportMode } from "../../api/routeService";

const RECENT_KEY = "bitbox.recentDestinations";

function loadRecentDestinations(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string").slice(0, 3) : [];
  } catch {
    return [];
  }
}

export function DestinationSearch({
  disabled,
  onSubmit,
}: {
  disabled?: boolean;
  onSubmit: (destination: string, mode: TransportMode) => Promise<void>;
}) {
  const [destination, setDestination] = useState("");
  const [mode, setMode] = useState<TransportMode>("bus");
  const [recent, setRecent] = useState<string[]>(loadRecentDestinations);
  const trimmedDestination = useMemo(() => destination.trim(), [destination]);

  const submit = async (value = trimmedDestination) => {
    if (!value || disabled) return;
    const nextRecent = [value, ...recent.filter((item) => item !== value)].slice(0, 3);
    setRecent(nextRecent);
    localStorage.setItem(RECENT_KEY, JSON.stringify(nextRecent));
    setDestination(value);
    await onSubmit(value, mode);
  };

  return (
    <div className="w-full max-w-[520px]">
      <form
        className="flex h-12 overflow-hidden rounded-md border border-white/20 bg-white shadow-lg"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <input
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
          placeholder="목적지를 입력하세요"
          aria-label="목적지"
          className="min-w-0 flex-1 px-4 text-[15px] font-bold text-slate-900 outline-none placeholder:font-medium placeholder:text-slate-400"
          disabled={disabled}
        />
        <button
          type="submit"
          aria-label="경로 검색"
          title="경로 검색"
          disabled={!trimmedDestination || disabled}
          className="grid w-12 shrink-0 place-items-center bg-[#F0C929] text-[#17343B] disabled:cursor-not-allowed disabled:opacity-45"
        >
          <Search className="size-5" />
        </button>
      </form>

      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="flex rounded-md bg-black/20 p-1" aria-label="교통수단">
          <button
            type="button"
            title="버스 우선"
            aria-label="버스 우선"
            onClick={() => setMode("bus")}
            aria-pressed={mode === "bus"}
            className={`grid size-8 place-items-center rounded ${mode === "bus" ? "bg-white text-[#145466]" : "text-white/70"}`}
          >
            <Bus className="size-4" />
          </button>
          <button
            type="button"
            title="대중교통 전체"
            aria-label="대중교통 전체"
            onClick={() => setMode("transit")}
            aria-pressed={mode === "transit"}
            className={`grid size-8 place-items-center rounded ${mode === "transit" ? "bg-white text-[#145466]" : "text-white/70"}`}
          >
            <TrainFront className="size-4" />
          </button>
        </div>

        {recent.length > 0 && (
          <div className="flex min-w-0 items-center justify-end gap-1.5 overflow-hidden">
            <Clock3 className="size-4 shrink-0 text-white/70" />
            {recent.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  setDestination(item);
                  void submit(item);
                }}
                className="max-w-24 truncate rounded bg-white/10 px-2 py-1 text-xs font-bold text-white/85 hover:bg-white/20"
              >
                {item}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
