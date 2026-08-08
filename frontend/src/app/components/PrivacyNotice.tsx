import { Database, Mic, ShieldCheck, ShieldX, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export const VOICE_CONSENT_KEY = "bitbox.voiceConsent.v1";
const RECENT_DESTINATIONS_KEY = "bitbox.recentDestinations";

interface PrivacyNoticeProps {
  open: boolean;
  consentRequired: boolean;
  onAccept: () => void;
  onClose: () => void;
}

export function PrivacyNotice({ open, consentRequired, onAccept, onClose }: PrivacyNoticeProps) {
  const [recentCleared, setRecentCleared] = useState(false);
  const [consentRevoked, setConsentRevoked] = useState(false);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    dialogRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  if (!open) return null;

  const clearRecentDestinations = () => {
    localStorage.removeItem(RECENT_DESTINATIONS_KEY);
    window.dispatchEvent(new Event("bitbox:recent-cleared"));
    setRecentCleared(true);
  };

  const revokeVoiceConsent = () => {
    localStorage.removeItem(VOICE_CONSENT_KEY);
    setConsentRevoked(true);
  };

  return (
    <div className="absolute inset-0 z-[80] grid place-items-center bg-black/65 p-3" role="presentation">
      <section
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="privacy-title"
        className="max-h-full w-full max-w-[620px] overflow-y-auto rounded-md bg-white text-slate-900 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-[#145466]" />
            <h2 id="privacy-title" className="text-base font-black">음성·위치정보 처리 안내</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="안내 닫기" title="안내 닫기" className="grid size-8 place-items-center rounded hover:bg-slate-100">
            <X className="size-5" />
          </button>
        </header>

        <div className="space-y-4 px-4 py-4 text-sm leading-relaxed sm:px-5">
          <div className="flex gap-3">
            <Mic className="mt-0.5 size-5 shrink-0 text-[#145466]" />
            <div><strong className="block">음성 요청</strong><p className="text-slate-600">마이크를 누른 뒤 최대 20초간 녹음하며, 음성 인식을 위해 OpenAI로 전송합니다. BITBOX 서버는 녹음 파일과 인식 문장을 디스크에 저장하지 않습니다.</p></div>
          </div>
          <div className="flex gap-3">
            <Database className="mt-0.5 size-5 shrink-0 text-[#145466]" />
            <div><strong className="block">경로와 기기 기록</strong><p className="text-slate-600">목적지와 좌표는 경로 조회를 위해 Kakao·ODsay·공공데이터 API로 전송될 수 있습니다. 최근 목적지 최대 3개는 이 브라우저에만 저장됩니다.</p></div>
          </div>
          <p className="rounded bg-amber-50 px-3 py-2 font-bold text-amber-900">버스 도착 시각과 혼잡도는 외부 제공기관의 실시간 데이터로, 교통 상황에 따라 실제와 다를 수 있습니다.</p>

          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <button type="button" onClick={clearRecentDestinations} className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-red-700">
              <Trash2 className="size-4" /> {recentCleared ? "최근 목적지를 삭제했습니다" : "이 기기의 최근 목적지 삭제"}
            </button>
            {!consentRequired && <button type="button" onClick={revokeVoiceConsent} className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-red-700">
              <ShieldX className="size-4" /> {consentRevoked ? "음성 동의를 철회했습니다" : "음성 처리 동의 철회"}
            </button>}
          </div>
          <p className="text-xs text-slate-500">시행일: 2026-08-08 · 음성 동의는 이 기기에만 저장되며 언제든 브라우저 데이터 삭제로 철회할 수 있습니다.</p>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-slate-200 px-4 py-3 sm:px-5">
          <button type="button" onClick={onClose} className="rounded px-4 py-2 text-sm font-black text-slate-600 hover:bg-slate-100">닫기</button>
          {consentRequired && <button type="button" onClick={onAccept} className="rounded bg-[#145466] px-4 py-2 text-sm font-black text-white hover:bg-[#0F4655]">동의하고 마이크 사용</button>}
        </footer>
      </section>
    </div>
  );
}
