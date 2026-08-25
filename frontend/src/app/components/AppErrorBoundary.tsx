import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  secondsLeft: number;
}

// 무인 정류장에는 새로고침을 눌러 줄 사람이 없습니다. 화면이 죽은 채로 방치되지
// 않도록 스스로 다시 불러옵니다. 이용자가 읽고 상황을 인지할 만큼은 기다립니다.
const AUTO_RELOAD_SECONDS = 15;

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, secondsLeft: AUTO_RELOAD_SECONDS };
  private countdownId: ReturnType<typeof setInterval> | null = null;

  static getDerivedStateFromError(): State {
    return { hasError: true, secondsLeft: AUTO_RELOAD_SECONDS };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Application render failed", error.name, info.componentStack);
    this.startAutoReload();
  }

  componentWillUnmount() {
    if (this.countdownId) clearInterval(this.countdownId);
  }

  private startAutoReload() {
    if (this.countdownId) return;
    this.countdownId = setInterval(() => {
      this.setState((current) => {
        if (current.secondsLeft <= 1) {
          if (this.countdownId) clearInterval(this.countdownId);
          this.countdownId = null;
          window.location.reload();
          return { ...current, secondsLeft: 0 };
        }
        return { ...current, secondsLeft: current.secondsLeft - 1 };
      });
    }, 1000);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <main role="alert" className="grid min-h-dvh place-items-center bg-[#E8EEF0] p-6 text-[#171D23]">
        <section className="w-full max-w-md rounded-md border border-red-200 bg-white p-6 text-center shadow-lg">
          <AlertTriangle className="mx-auto mb-3 size-10 text-red-600" />
          <h1 className="text-xl font-black">화면을 불러오지 못했습니다</h1>
          <p className="mt-2 text-sm font-medium text-slate-600" aria-live="polite">
            {this.state.secondsLeft > 0
              ? `${this.state.secondsLeft}초 뒤 자동으로 다시 불러옵니다.`
              : "다시 불러오는 중입니다."}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex items-center gap-2 rounded-md bg-[#123E49] px-4 py-3 text-sm font-black text-white"
          >
            <RefreshCw className="size-4" /> 새로고침
          </button>
        </section>
      </main>
    );
  }
}
