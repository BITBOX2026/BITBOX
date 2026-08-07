import { useState, useRef, useCallback } from 'react';
import { BusOption } from '../../types/bus';

/**
 * 1. 음성 녹음 및 TTS 안내 로직을 담당하는 훅 (Hook)
 */
export function useVoiceRecorder() {
  const [status, setStatus] = useState<'idle' | 'listening' | 'loading' | 'result'>('idle');
  const [transcript, setTranscript] = useState("듣고 있습니다...");
  const [audioUrl, setAudioUrl] = useState<string | null>(null); // 녹음 파일 재생용 URL

  // 백엔드 파이프라인이 반환한 실제 데이터 저장
  const [destination, setDestination] = useState<string>("");
  const [buses, setBuses] = useState<BusOption[]>([]);
  
  const [message, setMessage] = useState<string>("");
  const [audioBase64, setAudioBase64] = useState<string>("");
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null); 
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null); 
  
  // 실시간 오디오 덩어리들을 실시간으로 저장할 배열 변수
  const audioChunks = useRef<Blob[]>([]);
  const hasDetectedSound = useRef(false);

  // 타임아웃 종료인지 정상 침묵 종료인지 구분을 위한 플래그 Ref 추가
  const isTimeoutRef = useRef(false);

  // 녹음된 데이터를 EC2 서버로 전송
  const uploadAudioToServer = async (blob: Blob) => {
    const formData = new FormData();
    formData.append("file", blob, "recording.webm");

    try {
      console.log("서버로 데이터 전송 시작...");      
      const baseUrl = import.meta.env.VITE_API_BASE_URL || "http://3.144.238.75:8000";
      // 엔드포인트는 최적 경로를 계산해주는 `/api/process`
      const response = await fetch(`${baseUrl}/api/process`, { 
        method: "POST",
        body: formData,
      });
      
      if (!response.ok) throw new Error("서버 응답 실패");
      const result = await response.json();
      console.log("서버 응답 성공:", result);

      if (result.message) setMessage(result.message);
      if (result.audio_base64) setAudioBase64(result.audio_base64);

      if (result.status === "success" && result.data) {
        const routeData = result.data;
        
        if (routeData.destination) setDestination(routeData.destination);
        
        const mappedSteps = (routeData.route_segments || []).map((segment: any) => ({
          type: segment.vehicle_type === "지하철" ? "subway" : "bus",
          description: `${segment.line || "추천 노선"} 탑승`,
          durationMin: Math.round((routeData.total_time_min || 0) / (routeData.route_segments?.length || 1)), 
          busNumber: segment.line || "",
          fromStop: segment.start_name || "",
          toStop: segment.end_name || ""
        }));

        // BusList 컴포넌트와 규격 통일
        const recommendBus: BusOption & { routeDetail?: any } = {
          id: routeData.bus_number || "recommend-1",
          busNumber: routeData.bus_number || "추천",
          arrivalMin: routeData.arrival_time !== undefined ? routeData.arrival_time : 0,
          traTimeSec: routeData.arrival_time ? parseInt(routeData.arrival_time) * 60 : 0,
          arrivalMsg: "최적 경로 안내",
          currentStationName: routeData.origin || "올림픽공원역",
          remainingStops: -1,
          busType: 0,
          congetion: 3,
          isFullFlag: false,
          isLastBus: false,
          plainNo: "",
          isSecond: false,
          routeDetail: {
            busNumber: routeData.bus_number || "추천",
            totalMin: routeData.total_time_min || 0,
            steps: mappedSteps,
            origin_x: routeData.origin_x,
            origin_y: routeData.origin_y,
            destination_x: routeData.destination_x,
            destination_y: routeData.destination_y,
            origin: routeData.origin,
            route_segments: routeData.route_segments           
          }
        };

        setBuses([recommendBus]);
        setStatus('result');

        // 서버 결과 화면 전환과 동시에 LLM 문장 TTS 출력

      } else {
        // 만약 기존 규격 형태의 백엔드 응답일 경우를 대비한 백업 로직
        if (result.destination) setDestination(result.destination);
        if (result.buses) setBuses(result.buses);
        setStatus('result');

        // 백업 예외 응답인 경우에도 메시지가 있다면 출력 처리
      }
    } catch (error) {
      console.error("서버 전송 실패:", error);
      alert("음성 인식 처리 중 오류가 발생했습니다.");
      setStatus('idle');
    }
  };

  // 녹음 종료 함수
  const stopRecording = useCallback((isTimeout = false) => {
    // 1. 모든 타이머 정리
    if (timerRef.current) clearTimeout(timerRef.current);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);

    // 2. 타임아웃 상태 플래그 기록
    isTimeoutRef.current = isTimeout;

    // 3. 미디어 녹음 중단 명령
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
    
    // 4. AudioContext 종료
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
    }

    if (isTimeout) {
      alert("음성이 감지되지 않았습니다. 처음부터 다시 시도해주세요.");
      setStatus('idle');
    } else {
      setStatus('loading');
    }
  }, []);

  // 녹음 시작 함수
  const startRecording = async () => {
    try {
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // 데이터 초기화 정리
      audioChunks.current = [];
      isTimeoutRef.current = false; 
      setAudioUrl(null); 
      hasDetectedSound.current = false; 

      setMessage("");
      setAudioBase64("");

      // 오디오 분석기 설정
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
      audioContextRef.current = audioContext;
      const analyser = audioContext.createAnalyser();
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      
      const dataArray = new Uint8Array(analyser.fftSize);
      
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
        ? 'audio/webm;codecs=opus' 
        : 'audio/webm';
      
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      // 실시간 데이터 청크 수집 (브라우저 콘솔에 나옴)
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunks.current.push(e.data);
          console.log("데이터 청크 수신됨, 현재 총 개수:", audioChunks.current.length);
        }
      };

      // 녹음이 완전히 끝난 시점에 안전하게 실행되는 리스너 구현
      mediaRecorder.onstop = async () => {
        // 아무 말도 안 해서 타임아웃 알림이 뜬 경우라면 서버 전송을 무시하고 종료
        if (isTimeoutRef.current) {
          console.log("타임아웃으로 인한 녹음 종료 - 서버 전송을 취소합니다.");
          return;
        }

        console.log("MediaRecorder 정상 정지 완료. 최종 전달 오디오 데이터:", audioChunks.current);

        if (audioChunks.current.length > 0) {
          const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
          const url = URL.createObjectURL(audioBlob);
          setAudioUrl(url); 
          console.log("생성된 Audio URL:", url);

          // 데이터가 온전히 확보된 이 시점에서 백엔드로 파일 전송
          await uploadAudioToServer(audioBlob);
        } else {
          console.warn("녹음된 데이터(chunks)가 없습니다.");
          setStatus('idle');
        }
      };
      
      // 200ms 단위로 데이터를 나눠 주기적으로 배출
      mediaRecorder.start(200); 
      
      setStatus('listening');
      setTranscript("듣고 있습니다...");

      // A. 8초 무응답 타이머
      timerRef.current = setTimeout(() => stopRecording(true), 8000);

      // B. 실시간 음량 분석 (VAD)
      const checkVolume = () => {
        if (mediaRecorder.state === 'inactive') return;
        analyser.getByteFrequencyData(dataArray);
        const volume = dataArray.reduce((a, b) => a + b) / dataArray.length;
        console.log("현재 감지된 볼륨:", volume);

        // 녹음 볼륨 조절
        if (volume > 5) { 
          hasDetectedSound.current = true;
          clearTimeout(timerRef.current!); 
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
          }
        } else {
          if (hasDetectedSound.current && !silenceTimerRef.current) {
            silenceTimerRef.current = setTimeout(() => stopRecording(false), 1000);
          }
        }
        requestAnimationFrame(checkVolume);
      };
      checkVolume();

    } catch (err: any) {
      console.error("녹음 시작 실패:", err);
      alert(`마이크 시작 실패: ${err.name} - ${err.message}`);
    }
  };

  return { status, transcript, audioUrl, audioChunks, destination, buses, message, audioBase64, startRecording, stopRecording };
}

/**
 * 2. 화면을 담당하는 컴포넌트 (Component)
 */

export function VoiceRecording({ transcript }: { transcript: string }) {
  return (
    <p className="text-4xl font-black text-white text-center drop-shadow-lg leading-tight animate-pulse">
      {transcript}
    </p>
  );
}