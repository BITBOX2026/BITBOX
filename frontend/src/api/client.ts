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
  needs_confirmation?: boolean;
  confirmation?: TransitConfirmation | null;
};

export type TransitConfirmation = {
  kind: "place";
  prompt: string;
  candidate: PlaceSuggestion;
  alternatives: PlaceSuggestion[];
};

export interface PlaceSuggestion {
  name: string;
  address: string;
  x?: string | null;
  y?: string | null;
  category?: string | null;
  category_code?: string | null;
}

export interface RouteDestination {
  name: string;
  address?: string | null;
  x?: number | null;
  y?: number | null;
}

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

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
  });
}

export async function parseApiResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail || payload?.message;
    throw new Error(withSupportCode(detail || `${fallbackMessage} (${response.status})`, response));
  }
  if (payload === null) {
    throw new Error(withSupportCode("서버 응답 형식을 확인하지 못했습니다.", response));
  }
  return payload as T;
}

async function parseTransitResponse(response: Response): Promise<TransitResponse> {
  return parseApiResponse<TransitResponse>(response, "서버 요청에 실패했습니다.");
}

export async function uploadVoiceAudio(blob: Blob, signal?: AbortSignal): Promise<TransitResponse> {
  const formData = new FormData();
  const extension = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  formData.append("file", blob, `recording.${extension}`);

  const response = await apiFetch("/api/upload", {
    method: "POST",
    body: formData,
    signal,
  });

  return parseTransitResponse(response);
}

export async function requestTextRoute(
  destination: RouteDestination,
  origin?: string,
  signal?: AbortSignal,
): Promise<TransitResponse> {
  const response = await apiFetch("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      destination: destination.name,
      destination_address: destination.address || null,
      destination_x: destination.x ?? null,
      destination_y: destination.y ?? null,
      origin: origin || null,
      transport_mode: "bus",
    }),
    signal,
  });
  return parseTransitResponse(response);
}

export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<PlaceSuggestion[]> {
  const params = new URLSearchParams({ query: query.trim() });
  const response = await apiFetch(`/api/places/suggest?${params}`, { signal });
  const payload = await parseApiResponse<{ suggestions?: PlaceSuggestion[] }>(response, "장소 검색에 실패했습니다.");
  return Array.isArray(payload?.suggestions) ? payload.suggestions : [];
}

function withSupportCode(message: string, response: Response): string {
  const requestId = response.headers.get("x-request-id")?.slice(0, 12);
  return requestId ? `${message} (문의 코드: ${requestId})` : message;
}
