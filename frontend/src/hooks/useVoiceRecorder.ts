import { useCallback, useEffect, useRef, useState } from "react";
import { requestTextRoute, uploadVoiceAudio, type RouteDestination, type TransitConfirmation, type PlaceSuggestion, type SafetyDecision } from "../api/client";
import { BusOption } from "../types/bus";

type RecorderStatus = "idle" | "starting" | "listening" | "loading" | "confirming" | "result";
const NO_SPEECH_TIMEOUT_MS = 8_000;
const MAX_RECORDING_MS = 20_000;
const REQUEST_TIMEOUT_MS = 35_000;

export function selectRecordingMimeType(
  isSupported: (mimeType: string) => boolean = MediaRecorder.isTypeSupported,
): string | undefined {
  return ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"]
    .find((type) => isSupported(type));
}

function normalizeBuses(rawBuses: BusOption[]): BusOption[] {
  return (rawBuses || []).map((bus) => ({
    ...bus,
    routeDetail: bus.routeDetail || {
      busNumber: bus.busNumber,
      totalMin: bus.totalMin || bus.arrivalMin || 0,
      steps: bus.steps || [],
    },
  }));
}

export function useVoiceRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [transcript, setTranscript] = useState("듣고 있습니다...");
  const [destination, setDestination] = useState("");
  const [buses, setBuses] = useState<BusOption[]>([]);
  const [message, setMessage] = useState("");
  const [audioBase64, setAudioBase64] = useState("");
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<TransitConfirmation | null>(null);
  const [safetyDecision, setSafetyDecision] = useState<SafetyDecision | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxDurationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const recordingStartIdRef = useRef(0);
  const isStartingRef = useRef(false);
  const audioChunks = useRef<Blob[]>([]);
  const hasDetectedSound = useRef(false);
  const isTimeoutRef = useRef(false);

  const applyResult = (result: Awaited<ReturnType<typeof uploadVoiceAudio>>) => {
    setTranscript(result.text || "");
    setSafetyDecision(result.safety_decision || null);
    if (
      result.needs_confirmation
      && result.confirmation?.kind === "place"
      && result.confirmation.candidate?.name
    ) {
      setError("");
      setMessage(result.message || result.confirmation.prompt);
      setAudioBase64(result.audio_base64 || "");
      setDestination(result.destination || result.destination_text || "");
      setBuses([]);
      setConfirmation(result.confirmation);
      setStatus("confirming");
      return;
    }
    if (result.needs_confirmation && !result.confirmation && result.success) {
      setError("확인할 장소 정보가 올바르지 않습니다. 목적지를 다시 말씀해 주세요.");
      setConfirmation(null);
      setSafetyDecision(null);
      setStatus("idle");
      return;
    }
    if (!result.success) {
      setError(result.message || "경로를 찾지 못했습니다.");
      setStatus("idle");
      return;
    }
    if (!result.buses?.length && result.intent === "arrival") {
      setError("");
      setConfirmation(null);
      setMessage(result.message || "현재 표시할 수 있는 버스 도착 정보가 없습니다.");
      setAudioBase64(result.audio_base64 || "");
      setDestination(result.destination || result.destination_text || "버스 운행 안내");
      setBuses([]);
      setStatus("result");
      return;
    }
    if (!result.buses?.length) {
      setError(result.message || "표시할 수 있는 버스 경로가 없습니다.");
      setStatus("idle");
      return;
    }

    setError("");
    setConfirmation(null);
    setMessage(result.message || "");
    setAudioBase64(result.audio_base64 || "");
    setDestination(result.destination || result.destination_text || "");
    setBuses(normalizeBuses(result.buses));
    setStatus("result");
  };

  const beginRequest = () => {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeoutId = window.setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    return { controller, timeoutId };
  };

  const uploadAudioToServer = async (blob: Blob) => {
    const { controller, timeoutId } = beginRequest();
    try {
      const result = await uploadVoiceAudio(blob, controller.signal);
      if (requestControllerRef.current !== controller) return;
      applyResult(result);
    } catch (error) {
      if (requestControllerRef.current !== controller) return;
      console.error("Audio upload failed:", error);
      setError(controller.signal.aborted ? "음성 요청 시간이 초과되었습니다. 다시 시도해 주세요." : error instanceof Error ? error.message : "음성 인식 처리 중 오류가 발생했습니다.");
      setStatus("idle");
    } finally {
      window.clearTimeout(timeoutId);
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  };

  const submitTextRoute = async (value: RouteDestination) => {
    const { controller, timeoutId } = beginRequest();
    setStatus("loading");
    setError("");
    setMessage("");
    setAudioBase64("");
    setSafetyDecision(null);
    try {
      const result = await requestTextRoute(
        { ...value, name: value.name.trim() },
        undefined,
        controller.signal,
      );
      if (requestControllerRef.current !== controller) return;
      applyResult(result);
    } catch (routeError) {
      if (requestControllerRef.current !== controller) return;
      console.error("Text route lookup failed:", routeError);
      setError(controller.signal.aborted ? "경로 조회 시간이 초과되었습니다. 다시 시도해 주세요." : routeError instanceof Error ? routeError.message : "경로 조회에 실패했습니다.");
      setStatus("idle");
    } finally {
      window.clearTimeout(timeoutId);
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  };

  const confirmPlace = async (place: PlaceSuggestion) => {
    const x = place.x == null ? null : Number(place.x);
    const y = place.y == null ? null : Number(place.y);
    await submitTextRoute({
      name: place.name,
      address: place.address,
      x: Number.isFinite(x) ? x : null,
      y: Number.isFinite(y) ? y : null,
    });
  };

  const clearTimers = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (maxDurationTimerRef.current) clearTimeout(maxDurationTimerRef.current);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    timerRef.current = null;
    maxDurationTimerRef.current = null;
    silenceTimerRef.current = null;
  };

  const stopRecording = useCallback((isTimeout = false) => {
    clearTimers();
    isTimeoutRef.current = isTimeout;

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());

    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close();
    }

    if (isTimeout) {
      setError("음성이 감지되지 않았습니다. 다시 시도해 주세요.");
      setStatus("idle");
    } else {
      setStatus("loading");
    }
  }, []);

  const startRecording = async () => {
    if (isStartingRef.current || mediaRecorderRef.current?.state === "recording") return;

    isStartingRef.current = true;
    const startId = ++recordingStartIdRef.current;
    setStatus("starting");
    let stream: MediaStream | null = null;
    let audioContext: AudioContext | null = null;
    try {
      if (!window.isSecureContext && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
        throw new Error("음성 기능은 HTTPS 연결에서만 사용할 수 있습니다. 목적지를 직접 입력해 주세요.");
      }
      if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
      }

      if (!("MediaRecorder" in window)) {
        throw new Error("이 브라우저는 음성 녹음을 지원하지 않습니다.");
      }
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (recordingStartIdRef.current !== startId) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      audioChunks.current = [];
      isTimeoutRef.current = false;
      hasDetectedSound.current = false;
      setConfirmation(null);
      setSafetyDecision(null);
      setMessage("");
      setAudioBase64("");
      setError("");

      const AudioContextClass = window.AudioContext || (window as typeof window & {
        webkitAudioContext?: typeof AudioContext;
      }).webkitAudioContext;
      if (!AudioContextClass) throw new Error("이 브라우저는 음성 분석을 지원하지 않습니다.");
      audioContext = new AudioContextClass();
      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }
      audioContextRef.current = audioContext;

      const analyser = audioContext.createAnalyser();
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.fftSize);

      const mimeType = selectRecordingMimeType();
      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        if (isTimeoutRef.current) return;

        if (audioChunks.current.length > 0) {
          const audioBlob = new Blob(audioChunks.current, { type: mediaRecorder.mimeType || mimeType || "application/octet-stream" });
          await uploadAudioToServer(audioBlob);
        } else {
          setStatus("idle");
        }
      };

      mediaRecorder.start(200);
      setStatus("listening");
      setTranscript("듣고 있습니다...");
      timerRef.current = setTimeout(() => stopRecording(true), NO_SPEECH_TIMEOUT_MS);
      maxDurationTimerRef.current = setTimeout(() => stopRecording(false), MAX_RECORDING_MS);

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
    } catch (err: unknown) {
      stream?.getTracks().forEach((track) => track.stop());
      if (audioContext?.state !== "closed") void audioContext?.close();
      if (recordingStartIdRef.current !== startId) return;
      console.error("Recording failed:", err);
      const message = err instanceof Error ? err.message : "마이크를 시작하지 못했습니다.";
      setError(`마이크를 사용할 수 없습니다. ${message}`);
      setStatus("idle");
    } finally {
      if (recordingStartIdRef.current === startId) isStartingRef.current = false;
    }
  };

  const reset = () => {
    clearTimers();
    recordingStartIdRef.current += 1;
    isStartingRef.current = false;
    isTimeoutRef.current = true;
    requestControllerRef.current?.abort("reset");
    requestControllerRef.current = null;
    if (mediaRecorderRef.current?.state !== "inactive") {
      mediaRecorderRef.current?.stop();
    }
    // 녹음기가 이미 inactive 여도 스트림이 살아 있으면 마이크 표시가 남으므로 항상 정리합니다.
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    if (audioContextRef.current?.state !== "closed") void audioContextRef.current?.close();
    window.speechSynthesis?.cancel();
    setStatus("idle");
    setDestination("");
    setBuses([]);
    setMessage("");
    setAudioBase64("");
    setError("");
    setConfirmation(null);
    setSafetyDecision(null);
  };

  useEffect(() => () => {
    clearTimers();
    recordingStartIdRef.current += 1;
    isStartingRef.current = false;
    isTimeoutRef.current = true;
    requestControllerRef.current?.abort("unmount");
    if (mediaRecorderRef.current?.state !== "inactive") {
      mediaRecorderRef.current?.stop();
    }
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    if (audioContextRef.current?.state !== "closed") void audioContextRef.current?.close();
  }, []);

  return {
    status,
    transcript,
    destination,
    buses,
    message,
    audioBase64,
    error,
    confirmation,
    safetyDecision,
    startRecording,
    stopRecording,
    submitTextRoute,
    confirmPlace,
    reset,
  };
}
