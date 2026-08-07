import { BusInfoList } from "./components/BusInfoList";
import { VoiceAssistant } from "./components/VoiceAssistant"; 
import { useKakaoLoader } from "react-kakao-maps-sdk";

export default function App() {
  useKakaoLoader({
    appkey: import.meta.env.VITE_KAKAO_MAP_APPKEY || "",
    libraries: ["services", "clusterer"],
  });

  return (
    <main className="mx-auto flex h-dvh min-h-[680px] w-full max-w-[960px] flex-col overflow-hidden border-x border-black/10 bg-white shadow-2xl">
      <section className="h-[58%] min-h-0 w-full shrink-0 overflow-hidden md:h-[60%]">
        <BusInfoList />
      </section>
      <section className="relative h-[42%] min-h-0 w-full shrink-0 overflow-hidden md:h-[40%]">
        <VoiceAssistant />
      </section>
    </main>
  );
}
