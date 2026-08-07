import type { BusOption, RouteDetail } from "../types/bus";

export type TransitResponse = {
  success: boolean;
  text?: string | null;
  intent?: string | null;
  destination?: string | null;
  destination_text?: string | null;
  bus_number?: string | null;
  arrival_time?: string | null;
  arrival_time_2?: string | null;
  first_bus_time?: string | null;
  message: string;
  buses: Array<BusOption & { routeDetail?: RouteDetail }>;
  audio_base64?: string | null;
  request_id?: string | null;
};

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim() || "";
  if (
    configured.startsWith("http://") &&
    typeof window !== "undefined" &&
    window.location.protocol === "https:"
  ) {
    throw new Error("HTTPS 화면에서는 HTTP API 서버를 사용할 수 없습니다.");
  }
  return configured.replace(/\/+$/, "");
}

function getAuthHeaders(): HeadersInit {
  const token = import.meta.env.VITE_API_AUTH_TOKEN;
  return token ? { "x-bitbox-token": token } : {};
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  Object.entries(getAuthHeaders()).forEach(([key, value]) => headers.set(key, value));

  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });
}

async function parseTransitResponse(response: Response): Promise<TransitResponse> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail || payload?.message;
    throw new Error(detail || `서버 요청에 실패했습니다. (${response.status})`);
  }
  return payload as TransitResponse;
}

export async function uploadVoiceAudio(blob: Blob): Promise<TransitResponse> {
  const formData = new FormData();
  formData.append("file", blob, "recording.webm");

  const response = await apiFetch("/api/upload", {
    method: "POST",
    body: formData,
  });

  return parseTransitResponse(response);
}

export async function requestTextRoute(
  destination: string,
  origin?: string,
  transportMode: "bus" | "subway" | "transit" = "bus",
): Promise<TransitResponse> {
  const response = await apiFetch("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ destination, origin: origin || null, transport_mode: transportMode }),
  });
  return parseTransitResponse(response);
}
