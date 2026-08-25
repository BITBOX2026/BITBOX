import { BusInfoList } from "./components/BusInfoList";
import { VoiceAssistant } from "./components/VoiceAssistant";
import { useState } from "react";

export default function App() {
  const [isRouteMode, setIsRouteMode] = useState(false);

  return (
    <main className="mx-auto flex h-dvh min-h-[680px] w-full max-w-[1280px] flex-col overflow-hidden bg-white shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
      <section className={`min-h-0 w-full shrink-0 overflow-hidden transition-[height] duration-500 ${isRouteMode ? "h-[30%] md:h-[36%]" : "h-[58%] md:h-[60%]"}`}>
        <BusInfoList />
      </section>
      <section className={`relative min-h-0 w-full shrink-0 overflow-hidden transition-[height] duration-500 ${isRouteMode ? "h-[70%] md:h-[64%]" : "h-[42%] md:h-[40%]"}`}>
        <VoiceAssistant onResultModeChange={setIsRouteMode} />
      </section>
    </main>
  );
}
