import { BusInfoList } from "./components/BusInfoList";
import { VoiceAssistant } from "./components/VoiceAssistant";
import { useState } from "react";

export default function App() {
  const [isRouteMode, setIsRouteMode] = useState(false);

  return (
    <main className="mx-auto flex h-dvh min-h-0 w-full max-w-[1280px] flex-col overflow-hidden bg-white shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
      {/*
        대기 화면에서 아래 음성 패널은 제목·안내문·검색창·마이크만 담아 183px 면
        충분한데 320px 를 받고 있었습니다. 그동안 위 전광판은 도착 행을 한 줄밖에
        못 보여 줬습니다. 남는 공간을 정보가 있는 쪽으로 돌립니다.
        (경로를 조회한 뒤에는 반대로 경로 안내가 주인공이므로 비율을 뒤집습니다.)
      */}
      <section className={`min-h-0 w-full shrink-0 overflow-hidden ${isRouteMode ? "h-[36%]" : "h-[64%] md:h-[68%]"}`}>
        <BusInfoList compact={isRouteMode} />
      </section>
      <section className={`relative min-h-0 w-full shrink-0 overflow-hidden ${isRouteMode ? "h-[64%]" : "h-[36%] md:h-[32%]"}`}>
        <VoiceAssistant onResultModeChange={setIsRouteMode} />
      </section>
    </main>
  );
}
