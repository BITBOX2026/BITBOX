export function VoiceLoading() {
  return (
    // 페이드 인 효과를 주어 부드럽게 등장
    <div className="flex flex-col items-center gap-4 animate-in fade-in">
      {/* 텍스트에 drop-shadow-lg를 주어 가독성을 높임. */}
      <p className="text-xl font-black text-white tracking-tight drop-shadow-lg">최적의 경로를 찾는 중입니다...</p>
      {/* 점 세 개가 순차적으로 통통 튀는 애니메이션 영역 */}
      <div className="flex gap-2">
        <div className="size-2.5 bg-white rounded-full animate-bounce [animation-delay:-0.3s]" />
        <div className="size-2.5 bg-white rounded-full animate-bounce [animation-delay:-0.15s]" />
        <div className="size-2.5 bg-white rounded-full animate-bounce" />
      </div>
    </div>
  );
}