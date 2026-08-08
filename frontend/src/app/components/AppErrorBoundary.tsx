import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Application render failed", error.name, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <main role="alert" className="grid min-h-dvh place-items-center bg-[#E8EEF0] p-6 text-[#171D23]">
        <section className="w-full max-w-md rounded-md border border-red-200 bg-white p-6 text-center shadow-lg">
          <AlertTriangle className="mx-auto mb-3 size-10 text-red-600" />
          <h1 className="text-xl font-black">화면을 불러오지 못했습니다</h1>
          <p className="mt-2 text-sm font-medium text-slate-600">잠시 후 다시 시도해 주세요.</p>
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
