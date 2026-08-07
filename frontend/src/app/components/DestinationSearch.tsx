import { useEffect, useMemo, useState } from "react";
import { BusFront, Clock3, LoaderCircle, MapPin, Search } from "lucide-react";
import { suggestPlaces, type PlaceSuggestion } from "../../api/client";

const RECENT_KEY = "bitbox.recentDestinations";

function loadRecentDestinations(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string").slice(0, 3) : [];
  } catch {
    return [];
  }
}

interface DestinationSearchProps {
  disabled?: boolean;
  onSubmit: (destination: string) => Promise<void>;
}

export function DestinationSearch({ disabled, onSubmit }: DestinationSearchProps) {
  const [destination, setDestination] = useState("");
  const [recent, setRecent] = useState<string[]>(loadRecentDestinations);
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isFocused, setIsFocused] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const trimmedDestination = useMemo(() => destination.trim(), [destination]);

  useEffect(() => {
    if (trimmedDestination.length < 2) {
      setSuggestions([]);
      setIsSuggesting(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setIsSuggesting(true);
      try {
        setSuggestions(await suggestPlaces(trimmedDestination, controller.signal));
      } catch {
        if (!controller.signal.aborted) setSuggestions([]);
      } finally {
        if (!controller.signal.aborted) setIsSuggesting(false);
      }
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [trimmedDestination]);

  const submit = async (value = trimmedDestination) => {
    const normalized = value.trim();
    if (!normalized || disabled) return;
    const nextRecent = [normalized, ...recent.filter((item) => item !== normalized)].slice(0, 3);
    setRecent(nextRecent);
    localStorage.setItem(RECENT_KEY, JSON.stringify(nextRecent));
    setDestination(normalized);
    setSuggestions([]);
    setIsFocused(false);
    await onSubmit(normalized);
  };

  return (
    <div className="w-full max-w-[520px]">
      <div className="relative">
        <form className="flex h-12 overflow-hidden rounded-md border border-white/20 bg-white shadow-lg" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <input
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => window.setTimeout(() => setIsFocused(false), 120)}
            placeholder="버스로 갈 목적지를 입력하세요"
            aria-label="버스 목적지"
            aria-autocomplete="list"
            aria-expanded={isFocused && suggestions.length > 0}
            className="min-w-0 flex-1 px-4 text-[15px] font-bold text-slate-900 outline-none placeholder:font-medium placeholder:text-slate-400"
            disabled={disabled}
          />
          <button type="submit" aria-label="버스 경로 검색" title="버스 경로 검색" disabled={!trimmedDestination || disabled} className="grid w-12 shrink-0 place-items-center bg-[#F0C929] text-[#17343B] disabled:cursor-not-allowed disabled:opacity-45">
            {isSuggesting ? <LoaderCircle className="size-5 animate-spin" /> : <Search className="size-5" />}
          </button>
        </form>

        {isFocused && suggestions.length > 0 && (
          <div role="listbox" className="absolute inset-x-0 top-[52px] z-50 max-h-44 overflow-y-auto rounded-md border border-slate-200 bg-white py-1 text-slate-900 shadow-xl">
            {suggestions.map((suggestion) => (
              <button
                key={`${suggestion.name}-${suggestion.address}`}
                type="button"
                role="option"
                aria-selected={false}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  setDestination(suggestion.name);
                  setSuggestions([]);
                  setIsFocused(false);
                }}
                className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-slate-100"
              >
                <MapPin className="mt-0.5 size-4 shrink-0 text-[#145466]" />
                <span className="min-w-0"><strong className="block truncate text-sm">{suggestion.name}</strong><span className="block truncate text-xs text-slate-500">{suggestion.address}</span></span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 rounded bg-black/20 px-2 py-1 text-xs font-bold text-white/80"><BusFront className="size-4 text-[#F0C929]" /> 버스 전용</span>
        {recent.length > 0 && (
          <div className="flex min-w-0 items-center justify-end gap-1.5 overflow-hidden">
            <Clock3 className="size-4 shrink-0 text-white/70" />
            {recent.map((item) => <button key={item} type="button" onClick={() => { setDestination(item); void submit(item); }} className="max-w-24 truncate rounded bg-white/10 px-2 py-1 text-xs font-bold text-white/85 hover:bg-white/20">{item}</button>)}
          </div>
        )}
      </div>
    </div>
  );
}
