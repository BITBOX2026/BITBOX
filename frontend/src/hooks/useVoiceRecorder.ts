import { useCallback, useEffect, useRef, useState } from "react";
import { requestTextRoute, uploadVoiceAudio, type RouteDestination, type TransitConfirmation, type PlaceSuggestion, type SafetyDecision } from "../api/client";
import { BusOption } from "../types/bus";
import { cancelSpeech } from "../utils/speech";

type RecorderStatus = "idle" | "starting" | "listening" | "loading" | "confirming" | "result";
const NO_SPEECH_TIMEOUT_MS = 8_000;
const MAX_RECORDING_MS = 20_000;
const REQUEST_TIMEOUT_MS = 35_000;
// 말을 마쳤다고 판단하기까지 기다리는 침묵 길이. 고령 이용자는 문장 중간에
// 쉬는 일이 잦아("올림픽공원역… 어… 가는 버스") 1초로는 발화가 잘립니다.
const SILENCE_END_MS = 1_800;
// 마이크 권한 프롬프트에 아무도 응답하지 않으면 getUserMedia 는 영영 대기합니다.
// 무인 키오스크에서는 그대로 "마이크 준비 중"에 갇히므로 상한을 둡니다.
const MIC_START_TIMEOUT_MS = 15_000;
// 사람 목소리로 판정하는 주파수 평균 임계값(0~255).
const SPEECH_VOLUME_THRESHOLD = 5;

/** getUserMedia 가 응답하지 않는 기기에서 무한 대기를 막습니다. */
async function withMicrophoneTimeout(request: Promise<MediaStream>): Promise<MediaStream> {
  let timedOut = false;
  let timer: number | undefined;
  try {
    return await Promise.race([
      request,
      new Promise<never>((_resolve, reject) => {
        timer = window.setTimeout(() => {
          timedOut = true;
          reject(new Error("마이크 응답이 없습니다. 화면의 입력창을 이용해 주세요."));
        }, MIC_START_TIMEOUT_MS);
      }),
    ]);
  } finally {
    window.clearTimeout(timer);
    if (timedOut) {
      // 뒤늦게 열린 스트림이 마이크 표시를 켜 둔 채 남지 않도록 정리합니다.
      void request.then(
        (stream) => stream.getTracks().forEach((track) => track.stop()),
        () => {},
      );
    }
  }
}

export function selectRecordingMimeType(
  isSupported: (mimeType: string) => boolean = MediaRecorder.isTypeSupported,
): string | undefined {
  return ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"]
    .find((type) => isSupported(type));
}

/** 분석기가 채워 주는 주파수 구간만으로 평균 세기를 구합니다. */
export function createVolumeReader(
  analyser: Pick<AnalyserNode, "frequencyBinCount" | "getByteFrequencyData">,
): () => number {
  // getByteFrequencyData 는 frequencyBinCount 개만 채웁니다. 버퍼를 그보다 크게
  // 잡으면 남은 칸이 0 인 채로 평균에 섞여 감도가 그만큼 떨어집니다.
  const bins = new Uint8Array(analyser.frequencyBinCount);
  return () => {
    analyser.getByteFrequencyData(bins);
    if (bins.length === 0) return 0;
    return bins.reduce((sum, value) => sum + value, 0) / bins.length;
  };
}

function normalizeBuses(rawBuses: BusOption[]): BusOption[] {
  return (rawBuses || []).map((bus) => ({
    ...bus,
    routeDetail: bus.routeDetail || (
      bus.steps?.length && bus.totalMin != null
        ? { busNumber: bus.busNumber, totalMin: bus.totalMin, steps: bus.steps }
        : undefined
    ),
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
  const requestKeyRef = useRef<string | null>(null);
  const recordingStartIdRef = useRef(0);
  const isStartingRef = useRef(false);
  const hasDetectedSound = useRef(false);

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

  const beginRequest = (requestKey: string) => {
    if (requestControllerRef.current && requestKeyRef.current === requestKey) {
      return null;
    }
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    requestKeyRef.current = requestKey;
    const timeoutId = window.setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    return { controller, timeoutId };
  };

  const uploadAudioToServer = async (blob: Blob) => {
    const request = beginRequest("voice-upload");
    if (!request) return;
    const { controller, timeoutId } = request;
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
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
        requestKeyRef.current = null;
      }
    }
  };

  const submitTextRoute = async (value: RouteDestination) => {
    const normalizedName = value.name.trim();
    const requestKey = `route:${normalizedName}:${value.x ?? ""}:${value.y ?? ""}`;
    const request = beginRequest(requestKey);
    if (!request) return;
    const { controller, timeoutId } = request;
    setStatus("loading");
    setError("");
    setMessage("");
    setAudioBase64("");
    setSafetyDecision(null);
    try {
      const result = await requestTextRoute(
        { ...value, name: normalizedName },
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
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
        requestKeyRef.current = null;
      }
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

  const clearTimers = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (maxDurationTimerRef.current) clearTimeout(maxDurationTimerRef.current);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    timerRef.current = null;
    maxDurationTimerRef.current = null;
    silenceTimerRef.current = null;
  }, []);

  const stopRecording = useCallback((isTimeout = false) => {
    clearTimers();
    if (isTimeout) recordingStartIdRef.current += 1;

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
  }, [clearTimers]);

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
      // 녹음 시작 전에 진행 중인 안내 음성을 멈춥니다(브라우저·서버 양쪽).
      cancelSpeech();

      if (!("MediaRecorder" in window)) {
        throw new Error("이 브라우저는 음성 녹음을 지원하지 않습니다.");
      }
      stream = await withMicrophoneTimeout(navigator.mediaDevices.getUserMedia({ audio: true }));
      if (recordingStartIdRef.current !== startId) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const audioChunks: Blob[] = [];
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
      const readVolume = createVolumeReader(analyser);

      const mimeType = selectRecordingMimeType();
      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        if (recordingStartIdRef.current !== startId) return;

        if (audioChunks.length > 0) {
          const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || mimeType || "application/octet-stream" });
          await uploadAudioToServer(audioBlob);
        } else {
          // 소리가 하나도 담기지 않았는데 조용히 첫 화면으로 돌아가면 이용자는
          // 무엇이 잘못됐는지 알 수 없습니다. 이유를 남깁니다.
          setError("녹음된 소리가 없습니다. 마이크에 가까이 대고 다시 말씀해 주세요.");
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

        const volume = readVolume();

        if (volume > SPEECH_VOLUME_THRESHOLD) {
          hasDetectedSound.current = true;
          if (timerRef.current) clearTimeout(timerRef.current);
          timerRef.current = null;
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
          }
        } else if (hasDetectedSound.current && !silenceTimerRef.current) {
          silenceTimerRef.current = setTimeout(() => stopRecording(false), SILENCE_END_MS);
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

  const reset = useCallback(() => {
    clearTimers();
    recordingStartIdRef.current += 1;
    isStartingRef.current = false;
    requestControllerRef.current?.abort("reset");
    requestControllerRef.current = null;
    requestKeyRef.current = null;
    if (mediaRecorderRef.current?.state !== "inactive") {
      mediaRecorderRef.current?.stop();
    }
    // 녹음기가 이미 inactive 여도 스트림이 살아 있으면 마이크 표시가 남으므로 항상 정리합니다.
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    if (audioContextRef.current?.state !== "closed") void audioContextRef.current?.close();
    cancelSpeech();
    setStatus("idle");
    setDestination("");
    setBuses([]);
    setMessage("");
    setAudioBase64("");
    setError("");
    setConfirmation(null);
    setSafetyDecision(null);
  }, [clearTimers]);

  useEffect(() => () => {
    clearTimers();
    recordingStartIdRef.current += 1;
    isStartingRef.current = false;
    requestControllerRef.current?.abort("unmount");
    requestControllerRef.current = null;
    requestKeyRef.current = null;
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
