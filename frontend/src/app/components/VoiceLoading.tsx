export function VoiceLoading() {
  return (
    <div className="fade-enter max-w-md">
      <p className="mb-2 text-xs font-extrabold text-[#F0C929]">경로 계산 중</p>
      <h2 className="text-[clamp(23px,4vw,34px)] font-black leading-tight">가장 알맞은 이동 경로를 찾고 있어요</h2>
      <div className="mt-5 h-1.5 w-full overflow-hidden rounded-full bg-white/15">
        <div className="route-progress h-full w-1/3 rounded-full bg-[#F0C929]" />
      </div>
    </div>
  );
}
