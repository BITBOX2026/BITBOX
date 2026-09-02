export function VoiceRecording({ transcript }: { transcript: string }) {
  return (
    <div className="mt-3 max-w-lg rounded-lg border border-white/20 bg-black/15 px-4 py-3" role="status">
      <p className="break-keep text-base font-black leading-relaxed text-white/95">{transcript}</p>
      <p className="mt-1 break-keep text-sm font-bold leading-relaxed text-white/75">
        목적지를 말씀한 뒤 노란 버튼을 다시 눌러 주세요. 말씀을 멈추면 자동으로 전송됩니다.
      </p>
    </div>
  );
}
