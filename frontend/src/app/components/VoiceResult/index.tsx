import { MapPin, Mic, Home, Volume2 } from "lucide-react";
import { BusList } from "./BusList"; 
import { RouteDetailOverlay } from "./RouteDetail";
import { BusOption } from "../../../types/bus";
import { useEffect, useState, useRef, RefObject } from "react";

export function VoiceResult({
    destination = "",
    buses = [],
    message = "",          
    audioBase64 = "",     
    audio_base64 = "",
    audioChunks: _audioChunks,
    onReset,
    onGoHome
}: {
    destination?: string;
    buses?: BusOption[];
    message?: string;
    audioBase64?: string;
    audio_base64?: string;
    audioChunks?: RefObject<Blob[]>;
    onReset: () => void;
    onGoHome: () => void;
}) {
    const [viewMode, setViewMode] = useState<'text' | 'map'>('text');
    const [selectedBus, setSelectedBus] = useState<BusOption | null>(null);
    
    // 자막 상태 및 중복 재생 방지 Ref
    const [isSpeaking, setIsSpeaking] = useState(false);
    const playedMessageRef = useRef<string>("");

    const rawAudioData = audio_base64 || audioBase64;

    useEffect(() => {
        if (buses && buses.length > 0) {
            setSelectedBus(buses[0]);
        }
    }, [buses]);

    // TTS 재생 및 자막 동기화
    useEffect(() => {
        if (!message) return;

        // 이미 동일한 메시지로 재생 중이라면 재렌더링에 의한 자막 리셋 방지
        if (playedMessageRef.current === message && isSpeaking) return;
        playedMessageRef.current = message;

        // 1. 백엔드 오디오(Base64) 데이터 처리
        if (rawAudioData) {
            const audioUrl = rawAudioData.startsWith('data:') 
                ? rawAudioData 
                : `data:audio/wav;base64,${rawAudioData}`;

            const audio = new Audio(audioUrl);

            // 오디오 시작 즉시 자막 켜기
            setIsSpeaking(true);

            // 오디오가 끝까지 다 읽히면 자막 끄기
            audio.onended = () => {
                setIsSpeaking(false);
            };

            audio.onerror = (e) => {
                console.error("오디오 재생 실패:", e);
                setIsSpeaking(false);
            };

            audio.play().catch((err) => {
                console.warn("오디오 자동재생 차단됨:", err);
                setIsSpeaking(false);
            });
        } 
        // 2. 브라우저 Web Speech API (Fallback)
        else if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();

            const utterance = new SpeechSynthesisUtterance(message);
            utterance.lang = 'ko-KR';
            utterance.rate = 0.85;

            setIsSpeaking(true);

            utterance.onend = () => setIsSpeaking(false);
            utterance.onerror = () => setIsSpeaking(false);

            window.speechSynthesis.speak(utterance);
        }
    }, [message, rawAudioData]);

    const handleBusClick = (bus: BusOption) => {
        setSelectedBus(bus);
    };
  
    return (
        <div className="w-full h-full flex flex-col font-['Noto_Sans_KR'] overflow-hidden relative" style={{ background: "#1A66CC" }}>
            {/* 1. 글로벌 헤더 영역 */}
            <div className="h-14 flex items-center justify-between px-6 border-b border-white/10 shrink-0 z-10">
                <div className="flex items-center gap-4">
                    <button 
                        type="button"
                        onClick={onGoHome} 
                        className="flex flex-row items-center gap-1.5 px-3 py-1.5 bg-white/10 border border-white/20 rounded-lg text-white font-bold text-sm hover:bg-white/20 transition-all shrink-0"
                    >
                        <Home className="w-4 h-4 shrink-0" />
                        <span className="whitespace-nowrap">처음으로</span>
                    </button>

                    <div className="flex items-center gap-2">
                        <MapPin className="w-5 h-5 text-green-300 shrink-0" />
                        <span className="text-xl font-black text-white whitespace-nowrap">{destination || "목적지"} 가는 버스</span>
                    </div>
                </div>
                
                <div>
                    <button 
                        type="button"
                        onClick={onReset} 
                        className="flex flex-row items-center gap-1.5 px-3 py-1.5 bg-blue-50/10 border border-blue-100/20 rounded-lg text-white font-bold text-sm hover:bg-blue-50/20 transition-all"
                    >
                        <Mic className="w-4 h-4 shrink-0" />
                        <span className="whitespace-nowrap">다시 말하기</span>
                    </button>
                </div>
            </div>

            {/* 2. 메인 콘텐츠 영역 */}
            <div className="flex-1 flex overflow-hidden relative">
                <BusList buses={buses} selectedId={selectedBus?.id} onBusClick={handleBusClick} />
                
                <div className="flex-1 bg-white relative">
                    {selectedBus && (selectedBus as any).routeDetail ? (
                        <RouteDetailOverlay 
                            route={(selectedBus as any).routeDetail} 
                            destination={destination} 
                            viewMode={viewMode}
                            onToggleView={() => setViewMode(prev => prev === 'text' ? 'map' : 'text')} 
                            onClose={() => { }} 
                        />
                    ) : (
                        <div className="flex-1 h-full flex items-center justify-center">
                            <div className="text-gray-400 font-bold">경로 데이터를 구성 중입니다...</div>
                        </div>
                    )}
                </div>
            </div>

            {/* 3. 하단 실시간 자막 배너 */}
            {isSpeaking && message && (
                <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-[999] max-w-[85%] w-auto bg-gray-900/95 text-white px-6 py-4 rounded-2xl shadow-2xl border-2 border-yellow-400/50 backdrop-blur-md flex items-center gap-4 transition-all duration-300">
                    <div className="relative flex h-3.5 w-3.5 shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-green-500"></span>
                    </div>
                    <Volume2 className="w-7 h-7 text-yellow-300 shrink-0 animate-pulse" />
                    <p className="text-lg font-bold text-yellow-100 leading-snug break-keep">
                        {message}
                    </p>
                </div>
            )}
        </div>
    );
}