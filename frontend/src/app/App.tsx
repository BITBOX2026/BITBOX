import { BusInfoList } from "./components/BusInfoList";
import { VoiceAssistant } from "./components/VoiceAssistant"; 
import { useKakaoLoader } from "react-kakao-maps-sdk";

export default function App() {
  
  // 카카오 지도 엔진 비동기 로드
  useKakaoLoader({
    appkey: import.meta.env.VITE_KAKAO_MAP_APPKEY || "",
    libraries: ["services", "clusterer"],
  });

  return (
    <main className="mx-auto flex h-dvh min-h-[720px] w-full max-w-[900px] flex-col overflow-hidden bg-white shadow-2xl">
      
      {/* 상단 - 버스 정보 (60% 높이 고정, 축소 방지) */}
      <section className="h-[58%] min-h-0 w-full shrink-0 overflow-hidden md:h-[60%]">
        <BusInfoList />
      </section>
      
      {/* 하단 - 음성인식 안내 및 결과 (40% 높이 고정, 축소 방지) */}
      <section className="relative h-[42%] min-h-0 w-full shrink-0 overflow-hidden md:h-[40%]">
        <VoiceAssistant />
      </section>
    </main>
  );
}
