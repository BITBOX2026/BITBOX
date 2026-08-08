import { useEffect, useMemo, useState } from "react";
import { BusFront, Clock3, LoaderCircle, MapPin, Search } from "lucide-react";
import { suggestPlaces, type PlaceSuggestion, type RouteDestination } from "../../api/client";

const RECENT_KEY = "bitbox.recentDestinations";

function loadRecentDestinations(): RouteDestination[] {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    if (!Array.isArray(value)) return [];
    return value.flatMap((item): RouteDestination[] => {
      if (typeof item === "string" && item.trim()) return [{ name: item.trim() }];
      if (item && typeof item === "object" && typeof item.name === "string" && item.name.trim()) {
        const x = item.x == null ? null : Number(item.x);
        const y = item.y == null ? null : Number(item.y);
        return [{
          name: item.name.trim(),
          address: typeof item.address === "string" ? item.address : null,
          x: Number.isFinite(x) ? x : null,
          y: Number.isFinite(y) ? y : null,
        }];
      }
      return [];
    }).slice(0, 3);
  } catch {
    return [];
  }
}

interface DestinationSearchProps {
  disabled?: boolean;
  onSubmit: (destination: RouteDestination) => Promise<void>;
}

export function DestinationSearch({ disabled, onSubmit }: DestinationSearchProps) {
  const [destination, setDestination] = useState("");
  const [recent, setRecent] = useState<RouteDestination[]>(loadRecentDestinations);
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isFocused, setIsFocused] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [selectedDestination, setSelectedDestination] = useState<RouteDestination | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const trimmedDestination = useMemo(() => destination.trim(), [destination]);

  useEffect(() => {
    const clearRecent = () => setRecent([]);
    window.addEventListener("bitbox:recent-cleared", clearRecent);
    return () => window.removeEventListener("bitbox:recent-cleared", clearRecent);
  }, []);

  useEffect(() => {
    if (trimmedDestination.length < 2 || selectedDestination?.name === trimmedDestination) {
      setSuggestions([]);
      setIsSuggesting(false);
      setSuggestionError("");
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setIsSuggesting(true);
      setSuggestionError("");
      try {
        setSuggestions(await suggestPlaces(trimmedDestination, controller.signal));
        setActiveIndex(-1);
      } catch (error) {
        if (!controller.signal.aborted) {
          setSuggestions([]);
          setSuggestionError(error instanceof Error ? error.message : "장소 후보를 불러오지 못했습니다.");
        }
      } finally {
        if (!controller.signal.aborted) setIsSuggesting(false);
      }
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [selectedDestination, trimmedDestination]);

  const submit = async (value: string | RouteDestination = selectedDestination ?? trimmedDestination) => {
    const routeDestination = typeof value === "string" ? { name: value } : value;
    const normalized = routeDestination.name.trim();
    if (!normalized || disabled) return;
    const normalizedDestination = { ...routeDestination, name: normalized };
    const nextRecent = [normalizedDestination, ...recent.filter((item) => item.name !== normalized)].slice(0, 3);
    setRecent(nextRecent);
    localStorage.setItem(RECENT_KEY, JSON.stringify(nextRecent));
    setDestination(normalized);
    setSuggestions([]);
    setIsFocused(false);
    await onSubmit(normalizedDestination);
  };

  const selectSuggestion = (suggestion: PlaceSuggestion) => {
    const x = suggestion.x == null ? null : Number(suggestion.x);
    const y = suggestion.y == null ? null : Number(suggestion.y);
    const selected = {
      name: suggestion.name,
      address: suggestion.address,
      x: Number.isFinite(x) ? x : null,
      y: Number.isFinite(y) ? y : null,
    };
    setDestination(selected.name);
    setSelectedDestination(selected);
    setSuggestions([]);
    setActiveIndex(-1);
    setIsFocused(false);
  };

  return (
    <div className="w-full max-w-[520px]">
      <div className="relative">
        <form className="flex h-12 overflow-hidden rounded-md border border-white/20 bg-white shadow-lg" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <input
            value={destination}
            onChange={(event) => { setDestination(event.target.value); setSelectedDestination(null); }}
            onFocus={() => setIsFocused(true)}
            onBlur={() => window.setTimeout(() => setIsFocused(false), 120)}
            placeholder="목적지를 입력하세요"
            aria-label="버스 목적지"
            aria-autocomplete="list"
            aria-expanded={isFocused && suggestions.length > 0}
            aria-controls="destination-suggestions"
            aria-activedescendant={activeIndex >= 0 ? `destination-option-${activeIndex}` : undefined}
            onKeyDown={(event) => {
              if (!suggestions.length) return;
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((index) => (index + 1) % suggestions.length);
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1));
              } else if (event.key === "Enter" && activeIndex >= 0) {
                event.preventDefault();
                selectSuggestion(suggestions[activeIndex]);
              } else if (event.key === "Escape") {
                setSuggestions([]);
              }
            }}
            className="min-w-0 flex-1 px-4 text-[15px] font-bold text-slate-900 outline-none placeholder:font-medium placeholder:text-slate-400"
            disabled={disabled}
          />
          <button type="submit" aria-label="버스 경로 검색" title="버스 경로 검색" disabled={!trimmedDestination || disabled} className="grid w-12 shrink-0 place-items-center bg-[#F0C929] text-[#17343B] disabled:cursor-not-allowed disabled:opacity-45">
            {isSuggesting ? <LoaderCircle className="size-5 animate-spin" /> : <Search className="size-5" />}
          </button>
        </form>

        {isFocused && suggestions.length > 0 && (
          <div id="destination-suggestions" role="listbox" className="absolute inset-x-0 top-[52px] z-50 max-h-44 overflow-y-auto rounded-md border border-slate-200 bg-white py-1 text-slate-900 shadow-xl">
            {suggestions.map((suggestion, index) => (
              <button
                key={`${suggestion.name}-${suggestion.address}`}
                type="button"
                id={`destination-option-${index}`}
                role="option"
                aria-selected={activeIndex === index}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectSuggestion(suggestion)}
                className={`flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-slate-100 ${activeIndex === index ? "bg-slate-100" : ""}`}
              >
                <MapPin className="mt-0.5 size-4 shrink-0 text-[#145466]" />
                <span className="min-w-0"><strong className="block truncate text-sm">{suggestion.name}</strong><span className="block truncate text-xs text-slate-500">{suggestion.address}</span></span>
              </button>
            ))}
          </div>
        )}
      </div>

      {suggestionError && isFocused && (
        <p role="alert" className="mt-2 text-xs font-bold text-amber-200">{suggestionError}</p>
      )}

      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 rounded bg-black/20 px-2 py-1 text-xs font-bold text-white/80"><BusFront className="size-4 text-[#F0C929]" /> 버스 전용</span>
        {recent.length > 0 && (
          <div className="flex min-w-0 items-center justify-end gap-1.5 overflow-hidden">
            <Clock3 className="size-4 shrink-0 text-white/70" />
            {recent.map((item) => <button key={`${item.name}-${item.x ?? ""}-${item.y ?? ""}`} type="button" onClick={() => { setDestination(item.name); void submit(item); }} className="max-w-24 truncate rounded bg-white/10 px-2 py-1 text-xs font-bold text-white/85 hover:bg-white/20">{item.name}</button>)}
          </div>
        )}
      </div>
    </div>
  );
}
