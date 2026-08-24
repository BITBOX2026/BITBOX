import { Check, MapPin, Mic, TrainFront } from "lucide-react";
import type { PlaceSuggestion, TransitConfirmation } from "../../api/client";

interface VoiceConfirmationProps {
  confirmation: TransitConfirmation;
  transcript: string;
  onSelect: (place: PlaceSuggestion) => void;
  onRetry: () => void;
}

export function VoiceConfirmation({ confirmation, transcript, onSelect, onRetry }: VoiceConfirmationProps) {
  const candidate = confirmation.candidate;
  const alternatives = confirmation.alternatives || [];
  if (!candidate) return null;

  return (
    <div className="fade-enter min-w-0" role="dialog" aria-labelledby="place-confirmation-title">
      <p className="mb-1 text-xs font-extrabold text-[#F0C929]">장소 확인</p>
      <h2 id="place-confirmation-title" className="text-[clamp(22px,4vw,34px)] font-black leading-tight">
        {confirmation.prompt}
      </h2>
      {transcript && <p className="mt-2 text-sm text-white/65">“{transcript}”로 들었어요.</p>}

      <button type="button" onClick={() => onSelect(candidate)} className="mt-4 flex w-full max-w-[520px] items-center gap-3 rounded-lg border-2 border-[#F0C929] bg-white px-4 py-3 text-left text-slate-900 shadow-xl">
        {candidate.category_code === "SW8" ? <TrainFront className="size-6 shrink-0 text-[#145466]" /> : <MapPin className="size-6 shrink-0 text-[#145466]" />}
        <span className="min-w-0 flex-1">
          <strong className="block truncate text-base">{candidate.name}</strong>
          <span className="block truncate text-xs text-slate-500">{candidate.category || candidate.address}</span>
        </span>
        <Check className="size-5 shrink-0 text-emerald-600" />
      </button>

      {alternatives.length > 0 && (
        <div className="mt-3 flex max-w-[520px] flex-wrap gap-2" aria-label="다른 장소 후보">
          {alternatives.slice(0, 3).map((place) => (
            <button key={`${place.name}-${place.x}`} type="button" onClick={() => onSelect(place)} className="rounded-md bg-white/10 px-3 py-2 text-xs font-bold text-white hover:bg-white/20">
              {place.name}
            </button>
          ))}
        </div>
      )}

      <button type="button" onClick={onRetry} className="mt-4 inline-flex items-center gap-2 rounded-md border border-white/25 px-3 py-2 text-sm font-bold text-white/85 hover:bg-white/10">
        <Mic className="size-4" /> 다시 말하기
      </button>
    </div>
  );
}
