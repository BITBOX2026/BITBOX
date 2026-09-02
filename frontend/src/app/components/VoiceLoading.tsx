export function VoiceLoading() {
  return (
    <div className="fade-enter max-w-md" role="status" aria-live="polite">
      <p className="mb-2 text-xs font-extrabold text-[#F0C929]">경로 계산 중</p>
      <h2 className="text-[clamp(1.4375rem,4vw,2.125rem)] font-black leading-tight">가장 알맞은 이동 경로를 찾고 있어요</h2>
      <p className="mt-2 text-sm font-bold leading-relaxed text-white/75">장소와 버스 경로를 확인하고 있습니다. 30초 이상 걸리면 다시 시도할 수 있게 안내합니다.</p>
      <div className="mt-5 h-1.5 w-full overflow-hidden rounded-full bg-white/15">
        <div className="route-progress h-full w-1/3 rounded-full bg-[#F0C929]" />
      </div>
    </div>
  );
}
