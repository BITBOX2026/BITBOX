export function VoiceRecording({ transcript }: { transcript: string }) {
  return (
    <p className="mt-3 max-w-lg truncate text-base font-bold text-white/65">
      {transcript}
    </p>
  );
}
