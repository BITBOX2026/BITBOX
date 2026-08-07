import { BusInfoList } from "./components/BusInfoList";
import { VoiceAssistant } from "./components/VoiceAssistant"; 
import { useKakaoLoader } from "react-kakao-maps-sdk";

export default function App() {
  
  // 카카오 지도 엔진 비동기 로드
  useKakaoLoader({
    appkey: import.meta.env.VITE_KAKAO_MAP_APPKEY, 
    libraries: ["services", "clusterer"],
  });

  return (
    <div className="size-full flex flex-col max-w-[800px] mx-auto bg-white" style={{ aspectRatio: '10/16' }}>
      
      {/* 상단 - 버스 정보 (60% 높이 고정, 축소 방지) */}
      <div className="h-[60%] w-full shrink-0 overflow-hidden">
        <BusInfoList />
      </div>
      
      {/* 하단 - 음성인식 안내 및 결과 (40% 높이 고정, 축소 방지) */}
      <div className="h-[40%] w-full shrink-0 overflow-hidden relative">
        <VoiceAssistant />
      </div>
    </div>
  );
}