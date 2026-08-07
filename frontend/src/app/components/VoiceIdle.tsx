export const VoiceIdle = {
  // 상단 말풍선 : "목적지를 말씀해 주세요"
  SpeechBubble: () => (
    // animate-in 등을 사용하여 아래에서 위로 나타나는 효과
    <div className="relative animate-in fade-in slide-in-from-bottom-2">
      <div className="bg-white rounded-[18px] px-6 py-3.5 shadow-xl text-center min-w-[220px]">
        <p className="text-[20px] font-[800] text-[#000000] leading-tight m-0">
          버튼을 눌러<br />목적지를 말씀해 주세요
        </p>
      </div>
      {/* 말풍선 꼬리 구현 */}
      <div className="absolute bottom-[-12px] left-1/2 -translate-x-1/2 w-0 h-0 border-l-[13px] border-l-transparent border-r-[13px] border-r-transparent border-t-[13px] border-t-white" />
    </div>
  ),
};
