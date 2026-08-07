import { useCallback, useRef, useState } from "react";
import { uploadVoiceAudio } from "../../api/client";
import { BusOption } from "../../types/bus";

type RecorderStatus = "idle" | "listening" | "loading" | "result";

type BusWithRoute = BusOption & {
  totalMin?: number;
  steps?: unknown[];
  routeDetail?: Record<string, unknown>;
};

function normalizeBuses(rawBuses: BusWithRoute[]): BusOption[] {
  return (rawBuses || []).map((bus) => ({
    ...bus,
    routeDetail: bus.routeDetail || {
      busNumber: bus.busNumber,
      totalMin: bus.totalMin || bus.arrivalMin || 0,
      steps: bus.steps || [],
    },
  })) as BusOption[];
}

export function useVoiceRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [transcript, setTranscript] = useState("듣고 있습니다...");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [destination, setDestination] = useState("");
  const [buses, setBuses] = useState<BusOption[]>([]);
  const [message, setMessage] = useState("");
  const [audioBase64, setAudioBase64] = useState("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const hasDetectedSound = useRef(false);
  const isTimeoutRef = useRef(false);

  const uploadAudioToServer = async (blob: Blob) => {
    try {
      const result = await uploadVoiceAudio(blob);

      setMessage(result.message || "");
      setAudioBase64(result.audio_base64 || "");
      setDestination(result.destination || result.destination_text || "");
      setBuses(normalizeBuses(result.buses));
      setStatus("result");
    } catch (error) {
      console.error("Audio upload failed:", error);
      alert("음성 인식 처리 중 오류가 발생했습니다.");
      setStatus("idle");
    }
  };

  const clearTimers = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    timerRef.current = null;
    silenceTimerRef.current = null;
  };

  const stopRecording = useCallback((isTimeout = false) => {
    clearTimers();
    isTimeoutRef.current = isTimeout;

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }

    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close();
    }

    if (isTimeout) {
      alert("음성이 감지되지 않았습니다. 처음부터 다시 시도해주세요.");
      setStatus("idle");
    } else {
      setStatus("loading");
    }
  }, []);

  const startRecording = async () => {
    try {
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks.current = [];
      isTimeoutRef.current = false;
      setAudioUrl(null);
      hasDetectedSound.current = false;
      setMessage("");
      setAudioBase64("");

      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      const audioContext = new AudioContextClass();
      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }
      audioContextRef.current = audioContext;

      const analyser = audioContext.createAnalyser();
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.fftSize);

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        if (isTimeoutRef.current) return;

        if (audioChunks.current.length > 0) {
          const audioBlob = new Blob(audioChunks.current, { type: "audio/webm" });
          setAudioUrl(URL.createObjectURL(audioBlob));
          await uploadAudioToServer(audioBlob);
        } else {
          setStatus("idle");
        }
      };

      mediaRecorder.start(200);
      setStatus("listening");
      setTranscript("듣고 있습니다...");
      timerRef.current = setTimeout(() => stopRecording(true), 8000);

      const checkVolume = () => {
        if (mediaRecorder.state === "inactive") return;

        analyser.getByteFrequencyData(dataArray);
        const volume = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length;

        if (volume > 5) {
          hasDetectedSound.current = true;
          if (timerRef.current) clearTimeout(timerRef.current);
          timerRef.current = null;
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
          }
        } else if (hasDetectedSound.current && !silenceTimerRef.current) {
          silenceTimerRef.current = setTimeout(() => stopRecording(false), 1000);
        }

        requestAnimationFrame(checkVolume);
      };

      checkVolume();
    } catch (err: any) {
      console.error("Recording failed:", err);
      alert(`마이크 시작 실패: ${err.name} - ${err.message}`);
      setStatus("idle");
    }
  };

  return {
    status,
    transcript,
    audioUrl,
    audioChunks,
    destination,
    buses,
    message,
    audioBase64,
    startRecording,
    stopRecording,
  };
}

export function VoiceRecording({ transcript }: { transcript: string }) {
  return (
    <p className="text-4xl font-black text-white text-center drop-shadow-lg leading-tight animate-pulse">
      {transcript}
    </p>
  );
}
